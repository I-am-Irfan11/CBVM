import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, ScanLine } from "lucide-react";
import { API_URL, api, getCsrfToken } from "../services/api";

export default function DemoControls({ notify, refresh, mockAi = true }) {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleId, setVehicleId] = useState("");
  const [direction, setDirection] = useState("IN");
  const [stream, setStream] = useState(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraPending, setCameraPending] = useState(false);
  const [pending, setPending] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [capturedFrame, setCapturedFrame] = useState("");
  const [readiness, setReadiness] = useState(null);
  const [lastResults, setLastResults] = useState(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    let active = true;
    if (!mockAi) return undefined;
    api("/vehicles?limit=100")
      .then((data) => {
        if (!active) return;
        const activeVehicles = (data.items || []).filter(
          (vehicle) => vehicle.status === "active",
        );
        setVehicles(activeVehicles);
        setVehicleId((current) => current || activeVehicles[0]?.id || "");
      })
      .catch((error) => notify(error.message, true));
    return () => {
      active = false;
    };
  }, [notify, mockAi]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return undefined;
    video.srcObject = stream;
    video
      .play()
      .catch(() =>
        setCameraError("Allow camera access in your browser, then try again."),
      );
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  useEffect(
    () => () => stream?.getTracks().forEach((track) => track.stop()),
    [stream],
  );

  useEffect(() => {
    if (mockAi) return undefined;
    let active = true;
    api("/anpr/status")
      .then((data) => {
        if (active) setReadiness(data);
      })
      .catch((error) => {
        if (active)
          setReadiness({ ready: false, dependencies: [error.message] });
      });
    return () => {
      active = false;
    };
  }, [mockAi]);

  async function startCamera() {
    setCameraPending(true);
    setCameraError("");
    setCapturedFrame("");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "This browser does not provide camera access. Open GateLog in a current browser over HTTPS.",
        );
      }
      const cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      setStream(cameraStream);
    } catch (error) {
      const messages = {
        NotAllowedError:
          "Camera access was blocked. Allow camera permission for cbvm.vercel.app in your browser.",
        NotFoundError: "No camera was found. Connect a webcam and try again.",
        NotReadableError:
          "The camera is busy in another app. Close that app and try again.",
      };
      setCameraError(
        messages[error.name] || error.message || "Could not start the camera.",
      );
    } finally {
      setCameraPending(false);
    }
  }

  function stopCamera() {
    stream?.getTracks().forEach((track) => track.stop());
    setStream(null);
    setCameraReady(false);
  }

  function frameBlob() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    setCapturedFrame(canvas.toDataURL("image/jpeg", 0.82));
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) =>
          blob
            ? resolve(blob)
            : reject(new Error("Could not capture a frame.")),
        "image/jpeg",
        0.9,
      );
    });
  }

  function describeOutcome(data) {
    if (data.outcome === "review")
      return `Sent to review: ${data.review.reason}`;
    if (data.outcome === "duplicate")
      return "Repeated detection ignored; no new movement recorded.";
    return `${data.detection.plate} · ${direction === "IN" ? "entry" : "exit"} recorded`;
  }

  async function captureAndRecord() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !cameraReady) return;
    if (mockAi && !vehicleId) return;
    setPending(true);
    setLastResults(null);
    try {
      if (mockAi) {
        await frameBlob();
        const data = await api("/detections/mock", {
          method: "POST",
          body: { vehicle_id: vehicleId, direction },
        });
        notify(describeOutcome(data), false);
        setLastResults([describeOutcome(data)]);
      } else {
        const blob = await frameBlob();
        const response = await fetch(
          `${API_URL}/anpr/detect?camera_id=main-gate-${direction.toLowerCase()}`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "image/jpeg",
              "X-CSRF-Token": getCsrfToken(),
            },
            body: blob,
          },
        );
        const payload = await response.json();
        if (!response.ok)
          throw new Error(
            payload.detail || `Recognition failed (${response.status})`,
          );
        if (!payload.results?.length) {
          setLastResults([
            "No plate detected. Move closer, keep the plate level and retry.",
          ]);
          notify(
            "No plate detected in this frame. Move closer and retry.",
            true,
          );
        } else {
          setLastResults(payload.results.map(describeOutcome));
          payload.results.forEach((item) =>
            notify(describeOutcome(item), item.outcome === "review"),
          );
        }
      }
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
        <span className="eyebrow">
          {mockAi ? "SIMULATION" : "CAMERA CAPTURE"}
        </span>
        <h3>Capture a gate scan</h3>
        <p>
          Hold the plate level in good light. Capture a clear frame to check its
          reading.
        </p>
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
            {capturedFrame ? (
              <img
                src={capturedFrame}
                alt="Captured camera frame for this demo scan"
              />
            ) : null}
          </div>
        ) : (
          <div className="demo-camera-placeholder">
            <Camera size={25} />
            <span>Your camera preview will appear here.</span>
          </div>
        )}
        <canvas ref={canvasRef} className="sr-only" aria-hidden="true" />
        {cameraError ? (
          <p className="demo-camera-error" role="alert">
            {cameraError}
          </p>
        ) : null}
        <p className="demo-camera-note">
          {mockAi
            ? "The captured image stays in this browser and isn’t saved. The plate match is simulated from your vehicle registry; this demo does not perform OCR."
            : "The frame is sent to real YOLO plate detection plus OCR. Low-confidence or unknown plates land in the review queue."}
        </p>
        {!mockAi && readiness && !readiness.ready ? (
          <details className="recognition-status">
            <summary>Recognition needs setup · view details</summary>
            <p>{(readiness.dependencies || []).join(" ")}</p>
          </details>
        ) : null}
      </div>
      <div className="demo-controls">
        {mockAi ? (
          <>
            <label className="sr-only" htmlFor="mock-vehicle">
              Registered vehicle
            </label>
            <select
              id="mock-vehicle"
              value={vehicleId}
              onChange={(event) => setVehicleId(event.target.value)}
            >
              <option value="">Select registered vehicle</option>
              {vehicles.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicle.number_plate} · {vehicle.owner_name}
                </option>
              ))}
            </select>
          </>
        ) : null}
        <label htmlFor="mock-direction">Direction</label>
        <select
          id="mock-direction"
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
        >
          <option value="IN">Entry</option>
          <option value="OUT">Exit</option>
        </select>
        {!stream ? (
          <button
            className="button"
            onClick={startCamera}
            disabled={cameraPending}
          >
            <Camera size={17} />
            {cameraPending ? "Starting camera…" : "Enable laptop camera"}
          </button>
        ) : (
          <>
            <button
              className="button"
              onClick={captureAndRecord}
              disabled={
                pending ||
                !cameraReady ||
                (mockAi && !vehicleId) ||
                (!mockAi && !readiness?.ready)
              }
            >
              <ScanLine size={17} />
              {pending ? "Recording…" : "Capture & record scan"}
            </button>
            <button
              className="button secondary"
              onClick={stopCamera}
              disabled={pending}
              aria-label="Turn camera off"
            >
              <CameraOff size={17} /> Stop
            </button>
          </>
        )}
        {mockAi && !vehicles.length ? (
          <p className="demo-empty">
            Register an active vehicle first. It will appear here automatically.
          </p>
        ) : null}
      </div>
      {lastResults ? (
        <div className="scan-result" role="status">
          <strong>
            Last capture · {mockAi ? "simulated result" : "recognition result"}
          </strong>
          <ul>
            {lastResults.map((result, index) => (
              <li key={index}>{result}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
