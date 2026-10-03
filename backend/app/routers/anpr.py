from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/anpr", tags=["ANPR"])
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@router.post("/detect")
async def detect_image(request: Request, camera_id: str = Query(default="main-gate-in", max_length=80)):
    """Send raw JPEG/PNG bytes. Recognize, review or record using the camera direction."""
    if request.headers.get("content-type", "").split(";")[0] not in ("image/jpeg", "image/png"):
        raise HTTPException(415, "Send raw image/jpeg or image/png bytes")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image exceeds the 8 MiB upload limit")

    def process():
        import cv2
        import numpy as np

        if not request.app.state.db.cameras.find_one({"_id": camera_id}):
            raise HTTPException(404, "Camera not found")
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR) if data else None
        if frame is None:
            raise HTTPException(422, "Unable to decode image")
        if frame.shape[0] * frame.shape[1] > 16000000:
            raise HTTPException(413, "Image exceeds 16 megapixels")
        try:
            detections = request.app.state.anpr.detect(frame)
        except (ImportError, RuntimeError, OSError):
            raise HTTPException(
                503, "Real ANPR is not ready. Check YOLO weights, AI dependencies and OCR installation."
            ) from None
        return [request.app.state.processor.process(item, camera_id) for item in detections]

    results = await run_in_threadpool(process)
    for result in results:
        if result["outcome"] == "accepted":
            kind = "vehicle.entry" if result["log"]["status"] == "INSIDE" else "vehicle.exit"
            await request.app.state.hub.publish(kind, result["log"])
        elif result["outcome"] == "review":
            await request.app.state.hub.publish("review.item", result["review"])
    if results:
        await request.app.state.hub.publish("camera.status", {"id": camera_id})
    return {"results": results, "mock_ai": request.app.state.settings.use_mock_ai}
