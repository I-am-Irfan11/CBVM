# Real ANPR model boundary

The demo needs no weights, GPU, OCR installation or camera.

The project supports two model layouts. A **single-class plate-box detector** finds each whole plate and then uses Tesseract OCR. The supplied Roboflow dataset is a **37-class character-box detector** (digits, letters and plate markings); GateLog reads those class labels in image order, so it does not need Tesseract. Do not use generic COCO vehicle weights for either layout. Set YOLO_MODEL_PATH to the trained `.pt` file; relative paths resolve from the repository root. Weights are deliberately not downloaded or committed.

Install backend/requirements-ai.txt in a Python environment supported by PyTorch/Ultralytics (Python 3.11 or 3.12 is a practical choice if their wheels are unavailable on a newer Python). For single-class plate-box weights, install the Tesseract executable and put it on PATH. The supplied TesseractOCR adapter can be replaced with any OCRService implementation.

RealANPRService lazily loads YOLO. Character-class weights are recognized from their class names; text boxes are grouped into rows, ordered, normalized and checked against Indian registration syntax. Plate-box weights instead have their boxes clamped to frame bounds, then crop, grayscale, resize, denoise, threshold and pass through OCR. Confidence values are model scores, not calibrated probabilities.

This phase detects plate regions directly. It does not yet implement a separate vehicle detector, multi-frame tracker, best-frame selection, or virtual-line crossing. Configure a camera with a fixed IN or OUT direction. Real accuracy and throughput require evaluation against your own labelled footage and licensed weights.
