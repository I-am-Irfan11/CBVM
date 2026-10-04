"""Bounded geometric tracking. OCR text never determines motion or identity."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import hypot
from time import monotonic
from uuid import uuid4

from app.ai.anpr import Detection


@dataclass
class Track:
    id: str
    box: tuple[float, float, float, float]
    seen: float
    side: int = 0
    anchor: tuple[float, float] | None = None

    @property
    def center(self):
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2, (y1 + y2) / 2)


class Tracker(ABC):
    @abstractmethod
    def update(self, detections, camera_id, frame_shape) -> list[tuple[Detection, Track]]:
        """Return detections associated with mutable, camera-local track state."""


class CentroidIoUTracker(Tracker):
    def __init__(self, *, expiry_seconds=2.0, max_tracks=128, max_cameras=32,
                 max_distance=0.25, clock=monotonic):
        if min(expiry_seconds, max_tracks, max_cameras, max_distance) <= 0:
            raise ValueError("Tracker limits must be positive")
        self.expiry_seconds = expiry_seconds
        self.max_tracks = max_tracks
        self.max_cameras = max_cameras
        self.max_distance = max_distance
        self.clock = clock
        self.cameras = {}

    @staticmethod
    def iou(a, b):
        intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
            0, min(a[3], b[3]) - max(a[1], b[1]))
        def area(box):
            return max(0, box[2] - box[0]) * max(0, box[3] - box[1])
        union = area(a) + area(b) - intersection
        return intersection / union if union else 0

    def update(self, detections, camera_id, frame_shape):
        height, width = frame_shape[:2]
        if height <= 0 or width <= 0:
            raise ValueError("Frame dimensions must be positive")
        now = self.clock()
        for key, tracks in list(self.cameras.items()):
            tracks[:] = [t for t in tracks if now - t.seen < self.expiry_seconds]
            if not tracks:
                del self.cameras[key]
        if camera_id not in self.cameras and len(self.cameras) >= self.max_cameras:
            oldest = min(self.cameras, key=lambda key: max(t.seen for t in self.cameras[key]))
            del self.cameras[oldest]
        tracks = self.cameras.setdefault(camera_id, [])
        boxes = [(d.bounding_box[0] / width, d.bounding_box[1] / height,
                  d.bounding_box[2] / width, d.bounding_box[3] / height)
                 for d in detections[:self.max_tracks]]
        pairs = []
        for index, box in enumerate(boxes):
            center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            for track_index, track in enumerate(tracks):
                distance = hypot(center[0] - track.center[0], center[1] - track.center[1])
                overlap = self.iou(box, track.box)
                if distance <= self.max_distance:
                    pairs.append((distance + (1 - overlap) * 0.1, index, track_index))
        matches, used = {}, set()
        for _, index, track_index in sorted(pairs):
            if index not in matches and track_index not in used:
                matches[index] = tracks[track_index]
                used.add(track_index)
        result = []
        for index, box in enumerate(boxes):
            track = matches.get(index)
            if track is None:
                track = Track(uuid4().hex, box, now)
                tracks.append(track)
            track.box, track.seen = box, now
            result.append((detections[index], track))
        # Keep current matches first, then the most recently seen inactive tracks.
        current = {track.id for _, track in result}
        tracks.sort(key=lambda track: (track.id in current, track.seen), reverse=True)
        del tracks[self.max_tracks:]
        return result


class FrameTracker:
    def __init__(self, tracker: Tracker | None = None):
        self.tracker = tracker or CentroidIoUTracker()

    def process(self, detections, camera, frame_shape):
        camera_id = str(camera.get("_id") or camera.get("id"))
        direction = camera.get("direction", "IN")
        line = camera.get("gate_line", [0.1, 0.5, 0.9, 0.5])
        x1, y1, x2, y2 = line
        dx, dy = x2 - x1, y2 - y1
        length = hypot(dx, dy)
        minimum = camera.get("minimum_movement", 0.03)
        inward_sign = camera.get("inward_sign", 1)
        if (direction not in ("IN", "OUT", "BOTH") or not length
                or any(not 0 <= value <= 1 for value in line)
                or minimum <= 0 or inward_sign not in (-1, 1)):
            raise ValueError("Invalid camera tracking configuration")
        result = []
        for detection, track in self.tracker.update(detections, camera_id, frame_shape):
            candidate = detection.model_copy(update={"tracking_id": track.id,
                                                     "camera_id": camera_id, "direction": None})
            if direction in ("IN", "OUT"):
                result.append(candidate.model_copy(update={"direction": direction}))
                continue
            center = track.center
            distance = (dx * (center[1] - y1) - dy * (center[0] - x1)) / length
            # A dead band keeps noise near the line from arming or crossing a track.
            side = 1 if distance >= minimum / 2 else -1 if distance <= -minimum / 2 else 0
            if not side:
                continue
            if not track.side:
                track.side, track.anchor = side, center
                continue
            if side == track.side:
                track.anchor = center
                continue
            anchor = track.anchor
            old_distance = (dx * (anchor[1] - y1) - dy * (anchor[0] - x1)) / length
            if abs(distance - old_distance) < minimum:
                continue
            fraction = old_distance / (old_distance - distance)
            crossing = (anchor[0] + fraction * (center[0] - anchor[0]),
                        anchor[1] + fraction * (center[1] - anchor[1]))
            projection = ((crossing[0] - x1) * dx + (crossing[1] - y1) * dy) / length ** 2
            track.side, track.anchor = side, center
            if 0 <= projection <= 1:
                result.append(candidate.model_copy(update={
                    "direction": "IN" if side == inward_sign else "OUT"}))
        return result
