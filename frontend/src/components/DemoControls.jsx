import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, ScanLine, SwitchCamera } from "lucide-react";
import { API_URL, api, getCsrfToken, readResponse } from "../services/api";

export default function DemoControls({ notify, refresh, mockAi = true }) {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleId, setVehicleId] = useState("");
  const [direction, setDirection] = useState("IN");
  const [facingMode, setFacingMode] = useState("environment");
  const mounted = useRef(true);
  const requestId = useRef(0);
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

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, []);

  async function startCamera(nextFacing = facingMode) {
    const id = ++requestId.current;
    stopCamera();
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
          facingMode: { ideal: nextFacing },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      if (!mounted.current || id !== requestId.current) {
        cameraStream.getTracks().forEach((track) => track.stop());
        return;
      }
      setFacingMode(nextFacing);
      setStream(cameraStream);
    } catch (error) {
      const messages = {
        NotAllowedError:
          "Camera access was blocked. Allow camera permission for this site in your browser settings.",
        NotFoundError:
          "No camera was found. Open this page on your phone or connect a webcam.",
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
    if (!video.videoWidth || !video.videoHeight) {
      throw new Error(
        "The camera is still getting ready. Try again in a moment.",
      );
    }
    const scale = Math.min(
      1,
      1920 / Math.max(video.videoWidth, video.videoHeight),
    );
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
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
      return "Needs confirmation. Your scan is saved in the review queue; confirm the plate there to record its movement.";
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
        const payload = await readResponse(response);
        if (!payload.results?.length) {
          setLastResults([
            "No plate detected. Move closer, keep the plate level and retry.",
          ]);
          notify(
            "No plate detected in this frame. Move closer and retry.",
            false,
          );
        } else {
          setLastResults(payload.results.map(describeOutcome));
          payload.results
            .filter((item) => item.outcome !== "review")
            .forEach((item) => notify(describeOutcome(item), false));
        }
      }
      refresh();
    } catch (error) {
      const message =
        error.status >= 500
          ? "We couldn’t finish this scan. Check Recent activity before retrying to see whether it was saved."
          : error instanceof TypeError
            ? "Connection interrupted. Check Recent activity before retrying your scan."
            : error.message;
      setLastResults([message]);
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
              aria-label="Live camera preview"
              onLoadedMetadata={() => setCameraReady(true)}
            />
            {capturedFrame ? (
              <img src={capturedFrame} alt="Last captured plate image" />
            ) : null}
          </div>
        ) : (
          <div className="demo-camera-placeholder">
            <Camera size={25} />
            <span>Use your phone camera or computer webcam.</span>
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
            : "Keep the full plate visible and steady. If a reading needs confirmation, you can complete it in the review queue."}
        </p>
        {!mockAi && readiness && !readiness.ready ? (
          <p className="recognition-status" role="status">
            Plate scanning is temporarily unavailable. Please try again shortly.
          </p>
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
          disabled={pending}
          onChange={(event) => setDirection(event.target.value)}
        >
          <option value="IN">Entry</option>
          <option value="OUT">Exit</option>
        </select>
        {!stream ? (
          <button
            className="button"
            onClick={() => startCamera()}
            disabled={cameraPending}
          >
            <Camera size={17} />
            {cameraPending ? "Starting camera…" : "Enable camera"}
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
              onClick={() =>
                startCamera(
                  facingMode === "environment" ? "user" : "environment",
                )
              }
              disabled={pending || cameraPending}
            >
              <SwitchCamera size={17} /> Switch camera
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
          {!mockAi &&
          lastResults.some((result) =>
            result.startsWith("Needs confirmation"),
          ) ? (
            <a className="text-button" href="#reviews">
              Open review queue
            </a>
          ) : null}
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
