import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ai.anpr import MockANPRService, OCRService, RealANPRService
from app.ai.video import MockVideoSource, OpenCVVideoSource
from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize("plate", ["TN 09 AB 1234", "TN07EF5678", "unreadable"])
def test_mock_requires_explicit_test_text(plate):
    detection = MockANPRService().detect(plate)[0]
    assert detection.raw_text
    assert 0 <= detection.confidence <= 1
    assert detection.timestamp.utcoffset() is not None
    assert detection.processing_time >= 0
    if plate == "unreadable":
        assert not detection.valid


def test_mock_never_invents_detection_from_camera_frame():
    assert MockANPRService().detect(np.zeros((64, 100, 3), dtype=np.uint8)) == []
    assert MockANPRService().detect() == []


def test_mock_full_movement(client, vehicle):
    payload = {"vehicle_id": vehicle["id"]}
    result = client.post("/detections/mock", json=payload).json()
    assert result["outcome"] == "accepted"
    assert client.post("/detections/mock", json=payload).json()["outcome"] == "duplicate"
    assert (
        client.post("/detections/mock", json={**payload, "direction": "OUT"}).json()["log"][
            "status"
        ]
        == "COMPLETED"
    )


@pytest.mark.parametrize("confidence", [0.43, 0.97])
def test_review_confidence_dedup_and_dismiss(app, client, confidence):
    detection = MockANPRService().detect("KA03ZZ9876")[0]
    detection.confidence = confidence
    first = app.state.processor.process(detection, "main-gate-in")
    assert first["outcome"] == "review"
    second = app.state.processor.process(detection, "main-gate-in")
    assert second["review"]["id"] == first["review"]["id"]
    assert second["review"]["sightings"] == 2
    assert client.get("/vehicles/inside").json()["total"] == 0
    assert client.get("/reviews").json()["total"] == 1
    assert client.post(f"/reviews/{first['review']['id']}/dismiss").status_code == 200
    assert client.get("/reviews").json()["total"] == 0


def test_real_mode_lazy_and_mock_disabled():
    from datetime import datetime, timezone
    from app.services.auth import password_hash

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_mode="memory",
            use_mock_ai=False,
            run_video_worker=False,
            seed_on_startup=True,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        app.state.db.users.insert_one({"_id": "test-admin", "username": "admin", "email": "admin@test.local",
            "full_name": "Test Admin", "role": "admin", "active": True,
            "password_hash": password_hash("TestOnly-password-123!"), "created_at": datetime.now(timezone.utc)})
        token = app.state.auth.login("admin", "TestOnly-password-123!", "test")["access_token"]
        assert client.post("/detections/mock", headers={"Authorization": f"Bearer {token}"},
                           json={"vehicle_id": "not-used"}).status_code == 409


def test_mock_video():
    source = MockVideoSource()
    assert source.read().shape == (360, 640, 3)
    source.close()


def test_real_pipeline_with_injected_detector_and_ocr():
    class OCR(OCRService):
        def read(self, image):
            assert len(image.shape) == 2
            return "TN 09 AB 1234", 0.91

    class Box:
        xyxy = np.array([[-10, 10, 80, 50]])
        conf = [0.95]

    class Result:
        boxes = [Box()]

    class Detector:
        def predict(self, frame, verbose=False):
            return [Result()]

    service = RealANPRService(Settings(_env_file=None), ocr=OCR())
    service.model = Detector()
    result = service.detect(np.zeros((100, 100, 3), dtype=np.uint8))[0]
    assert result.plate == "TN09AB1234"
    assert result.raw_text == "TN 09 AB 1234"
    assert result.confidence == 0.91
    assert result.bounding_box == (0, 10, 80, 50)


