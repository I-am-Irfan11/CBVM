from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import re
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import ROOT
from app.core.plates import normalize_plate, valid_plate


class Detection(BaseModel):
    plate: str
    raw_text: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: tuple[int, int, int, int]
    valid: bool
    processing_time: float  # milliseconds
    timestamp: datetime
    tracking_id: str | None = None
    camera_id: str | None = None
    direction: Literal["IN", "OUT"] | None = None
    capture_key: str | None = None


class ANPRService(ABC):
    @abstractmethod
    def detect(self, frame) -> list[Detection]: ...


class OCRService(ABC):
    @abstractmethod
    def read(self, image) -> tuple[str, float]: ...


class MockANPRService(ANPRService):
    def detect(self, frame=None):
        started = perf_counter()
        if not isinstance(frame, str) or not frame.strip():
            return []
        raw, confidence = frame.strip(), 0.97
        plate = normalize_plate(raw)
        return [
            Detection(
                plate=plate,
                raw_text=raw,
                confidence=confidence,
                bounding_box=(180, 180, 420, 260),
                valid=valid_plate(plate),
                processing_time=(perf_counter() - started) * 1000,
                timestamp=datetime.now(timezone.utc),
            )
        ]


class TesseractOCR(OCRService):
    def read(self, image):
        import pytesseract
        import shutil

        if not shutil.which("tesseract"):
            windows_install = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
            if windows_install.is_file():
                pytesseract.pytesseract.tesseract_cmd = str(windows_install)

        result = pytesseract.image_to_data(image, config="--psm 7", output_type=pytesseract.Output.DICT)
        words = [
            (text, float(conf))
            for text, conf in zip(result["text"], result["conf"])
            if text.strip() and float(conf) >= 0
        ]
        if not words:
            return "", 0.0
        return " ".join(text for text, _ in words), sum(conf for _, conf in words) / (100 * len(words))


