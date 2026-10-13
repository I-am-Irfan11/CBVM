from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from app.api.auth import operator

router = APIRouter(prefix="/anpr", tags=["ANPR"])
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def readiness(settings):
    import importlib.util
    import shutil
    from pathlib import Path
    from app.core.config import ROOT
    path = Path(settings.yolo_model_path)
    path = path if path.is_absolute() else ROOT / path
    missing = []
    if not path.is_file():
        missing.append("Trained license-plate YOLO weights are missing. Set YOLO_MODEL_PATH to a local .pt file.")
    if importlib.util.find_spec("ultralytics") is None:
        missing.append("Python package ultralytics is not installed. Install backend/requirements-ai.txt in the backend environment.")
    if importlib.util.find_spec("pytesseract") is None:
        missing.append("Install pytesseract from backend/requirements-ai.txt for plate text recognition.")
    if not shutil.which("tesseract") and not Path("C:/Program Files/Tesseract-OCR/tesseract.exe").is_file():
        missing.append("Install Tesseract OCR and add it to PATH for whole-plate recognition.")
    message = (
        "Dependencies detected; recognition quality requires camera validation."
        if not missing else " ".join(missing)
    )
    message += " Whole-plate detections use OCR; character-only detections are decoded from their labels."
    return {"ready": not missing, "dependencies": missing, "message": message}


@router.get("/status")
def status(request: Request, user=Depends(operator)):
    return readiness(request.app.state.settings)


@router.post("/detect")
async def detect_image(request: Request, camera_id: str = Query(default="main-gate-in", max_length=80),
                       user=Depends(operator)):
    """Send raw JPEG/PNG bytes. Recognize, review or record using the camera direction."""
    if request.headers.get("content-type", "").split(";")[0] not in ("image/jpeg", "image/png"):
        raise HTTPException(415, "Send raw image/jpeg or image/png bytes")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image exceeds the 8 MiB upload limit")

    def recognize():
        import cv2
        import numpy as np

        camera = request.app.state.db.cameras.find_one({"_id": camera_id})
        if not camera or not camera.get("active", True):
            raise HTTPException(404, "Camera not found")
        if camera["direction"] == "BOTH":
            raise HTTPException(422, "Single-frame capture requires a dedicated IN or OUT camera. Use the continuous video worker for line-crossing direction.")
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR) if data else None
        if frame is None:
            raise HTTPException(422, "Unable to decode image")
        if frame.shape[0] * frame.shape[1] > 16000000:
            raise HTTPException(413, "Image exceeds 16 megapixels")
        try:
            from app.services.operations import utcnow
            request.app.state.db.cameras.update_one({"_id": camera_id}, {"$set": {"health_status": "online", "last_frame_time": utcnow()}})
            detections = request.app.state.image_anpr.detect(frame)
        except (ImportError, RuntimeError, OSError):
            raise HTTPException(
                503, "Real ANPR is not ready. " + readiness(request.app.state.settings)["message"]
            ) from None
        return detections

    detections = await run_in_threadpool(recognize)
    storage = request.app.state.scan_storage
    if detections and storage.enabled:
        try:
            object_key = await run_in_threadpool(
                storage.put, bytes(data), request.headers["content-type"].split(";")[0], camera_id
            )
        except Exception:
            raise HTTPException(503, "Scan storage is unavailable; no movement was recorded.") from None
        detections = [item.model_copy(update={"capture_key": object_key}) for item in detections]
    results = await run_in_threadpool(
        lambda: [request.app.state.processor.process(item, camera_id) for item in detections]
    )
    for result in results:
        if result["outcome"] == "accepted":
            kind = "vehicle.entry" if result["log"]["status"] == "INSIDE" else "vehicle.exit"
            await request.app.state.hub.publish(kind, result["log"])
        elif result["outcome"] == "review":
            await request.app.state.hub.publish("review.item", result["review"])
    if results:
        await request.app.state.hub.publish("camera.status", {"id": camera_id})
    return {"results": results, "mock_ai": False}


@router.get("/scans/{object_key:path}")
def scan_url(object_key: str, request: Request, user=Depends(operator)):
    if not object_key.startswith("scans/") or ".." in object_key.split("/"):
        raise HTTPException(404, "Scan not found")
    db = request.app.state.db
    referenced = db.vehicle_logs.find_one({"$or": [
        {"entry_detection.capture_key": object_key}, {"exit_detection.capture_key": object_key},
    ]}) or db.review_items.find_one({"capture_key": object_key})
    if not referenced:
        raise HTTPException(404, "Scan not found")
    try:
        url = request.app.state.scan_storage.signed_read_url(object_key)
    except Exception:
        raise HTTPException(503, "Scan storage is unavailable.") from None
    if not url:
        raise HTTPException(503, "Private scan storage is not configured.")
    return {"url": url, "expires_in": request.app.state.settings.r2_presigned_url_expiry_seconds}
