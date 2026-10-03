from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
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
        if frame is None or frame.size == 0:
            return []
        started = perf_counter()
        rows = []
        height, width = frame.shape[:2]
        for result in self.model.predict(frame, verbose=False):
            for box in result.boxes:
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
                plate = normalize_plate(raw)
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
