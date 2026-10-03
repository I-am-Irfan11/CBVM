import asyncio
import logging
from threading import Event

from app.ai.video import video_source
from app.services.operations import utcnow

logger = logging.getLogger(__name__)


class CaptureWorker:
    """One source, one sampled frame at a time; retry live sources with capped backoff."""

    def __init__(self, state, loop):
        self.state = state
        self.loop = loop
        self.stop_event = Event()

    def emit(self, kind, value):
        asyncio.run_coroutine_threadsafe(self.state.hub.publish(kind, value), self.loop)

    def status(self, value, received_frame=False):
        changes = {"health_status": value}
        if received_frame:
            changes["last_frame_time"] = utcnow()
        self.state.db.cameras.update_one({"_id": self.state.settings.camera_id}, {"$set": changes})
        self.emit("camera.status", {"id": self.state.settings.camera_id, **changes})

    def run(self):
        camera_id = self.state.settings.camera_id
        if not self.state.db.cameras.find_one({"_id": camera_id}):
            logger.error("Configured CAMERA_ID does not exist.")
            return
        backoff = 1
        while not self.stop_event.is_set():
            source = None
            try:
                source = video_source(self.state.settings)
                while not self.stop_event.is_set():
                    frame = source.read()
                    detections = self.state.anpr.detect(frame)
                    for detection in detections:
                        result = self.state.processor.process(detection, camera_id)
                        if result["outcome"] == "review":
                            self.emit("review.item", result["review"])
                        elif result["outcome"] == "accepted":
                            kind = "vehicle.entry" if result["log"]["status"] == "INSIDE" else "vehicle.exit"
                            self.emit(kind, result["log"])
                    self.status("mock" if self.state.settings.use_mock_ai else "online", received_frame=True)
                    backoff = 1
                    self.stop_event.wait(1 / self.state.settings.frame_sample_rate)
            except Exception:
                # Never log RTSP URLs or their embedded credentials.
                logger.error("Capture interrupted. Check source, model, OCR and database configuration.")
                try:
                    self.status("offline")
                except Exception:
                    logger.error("Camera health could not be persisted.")
                if self.state.settings.video_source not in ("rtsp", "webcam"):
                    break
            finally:
                if source:
                    source.close()
            if self.stop_event.wait(backoff):
                break
            backoff = min(backoff * 2, 30)
