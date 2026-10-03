# Real ANPR model boundary

The demo needs no weights, GPU, OCR installation or camera.

For real recognition use a **custom license-plate detector**, not generic COCO vehicle weights. Set YOLO_MODEL_PATH to a local .pt file; relative paths resolve from the repository root. Weights are deliberately not downloaded or committed.

Install backend/requirements-ai.txt in a Python environment supported by PyTorch/Ultralytics (Python 3.11 or 3.12 is a practical choice if their wheels are unavailable on a newer Python). Install the Tesseract executable and put it on PATH. The supplied TesseractOCR adapter can be replaced with any OCRService implementation.

RealANPRService lazily loads YOLO, clamps plate boxes to frame bounds, crops, converts to grayscale, resizes, denoises, thresholds, invokes OCR, preserves raw text and validates syntax. The conservative confidence is the minimum of detector and OCR confidence; it is not a calibrated probability.

This phase detects plate regions directly. It does not yet implement a separate vehicle detector, multi-frame tracker, best-frame selection, or virtual-line crossing. Configure a camera with a fixed IN or OUT direction. Real accuracy and throughput require evaluation against your own labelled footage and licensed weights.