class RealANPRService(ANPRService):
    def __init__(self, settings, ocr: OCRService | None = None):
        self.path = Path(settings.yolo_model_path)
        if not self.path.is_absolute():
            self.path = ROOT / self.path
        self.ocr = ocr or TesseractOCR()
        self.model = None

    def detect(self, frame):
        import cv2

        # Lazy load: real mode can start without a camera or model file.
        if self.model is None:
            if not self.path.is_file():
                raise RuntimeError("License-plate YOLO weights are missing; configure YOLO_MODEL_PATH")
            from ultralytics import YOLO

            self.model = YOLO(str(self.path))
        names = getattr(self.model, "names", {})
        names = names.values() if isinstance(names, dict) else names
        self.character_labels = {str(name).strip().upper() for name in names}
        self.character_mode = len(self.character_labels.intersection(set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"))) >= 20
        if frame is None or frame.size == 0:
            return []
        started = perf_counter()
        rows = []
        height, width = frame.shape[:2]
        for result in self.model.predict(frame, verbose=False):
            plate_boxes = []
            if self.character_mode:
                plate_boxes = [box for box in result.boxes
                               if str(self.model.names[int(box.cls[0])]).lower()
                               in {"indian_registered", "non_registered", "license_plate", "licence_plate", "plate"}]
                if not plate_boxes:
                    rows.extend(self._read_character_boxes(result, width, height, started))
                    continue
            else:
                plate_boxes = result.boxes
            for box in plate_boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                x1, x2 = max(0, x1), min(width, x2)
                y1, y2 = max(0, y1), min(height, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                crop = cv2.resize(crop, None, fx=2, fy=2)
                crop = cv2.bilateralFilter(crop, 9, 75, 75)
                crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                raw, ocr_confidence = self.ocr.read(crop)
                # Keep the original OCR text for review; punctuation is not part of a plate.
                plate = re.sub(r"[^A-Z0-9]", "", raw.upper())
                confidence = min(float(box.conf[0]), max(0.0, min(1.0, ocr_confidence)))
                rows.append(
                    Detection(
                        plate=plate,
                        raw_text=raw,
                        confidence=confidence,
                        bounding_box=(x1, y1, x2, y2),
                        valid=valid_plate(plate),
                        processing_time=(perf_counter() - started) * 1000,
                        timestamp=datetime.now(timezone.utc),
                    )
                )
        return rows

    def _read_character_boxes(self, result, width, height, started):
        """Decode the Roboflow character-box dataset by reading boxes in plate order."""
        names = result.names
        characters = []
        for box in result.boxes:
            class_id = int(box.cls[0])
            label = str(names[class_id] if isinstance(names, dict) else names[class_id]).strip().upper()
            if len(label) != 1 or label not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                continue
            x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
            x1, x2 = max(0, x1), min(width, x2)
            y1, y2 = max(0, y1), min(height, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            characters.append({
                "label": label,
                "box": (x1, y1, x2, y2),
                "center_y": (y1 + y2) / 2,
                "height": y2 - y1,
                "confidence": float(box.conf[0]),
            })
        if not characters:
            return []

        typical_height = sorted(char["height"] for char in characters)[len(characters) // 2]
        row_tolerance = max(5, typical_height * 0.45)
        rows = []
        for char in sorted(characters, key=lambda item: item["center_y"]):
            row = next((item for item in rows if abs(item["center_y"] - char["center_y"]) <= row_tolerance), None)
            if row is None:
                rows.append({"center_y": char["center_y"], "characters": [char]})
            else:
                row["characters"].append(char)
                row["center_y"] = sum(item["center_y"] for item in row["characters"]) / len(row["characters"])

        segments = []
        max_character_gap = max(18, typical_height * 2.4)
        for row in rows:
            line = sorted(row["characters"], key=lambda item: item["box"][0])
            group = []
            for char in line:
                if group and char["box"][0] - group[-1]["box"][2] > max_character_gap:
                    segments.append(group)
                    group = []
                group.append(char)
            if group:
                segments.append(group)

        plates = []
        used = set()
        for index, segment in enumerate(segments):
            if index in used:
                continue
            merged = list(segment)
            left = min(char["box"][0] for char in segment)
            right = max(char["box"][2] for char in segment)
            top = min(char["box"][1] for char in segment)
            bottom = max(char["box"][3] for char in segment)
            center_x = (left + right) / 2
            span = max(1, right - left)
            for other_index, other in enumerate(segments[index + 1 :], start=index + 1):
                other_top = min(char["box"][1] for char in other)
                other_bottom = max(char["box"][3] for char in other)
                other_left = min(char["box"][0] for char in other)
                other_right = max(char["box"][2] for char in other)
                y_gap = max(0, max(top, other_top) - min(bottom, other_bottom))
                overlap = max(0, min(right, other_right) - max(left, other_left))
                other_center_x = (other_left + other_right) / 2
                if y_gap <= typical_height * 1.6 and (
                    overlap / min(span, max(1, other_right - other_left)) >= 0.25
                    or abs(center_x - other_center_x) <= max(span, other_right - other_left) * 0.35
                ):
                    merged.extend(other)
                    used.add(other_index)
                    left, right = min(left, other_left), max(right, other_right)
                    top, bottom = min(top, other_top), max(bottom, other_bottom)
                    center_x = (left + right) / 2
                    span = max(1, right - left)

            merged.sort(key=lambda char: (char["box"][1] // max(1, int(typical_height * 0.7)), char["box"][0]))
            raw = "".join(char["label"] for char in merged)
            plate = normalize_plate(raw)
            plates.append(Detection(
                plate=plate,
                raw_text=raw,
                confidence=sum(char["confidence"] for char in merged) / len(merged),
                bounding_box=(left, top, right, bottom),
                valid=valid_plate(plate),
                processing_time=(perf_counter() - started) * 1000,
                timestamp=datetime.now(timezone.utc),
            ))
        return plates
