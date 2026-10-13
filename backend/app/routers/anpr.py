import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from app.api.auth import operator

router = APIRouter(prefix="/anpr", tags=["ANPR"])
MAX_IMAGE_BYTES = 8 * 1024 * 1024
logger = logging.getLogger(__name__)


def readiness(settings):
    import importlib.util
    from pathlib import Path
    from app.core.config import resolve_model_path
    path = resolve_model_path(settings.yolo_model_path)
    missing = []
    if not path.is_file():
        missing.append("Trained plate model is missing. Set YOLO_MODEL_PATH to the model file.")
    if path.suffix.lower() == ".onnx":
        if importlib.util.find_spec("onnxruntime") is None:
            missing.append("ONNX Runtime is not installed. Install backend/requirements.txt.")
    else:
        if importlib.util.find_spec("ultralytics") is None:
            missing.append("Python package ultralytics is not installed. Install backend/requirements-ai.txt in the backend environment.")
    if importlib.util.find_spec("rapidocr_onnxruntime") is None:
        missing.append("RapidOCR is not installed. Install backend/requirements.txt.")
    message = (
        "Dependencies detected; recognition quality requires camera validation."
        if not missing else " ".join(missing)
    )
    message += " Character detections are assembled into plate text; whole-plate detections use the bundled OCR engine."
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
        except Exception:
            logger.exception("Unexpected error during plate recognition")
            raise HTTPException(503, "Plate recognition failed for this image. Please retry the scan.") from None
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
    try:
        results = await run_in_threadpool(
            lambda: [request.app.state.processor.process(item, camera_id) for item in detections]
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process plate scan results")
        raise HTTPException(500, "The scan could not be recorded. Please retry.") from None
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
