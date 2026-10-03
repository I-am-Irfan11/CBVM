# Phase 1 verification

Verified locally on 2026-10-03 with Python 3.14.0, Node.js 24.12.0 and Microsoft Edge.

| Check | Actual result |
| --- | --- |
| scripts/setup.bat | Passed; Python dependencies installed, npm ci completed, local .env created |
| scripts/test.bat | 45 passed, 1 skipped |
| ruff check backend | Passed |
| pip check | No broken requirements |
| npm run build | Passed; Vite production bundle generated |
| npm run test:e2e | 2 passed |
| scripts/seed_demo.bat | Passed; explains startup seeding for memory mode |
| GET /health on running Uvicorn | 200, status ok, database memory, persistent false |
| Mock scenario smoke run | Student/bus/staff entry, staff exit, unknown and low-confidence review |
| Desktop/mobile visual inspection | Inspected 1512px desktop and 390px mobile captures; no page overflow |

Backend coverage includes normalization without ambiguous-character replacement, Indian/Bharat syntax, registry CRUD, normalized uniqueness, entry/exit and duration, timestamp validation, inside/history/today queries, concurrent entry, repeated detection cooldown including exit-after-reentry, event retries, seed idempotence, live WebSocket events, review deduplication/dismissal, raw OCR preservation, real pipeline with injected detector/OCR, real OpenCV MP4 reading, and live-source reconnect using a controlled test adapter.

Browser coverage exercises registration, entry, exit, completed history, low-confidence review, dismissal, WebSocket connectivity, JavaScript errors and mobile page width.

The optional real MongoDB test was skipped: no TEST_MONGODB_URI was supplied, no local MongoDB listened on port 27017, and Docker's engine was not running. Physical camera, real trained YOLO weights and Tesseract recognition were not exercised. No field OCR accuracy or throughput is claimed.

Upstream mongomock datetime and Starlette TestClient deprecation warnings remain. They do not represent failed tests. Installed versions are captured in backend/requirements-lock.txt; frontend dependencies are locked in package-lock.json.

Two defects were reproduced and fixed during testing: double-slash WebSocket paths, and repeated previous-visit exit detections closing a new visit. Windows shared-temp permissions were handled by project-local pytest temporary files.
