from types import SimpleNamespace

import mongomock
import numpy as np
import pytest

from app.ai.anpr import MockANPRService
from app.ai.tracking import CentroidIoUTracker, FrameTracker
from app.services.capture import CaptureWorker


def detection(y, x=50, plate="TN09AB1234"):
    return MockANPRService().detect(plate)[0].model_copy(update={
        "bounding_box": (x - 5, y - 5, x + 5, y + 5)})


def camera(**overrides):
    return {"_id": "gate", "direction": "BOTH", "gate_line": [0.1, 0.5, 0.9, 0.5],
            "inward_sign": 1, "minimum_movement": 0.03, **overrides}


@pytest.mark.parametrize("sign,expected", [(1, ["IN", "OUT"]), (-1, ["OUT", "IN"])])
def test_crossings_have_stable_ids_and_one_event_each(sign, expected):
    tracker = FrameTracker()
    events = []
    for y in (40, 45, 49, 51, 55, 58, 56, 51, 49, 45, 40):
        events.extend(tracker.process([detection(y)], camera(inward_sign=sign), (100, 100)))
    assert [event.direction for event in events] == expected
    assert len({event.tracking_id for event in events}) == 1
    assert all(event.camera_id == "gate" for event in events)


def test_jitter_and_first_appearance_never_cross():
    tracker = FrameTracker()
    for y in (50, 49, 51, 49, 51, 55, 56):
        assert tracker.process([detection(y)], camera(), (100, 100)) == []


def test_expiry_camera_isolation_and_ocr_changes():
    now = [0.0]
    tracker = FrameTracker(CentroidIoUTracker(clock=lambda: now[0]))
    first = tracker.process([detection(40)], camera(direction="IN"), (100, 100))[0]
    repeated = tracker.process([detection(41, plate="unreadable")], camera(direction="IN"), (100, 100))[0]
    other = tracker.process([detection(41)], camera(_id="other", direction="OUT"), (100, 100))[0]
    assert first.tracking_id == repeated.tracking_id
    assert other.tracking_id != first.tracking_id
    assert other.direction == "OUT"
    now[0] = 3
    assert tracker.process([detection(55)], camera(), (100, 100)) == []
    after_expiry = tracker.process([detection(56)], camera(direction="IN"), (100, 100))[0]
    assert after_expiry.tracking_id != first.tracking_id


def test_crossing_outside_finite_line_is_not_event():
    tracker = FrameTracker()
    for y in (40, 45, 55, 60):
        assert tracker.process([detection(y, x=95)], camera(), (100, 100)) == []


def test_tracker_bounds_state_and_one_to_one_assignments():
    tracker = CentroidIoUTracker(max_tracks=2, max_cameras=2)
    rows = [detection(30, 20), detection(30, 70), detection(70, 40)]
    first = tracker.update(rows, "one", (100, 100))
    assert len(first) == len({track.id for _, track in first}) == 2
    reversed_rows = tracker.update(list(reversed(rows[:2])), "one", (100, 100))
    assert first[0][1].id == reversed_rows[1][1].id
    for name in ("two", "three"):
        tracker.update(rows, name, (100, 100))
    assert len(tracker.cameras) == 2
    assert all(len(tracks) <= 2 for tracks in tracker.cameras.values())


def worker_state():
    db = mongomock.MongoClient().test
    db.cameras.insert_one(camera(direction="IN"))
    return SimpleNamespace(db=db, settings=SimpleNamespace(camera_id="gate", video_source="rtsp",
        reconnect_delay_seconds=1, frame_sample_rate=2), scan_storage=SimpleNamespace(enabled=False))


def test_capture_retry_is_capped_and_stoppable():
    state = worker_state()
    def fail(settings):
        raise OSError("private source details")
    worker = CaptureWorker(state, None, source_factory=fail)
    events, waits = [], []
    worker.emit = lambda kind, value: events.append(kind)
    def wait(seconds):
        waits.append(seconds)
        if len(waits) == 7:
            worker.stop()
        return worker.stop_event.is_set()
    worker.stop_event.wait = wait
    worker.run()
    assert waits == [1, 2, 4, 8, 16, 30, 30]
    assert events.count("camera.offline") == 1
    assert "camera.restored" not in events
    assert state.db.cameras.find_one()["source"] == "rtsp"


def test_stop_during_read_does_not_process_frame():
    state = worker_state()
    closed = []
    class Source:
        def read(self):
            worker.stop()
            return np.zeros((100, 100, 3), dtype=np.uint8)
        def close(self):
            closed.append(True)
    worker = CaptureWorker(state, None, source_factory=lambda settings: Source())
    worker.emit = lambda kind, value: pytest.fail("Stopped frame must not be processed")
    worker.run()
    assert closed == [True]
    assert worker.last_frame_time is None


def test_processing_error_does_not_claim_camera_disconnected():
    state = worker_state()
    class Recognizer:
        def detect(self, frame):
            worker.stop()
            raise RuntimeError("missing YOLO weights")
    class Source:
        def read(self):
            return np.zeros((100, 100, 3), dtype=np.uint8)
        def close(self):
            pass
    state.anpr = Recognizer()
    worker = CaptureWorker(state, None, source_factory=lambda settings: Source())
    events = []
    worker.emit = lambda kind, value: events.append(kind)
    worker.run()
    assert "camera.processing_error" in events
    assert "camera.offline" not in events
    assert worker.health_status == "online"


def test_capture_forwards_only_crossings_with_direction():
    state = worker_state()
    state.db.cameras.update_one({"_id": "gate"}, {"$set": {"direction": "BOTH"}})
    positions = iter((40, 45, 55, 60))
    state.anpr = SimpleNamespace(detect=lambda frame: [detection(next(positions))])
    received = []
    def process(item, camera_id):
        received.append((item, camera_id))
        return {"outcome": "duplicate"}
    state.processor = SimpleNamespace(process=process)
    worker = CaptureWorker(state, None)
    for _ in range(4):
        worker.process_frame(np.zeros((100, 100, 3)), "gate")
    assert len(received) == 1
    assert received[0][0].direction == "IN"
    assert received[0][0].tracking_id