def test_opencv_file_source(tmp_path):
    import cv2

    path = str(tmp_path / "sample.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 5, (64, 48))
    assert writer.isOpened()
    writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()
    source = OpenCVVideoSource(path)
    try:
        assert source.read().shape == (48, 64, 3)
        with pytest.raises(EOFError):
            source.read()
    finally:
        source.close()


def test_image_endpoint_and_raw_evidence(app, client, vehicle):
    import cv2

    class ImageRecognizer:
        def detect(self, frame):
            assert frame.shape == (64, 100, 3)
            return MockANPRService().detect(vehicle["number_plate"])

    app.state.image_anpr = ImageRecognizer()
    encoded = cv2.imencode(".jpg", np.zeros((64, 100, 3), dtype=np.uint8))[1].tobytes()
    response = client.post("/anpr/detect", content=encoded, headers={"Content-Type": "image/jpeg"})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["outcome"] == "accepted"
    assert result["log"]["entry_detection"]["raw_text"] == vehicle["number_plate"]
    assert response.json()["mock_ai"] is False
    assert (
        client.post("/anpr/detect", content=b"bad", headers={"Content-Type": "image/jpeg"}).status_code == 422
    )
    assert client.post("/anpr/detect", content=b"bad").status_code == 415


def test_image_endpoint_returns_readable_error_when_recognition_crashes(app, client):
    import cv2

    class BrokenRecognizer:
        def detect(self, frame):
            raise ValueError("recognizer failure")

    app.state.image_anpr = BrokenRecognizer()
    encoded = cv2.imencode(".jpg", np.zeros((64, 100, 3), dtype=np.uint8))[1].tobytes()
    response = client.post("/anpr/detect", content=encoded, headers={"Content-Type": "image/jpeg"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Plate recognition failed for this image. Please retry the scan."


def test_confidence_threshold_with_valid_plate(app, client):
    detection = MockANPRService().detect("TN09AB1234")[0]
    detection.confidence = 0.79
    result = app.state.processor.process(detection, "main-gate-in")
    assert result["outcome"] == "review"
    assert app.state.db.vehicle_logs.count_documents({}) == 0


def test_capture_reconnects_after_source_failure(app, client, monkeypatch):
    from app.services.capture import CaptureWorker

    app.state.settings.video_source = "rtsp"
    worker = CaptureWorker(app.state, None)
    events, opened, closed = [], [], []
    worker.emit = lambda kind, value: events.append((kind, value))
    def wait(seconds):
        if worker.last_frame_time is not None:
            worker.stop()
        return worker.stop_event.is_set()
    monkeypatch.setattr(worker.stop_event, "wait", wait)

    class Recognizer:
        def detect(self, frame):
            return MockANPRService().detect("TN09AB1234")
    app.state.anpr = Recognizer()

    class Source:
        def __init__(self, number):
            self.number = number

        def read(self):
            if self.number == 1:
                raise EOFError("Disconnected")
            return np.zeros((64, 100, 3), dtype=np.uint8)

        def close(self):
            closed.append(self.number)

    def factory(settings):
        opened.append(len(opened) + 1)
        return Source(opened[-1])

    monkeypatch.setattr("app.services.capture.video_source", factory)
    worker.run()
    assert opened == [1, 2]
    assert closed == [1, 2]
    assert any(data.get("health_status") == "offline" for _, data in events)
    assert [kind for kind, _ in events].count("camera.offline") == 1
    assert [kind for kind, _ in events].count("camera.restored") == 1
    assert worker.health_status == "online"
    assert app.state.db.vehicle_logs.count_documents({"status": "INSIDE"}) == 1


def test_real_image_endpoint_unavailable_model_never_uses_mock(app, client, tmp_path):
    import cv2

    assert isinstance(app.state.image_anpr, RealANPRService)
    app.state.image_anpr.path = tmp_path / "missing.pt"
    encoded = cv2.imencode(".jpg", np.zeros((64, 100, 3), dtype=np.uint8))[1].tobytes()
    response = client.post("/anpr/detect", content=encoded, headers={"Content-Type": "image/jpeg"})
    assert response.status_code == 503
    assert "Real ANPR" in response.json()["detail"]
    assert app.state.db.vehicle_logs.count_documents({}) == 0


def test_single_image_rejects_both_direction(app, client):
    app.state.db.cameras.update_one({"_id": "main-gate-in"}, {"$set": {"direction": "BOTH"}})
    response = client.post("/anpr/detect", content=b"unused", headers={"Content-Type": "image/jpeg"})
    assert response.status_code == 422
    assert "Single-frame" in response.json()["detail"]
