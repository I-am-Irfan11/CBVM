import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, ScanLine, SwitchCamera } from "lucide-react";
import { API_URL, api, getCsrfToken, readResponse } from "../services/api";

export default function DemoControls({
  notify,
  refresh,
  navigate,
  mockAi = true,
}) {
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
  const [autoScanEnabled, setAutoScanEnabled] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [capturedFrame, setCapturedFrame] = useState("");
  const [readiness, setReadiness] = useState(null);
  const [lastResults, setLastResults] = useState(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const scanningRef = useRef(false);
  const captureRef = useRef(null);

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
    setAutoScanEnabled(false);
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
    setAutoScanEnabled(false);
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
      return `${data.detection.plate || "Unreadable plate"} · Added to the review queue. You can scan another plate now and confirm queued readings later.`;
    if (data.outcome === "duplicate")
      return "Repeated detection ignored; no new movement recorded.";
    return `${data.detection.plate} · ${direction === "IN" ? "entry" : "exit"} recorded`;
  }

  async function captureAndRecord({ manual = false } = {}) {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !cameraReady) return;
    if (mockAi && !vehicleId) return;
    setPending(true);
    try {
      if (mockAi) {
        await frameBlob();
        const data = await api("/detections/mock", {
          method: "POST",
          body: { vehicle_id: vehicleId, direction },
        });
        notify(describeOutcome(data), false);
        setLastResults([describeOutcome(data)]);
        setCapturedFrame(canvas.toDataURL("image/jpeg", 0.82));
        refresh();
        return true;
      } else {
        const blob = await frameBlob();
        if (manual) {
          setCapturedFrame(canvas.toDataURL("image/jpeg", 0.82));
          setLastResults(["Photo captured. Reading the plate with OCR…"]);
        }
        const response = await fetch(
          `${API_URL}/anpr/detect?camera_id=main-gate-${direction.toLowerCase()}&manual_capture=${manual}`,
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
          if (manual) {
            setCapturedFrame(canvas.toDataURL("image/jpeg", 0.82));
            setLastResults([
              "No plate was recognized in this frame. Move closer, improve the light, keep the plate level, then capture again.",
            ]);
          }
          return false;
        } else {
          setCapturedFrame(canvas.toDataURL("image/jpeg", 0.82));
          setLastResults(payload.results.map(describeOutcome));
          payload.results
            .filter((item) => item.outcome === "accepted")
            .forEach((item) => notify(describeOutcome(item), false));
          refresh();
          return false;
        }
      }
    } catch (error) {
      let pendingReviews = 0;
      if (!mockAi) {
        try {
          const reviews = await api("/reviews?limit=25&offset=0");
          pendingReviews = reviews.total || 0;
        } catch {
          // Keep the capture screen usable if the review count cannot be checked.
        }
        refresh();
      }
      const message = pendingReviews
        ? `The scan response was interrupted. ${pendingReviews} reading${pendingReviews === 1 ? " is" : "s are"} awaiting review; check the queue if needed. You can capture another plate.`
        : error.status >= 500
          ? "We couldn’t confirm the scan result. Check the review queue before trying again."
          : error instanceof TypeError
            ? "Connection interrupted. Check the review queue before trying again."
            : error.message;
      setLastResults([message]);
      refresh();
      return true;
    } finally {
      setPending(false);
    }
  }

  captureRef.current = captureAndRecord;

  async function capturePlateNow() {
    if (scanningRef.current || pending || !cameraReady || mockAi) return;
    scanningRef.current = true;
    setAutoScanEnabled(false);
    try {
      const shouldPause = await captureAndRecord({ manual: true });
      if (!shouldPause) setAutoScanEnabled(true);
    } finally {
      scanningRef.current = false;
    }
  }

  useEffect(() => {
    if (
      !stream ||
      !cameraReady ||
      !autoScanEnabled ||
      (!mockAi && !readiness?.ready) ||
      (mockAi && !vehicleId)
    ) {
      return undefined;
    }
    let cancelled = false;
    let timer;
    const scan = async () => {
      if (cancelled) return;
      if (scanningRef.current) {
        timer = window.setTimeout(scan, 1400);
        return;
      }
      scanningRef.current = true;
      try {
        const shouldPause = await captureRef.current?.();
        if (shouldPause) setAutoScanEnabled(false);
      } finally {
        scanningRef.current = false;
        if (!cancelled && autoScanEnabled) {
          timer = window.setTimeout(scan, 1400);
        }
      }
    };
    timer = window.setTimeout(scan, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    stream,
    cameraReady,
    autoScanEnabled,
    mockAi,
    readiness?.ready,
    vehicleId,
  ]);

  return (
    <section className="demo-panel">
      <div className="demo-intro">
        <span className="eyebrow">
          {mockAi ? "SIMULATION" : "CAMERA CAPTURE"}
        </span>
        <h3>Capture a gate scan</h3>
        <p>
          Enable the camera and hold the plate level in view. GateLog scans
          automatically. Keep scanning more plates and confirm queued readings
          later.
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
              onLoadedMetadata={() => {
                setCameraReady(true);
                setLastResults(null);
                setAutoScanEnabled(true);
              }}
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
        {stream ? (
          <p className="scanner-status" role="status">
            {!mockAi && !readiness?.ready
              ? "Plate recognition is unavailable. Check the service setup before scanning."
              : pending
                ? "Checking the camera frame…"
                : autoScanEnabled
                  ? mockAi
                    ? vehicleId
                      ? "Demo scan will record automatically when ready."
                      : "Select a registered vehicle to start the demo scan."
                    : "Scanning automatically. Show the next plate whenever you’re ready."
                  : lastResults
                    ? "Automatic scanning is paused. You can capture a plate or resume scanning."
                    : "Camera ready. Automatic scanning will start shortly."}
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
            {!mockAi ? (
              <button
                className="button"
                onClick={capturePlateNow}
                disabled={pending || !cameraReady || !readiness?.ready}
                title="Take a photo and read its number plate with OCR"
              >
                <ScanLine size={17} />
                Capture photo & read plate
              </button>
            ) : null}
            {!autoScanEnabled && lastResults ? (
              <button
                className="button"
                onClick={() => {
                  setLastResults(null);
                  setAutoScanEnabled(true);
                }}
                disabled={
                  !cameraReady ||
                  (mockAi && !vehicleId) ||
                  (!mockAi && !readiness?.ready)
                }
              >
                <ScanLine size={17} /> Resume automatic scanning
              </button>
            ) : null}
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
          {!mockAi ? (
            <button
              className="text-button scan-review-link"
              type="button"
              onClick={() =>
                navigate
                  ? navigate("reviews")
                  : (window.location.hash = "reviews")
              }
            >
              Open review queue
            </button>
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
