from abc import ABC, abstractmethod
import ast
from datetime import datetime, timezone
from pathlib import Path
import re
from types import SimpleNamespace
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import resolve_model_path
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


class RapidOCRService(OCRService):
    """OCR fallback whose ONNX models are distributed with the Python package."""

    def __init__(self):
        self.engine = None

    def read(self, image):
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self.engine = RapidOCR()
        result, _ = self.engine(image)
        if not result:
            return "", 0.0
        words = [(str(item[1]).strip(), float(item[2])) for item in result if str(item[1]).strip()]
        if not words:
            return "", 0.0
        return " ".join(word for word, _ in words), sum(score for _, score in words) / len(words)


class ONNXYOLO:
    """Small ONNX Runtime adapter for Ultralytics exports with embedded NMS."""

    def __init__(self, path):
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        metadata = self.session.get_modelmeta().custom_metadata_map
        try:
            self.names = ast.literal_eval(metadata.get("names", "{}"))
        except (SyntaxError, ValueError):
            self.names = {}
        shape = self.session.get_inputs()[0].shape
        self.input_height = int(shape[-2]) if isinstance(shape[-2], int) else 640
        self.input_width = int(shape[-1]) if isinstance(shape[-1], int) else 640

    def predict(self, frame, verbose=False):
        import cv2
        import numpy as np

        height, width = frame.shape[:2]
        scale = min(self.input_width / width, self.input_height / height)
        resized_width, resized_height = round(width * scale), round(height * scale)
        resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        pad_x = (self.input_width - resized_width) / 2
        pad_y = (self.input_height - resized_height) / 2
        left, top = round(pad_x - 0.1), round(pad_y - 0.1)
        right, bottom = self.input_width - resized_width - left, self.input_height - resized_height - top
        padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        tensor = np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        output = self.session.run(None, {self.input_name: tensor})[0]
        detections = []
        for x1, y1, x2, y2, confidence, class_id in output.reshape(-1, 6):
            x1 = max(0, min(width, int((x1 - pad_x) / scale)))
            y1 = max(0, min(height, int((y1 - pad_y) / scale)))
            x2 = max(0, min(width, int((x2 - pad_x) / scale)))
            y2 = max(0, min(height, int((y2 - pad_y) / scale)))
            if confidence <= 0 or x2 <= x1 or y2 <= y1:
                continue
            detections.append(SimpleNamespace(
                xyxy=np.asarray([[x1, y1, x2, y2]], dtype=np.float32),
                conf=np.asarray([confidence], dtype=np.float32),
                cls=np.asarray([int(class_id)], dtype=np.float32),
            ))
        yield SimpleNamespace(boxes=detections, names=self.names)


class RealANPRService(ANPRService):
    def __init__(self, settings, ocr: OCRService | None = None):
        self.path = resolve_model_path(settings.yolo_model_path)
        self.ocr = ocr or RapidOCRService()
        self.model = None

    def detect(self, frame):
        import cv2

        # Lazy load: real mode can start without a camera or model file.
        if self.model is None:
            if not self.path.is_file():
                raise RuntimeError("License-plate YOLO weights are missing; configure YOLO_MODEL_PATH")
            if self.path.suffix.lower() == ".onnx":
                self.model = ONNXYOLO(self.path)
            else:
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
                character_boxes = [box for box in result.boxes
                                   if str(self.model.names[int(box.cls[0])]).strip().upper()
                                   in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
                # This model predicts both plate regions and individual characters.
                # Prefer its character predictions inside each plate region over
                # sending a low-resolution crop to a generic OCR engine.
                if plate_boxes and character_boxes:
                    ocr_fallback_boxes = []
                    for plate_box in plate_boxes:
                        px1, py1, px2, py2 = (int(v) for v in plate_box.xyxy[0].tolist())
                        inside = [box for box in character_boxes
                                  if px1 <= float(box.xyxy[0][0] + box.xyxy[0][2]) / 2 <= px2
                                  and py1 <= float(box.xyxy[0][1] + box.xyxy[0][3]) / 2 <= py2]
                        if inside:
                            char_result = SimpleNamespace(boxes=inside, names=result.names)
                            rows.extend(self._read_character_boxes(char_result, width, height, started))
                        else:
                            ocr_fallback_boxes.append(plate_box)
                    if not ocr_fallback_boxes:
                        continue
                    plate_boxes = ocr_fallback_boxes
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
                if not plate:
                    continue
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
