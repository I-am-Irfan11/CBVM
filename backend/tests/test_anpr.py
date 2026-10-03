import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ai.anpr import MockANPRService, OCRService, RealANPRService
from app.ai.video import MockVideoSource, OpenCVVideoSource
from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize("scenario", list(MockANPRService.scenarios))
def test_mock_scenarios(scenario):
    detection = MockANPRService().detect(scenario)[0]
    assert detection.raw_text
    assert 0 <= detection.confidence <= 1
    assert detection.timestamp.utcoffset() is not None
    assert detection.processing_time >= 0
    if scenario == "low_confidence":
        assert detection.confidence < 0.8
        assert not detection.valid


@pytest.mark.parametrize("scenario", ["student", "staff", "bus", "service"])
def test_mock_full_movement(client, scenario):
    result = client.post("/detections/mock", json={"scenario": scenario}).json()
    assert result["outcome"] == "accepted"
    assert client.post("/detections/mock", json={"scenario": scenario}).json()["outcome"] == "duplicate"
    assert (
        client.post("/detections/mock", json={"scenario": scenario, "direction": "OUT"}).json()["log"][
            "status"
        ]
        == "COMPLETED"
    )


@pytest.mark.parametrize("scenario", ["unknown", "low_confidence"])
def test_review_confidence_dedup_and_dismiss(client, scenario):
    first = client.post("/detections/mock", json={"scenario": scenario}).json()
    assert first["outcome"] == "review"
    second = client.post("/detections/mock", json={"scenario": scenario}).json()
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
                           json={"scenario": "student"}).status_code == 409


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


def test_image_endpoint_and_raw_evidence(client):
    import cv2

    encoded = cv2.imencode(".jpg", np.zeros((64, 100, 3), dtype=np.uint8))[1].tobytes()
    response = client.post("/anpr/detect", content=encoded, headers={"Content-Type": "image/jpeg"})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["outcome"] == "accepted"
    assert result["log"]["entry_detection"]["raw_text"] == "TN 09 AB 1234"
    assert (
        client.post("/anpr/detect", content=b"bad", headers={"Content-Type": "image/jpeg"}).status_code == 422
    )
    assert client.post("/anpr/detect", content=b"bad").status_code == 415


def test_confidence_threshold_with_valid_plate(app, client):
    detection = MockANPRService().detect("student")[0]
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
    monkeypatch.setattr(worker.stop_event, "wait", lambda seconds: worker.stop_event.is_set())

    class Source:
        def __init__(self, number):
            self.number = number

        def read(self):
            if self.number == 1:
                raise EOFError("Disconnected")
            worker.stop_event.set()
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
    assert app.state.db.vehicle_logs.count_documents({"status": "INSIDE"}) == 1
