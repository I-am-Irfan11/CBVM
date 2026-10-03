import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, ScanLine } from "lucide-react";
import { api } from "../services/api";

export default function DemoControls({ notify, refresh }) {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleId, setVehicleId] = useState("");
  const [direction, setDirection] = useState("IN");
  const [stream, setStream] = useState(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraPending, setCameraPending] = useState(false);
  const [pending, setPending] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [capturedFrame, setCapturedFrame] = useState("");
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    let active = true;
    api("/vehicles?limit=100").then((data) => {
      if (!active) return;
      const activeVehicles = (data.items || []).filter((vehicle) => vehicle.status === "active");
      setVehicles(activeVehicles);
      setVehicleId((current) => current || activeVehicles[0]?.id || "");
    }).catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [notify]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return undefined;
    video.srcObject = stream;
    video.play().catch(() => setCameraError("Allow camera access in your browser, then try again."));
    return () => { video.srcObject = null; };
  }, [stream]);

  useEffect(() => () => stream?.getTracks().forEach((track) => track.stop()), [stream]);

  async function startCamera() {
    setCameraPending(true);
    setCameraError("");
    setCapturedFrame("");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("This browser does not provide camera access. Open GateLog in a current browser over HTTPS.");
      }
      const cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
      });
      setStream(cameraStream);
    } catch (error) {
      const messages = {
        NotAllowedError: "Camera access was blocked. Allow camera permission for cbvm.vercel.app in your browser.",
        NotFoundError: "No camera was found. Connect a webcam and try again.",
        NotReadableError: "The camera is busy in another app. Close that app and try again.",
      };
      setCameraError(messages[error.name] || error.message || "Could not start the camera.");
    } finally {
      setCameraPending(false);
    }
  }

  function stopCamera() {
    stream?.getTracks().forEach((track) => track.stop());
    setStream(null);
    setCameraReady(false);
  }

  async function captureAndRecord() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !vehicleId || !cameraReady) return;
    setPending(true);
    try {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      setCapturedFrame(canvas.toDataURL("image/jpeg", 0.82));
      const data = await api("/detections/mock", {
        method: "POST",
        body: { vehicle_id: vehicleId, direction },
      });
      notify(
        data.outcome === "review"
          ? `Sent to review: ${data.review.reason}`
          : data.outcome === "duplicate"
            ? "Repeated detection ignored; no new movement recorded."
            : `${data.detection.plate} · ${direction === "IN" ? "entry" : "exit"} recorded`,
      );
      refresh();
    } catch (error) {
      notify(error.message, true);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="demo-panel">
      <div className="demo-intro">
        <span className="eyebrow">LAPTOP CAMERA DEMO</span>
        <h3>Capture a gate scan</h3>
        <p>Allow camera access, frame the vehicle, and capture a still for the demo.</p>
      </div>
      <div className="demo-camera">
        {stream ? (
          <div className="demo-camera-preview">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              aria-label="Live laptop camera preview"
              onLoadedMetadata={() => setCameraReady(true)}
            />
            {capturedFrame ? <img src={capturedFrame} alt="Captured camera frame for this demo scan" /> : null}
          </div>
        ) : (
          <div className="demo-camera-placeholder">
            <Camera size={25} />
            <span>Your camera preview will appear here.</span>
          </div>
        )}
        <canvas ref={canvasRef} className="sr-only" aria-hidden="true" />
        {cameraError ? <p className="demo-camera-error" role="alert">{cameraError}</p> : null}
        <p className="demo-camera-note">The captured image stays in this browser and isn’t saved. The plate match is simulated from your vehicle registry; this demo does not perform OCR.</p>
      </div>
      <div className="demo-controls">
        <label className="sr-only" htmlFor="mock-vehicle">Registered vehicle</label>
        <select id="mock-vehicle" value={vehicleId} onChange={(event) => setVehicleId(event.target.value)}>
          <option value="">Select registered vehicle</option>
          {vehicles.map((vehicle) => (
            <option key={vehicle.id} value={vehicle.id}>
              {vehicle.number_plate} · {vehicle.owner_name}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="mock-direction">Direction</label>
        <select id="mock-direction" value={direction} onChange={(event) => setDirection(event.target.value)}>
          <option value="IN">Entry</option>
          <option value="OUT">Exit</option>
        </select>
        {!stream ? (
          <button className="button" onClick={startCamera} disabled={cameraPending}>
            <Camera size={17} />
            {cameraPending ? "Starting camera…" : "Enable laptop camera"}
          </button>
        ) : (
          <>
            <button className="button" onClick={captureAndRecord} disabled={pending || !cameraReady || !vehicleId}>
              <ScanLine size={17} />
              {pending ? "Recording…" : "Capture & record scan"}
            </button>
            <button className="button secondary" onClick={stopCamera} disabled={pending} aria-label="Turn camera off">
              <CameraOff size={17} /> Stop
            </button>
          </>
        )}
        {!vehicles.length ? <p className="demo-empty">Register an active vehicle first. It will appear here automatically.</p> : null}
      </div>
    </section>
  );
}
