import asyncio
import logging
from threading import Event

from app.ai.tracking import FrameTracker
from app.ai.video import video_source
from app.services.operations import utcnow

logger = logging.getLogger(__name__)


class CaptureWorker:
    """One source, one sampled frame at a time; retry live sources with capped backoff."""

    def __init__(self, state, loop, tracker=None, source_factory=None):
        self.state = state
        self.loop = loop
        self.stop_event = Event()
        self.tracker = tracker or FrameTracker()
        self.source_factory = source_factory
        self.health_status = "idle"
        self.last_frame_time = None
        self.source = state.settings.video_source

    def stop(self):
        self.stop_event.set()

    def emit(self, kind, value):
        asyncio.run_coroutine_threadsafe(self.state.hub.publish(kind, value), self.loop)

    def status(self, value, received_frame=False):
        previous = self.health_status
        changes = {"health_status": value, "source": self.source}
        if received_frame:
            self.last_frame_time = utcnow()
            changes["last_frame_time"] = self.last_frame_time
        self.state.db.cameras.update_one({"_id": self.state.settings.camera_id}, {"$set": changes})
        self.health_status = value
        self.emit("camera.status", {"id": self.state.settings.camera_id, **changes})
        if value == "offline" and previous != "offline":
            self.emit("camera.offline", {"id": self.state.settings.camera_id, **changes})
        elif previous == "offline" and received_frame:
            self.emit("camera.restored", {"id": self.state.settings.camera_id, **changes})

    def run(self):
        camera_id = self.state.settings.camera_id
        if not self.state.db.cameras.find_one({"_id": camera_id}):
            logger.error("Configured CAMERA_ID does not exist.")
            return
        retry_delay = min(30, max(0.01, self.state.settings.reconnect_delay_seconds))
        backoff = retry_delay
        while not self.stop_event.is_set():
            source = None
            try:
                source = (self.source_factory or video_source)(self.state.settings)
                while not self.stop_event.is_set():
                    frame = source.read()
                    self.status("mock" if self.source == "mock" else "online", received_frame=True)
                    backoff = retry_delay
                    detections = self.state.anpr.detect(frame)
                    camera = self.state.db.cameras.find_one({"_id": camera_id})
                    if camera is None:
                        raise RuntimeError("Configured camera was removed")
                    for detection in self.tracker.process(detections, camera, frame.shape):
                        storage = self.state.scan_storage
                        if storage.enabled:
                            object_key = storage.put_frame(frame, camera_id)
                            detection = detection.model_copy(update={"capture_key": object_key})
                        result = self.state.processor.process(detection, camera_id)
                        if result["outcome"] == "review":
                            self.emit("review.item", result["review"])
                        elif result["outcome"] == "accepted":
                            kind = "vehicle.entry" if result["log"]["status"] == "INSIDE" else "vehicle.exit"
                            self.emit(kind, result["log"])
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
                    try:
                        source.close()
                    except Exception:
                        logger.warning("Video source could not be closed cleanly.")
            if self.stop_event.wait(backoff):
                break
            backoff = min(backoff * 2, 30)
