# GateLog

ANPR-based campus vehicle movement and trip-purpose logging, built with FastAPI, MongoDB/PyMongo, React, Vite and Tailwind CSS.

This repository is the **Prompt 1 foundation**. It runs locally without MongoDB, a GPU, model weights or a camera using explicitly labelled, disposable demo storage and mock ANPR. Persistent operation uses MongoDB. The supplied GateLog design report was reviewed; see [report alignment](docs/report-alignment.md) for implemented and deferred modules.

## Start on Windows

Prerequisites: Python 3.10+ with pip and the Python launcher/PATH configured; Node.js 22 LTS or later with npm; a modern browser. The foundation was verified on Python 3.14 and Node.js 24.12. Optional AI libraries may require an older supported Python.

In PowerShell:

```powershell
cd D:\GateLog
.\scripts\setup.bat
.\scripts\run_backend.bat
```

Open a second terminal:

```powershell
cd D:\GateLog
.\scripts\run_frontend.bat
```

Open [GateLog](http://127.0.0.1:5173), [API docs](http://127.0.0.1:8000/docs), or [health](http://127.0.0.1:8000/health). Stop either server with Ctrl+C. Scripts bind to loopback and run one backend worker.

Setup creates .venv, installs backend/dev dependencies, installs the frontend from package-lock.json and copies .env.example to .env only if .env does not exist. Existing settings are preserved. Download Python from [python.org](https://www.python.org/downloads/windows/) and Node from [nodejs.org](https://nodejs.org/en/download) if missing; reopen the terminal after installation.

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env
cd frontend
npm.cmd ci
npm.cmd run build
```

Use the virtual environment's Python directly; activation is optional. Avoid overwriting an existing .env when doing manual setup.

## Demonstrate the full flow

1. The first startup seeds seven fictional student, staff, bus and service vehicles, two directional camera records and campus trip purposes.
2. On Dashboard choose **student / Entry**, then **Run detection**. Currently Inside and Entries Today increase; live activity records the plate.
3. Repeat the detection. No extra visit is created.
4. Select **Exit** and run detection. The visit completes, duration is saved, and the inside count falls.
5. Try **unknown** and **low confidence**. They appear in Review Queue without recording a movement.
6. Register another vehicle through Vehicle Registry. Record an entry with a purpose, open Currently Inside to record its exit, and search Vehicle History.
7. Edit or deactivate a registry record. Open visits must be closed before changing a plate or deactivating a vehicle.

Mock scenarios: TN09AB1234 (student), TN07EF5678 (staff), TN01BC9001 (bus), TN12DE4567 (service), KA03MN7890 (unknown), and the intentionally ambiguous raw text TN O9 AB I234 (low confidence). These are synthetic fixtures, not real personal data.

There are no invented historical movements. Dashboard counts and rows come from API writes. Memory mode resets on backend restart and cannot share data across processes.

## Architecture and structure

```text
backend/
  app/
    ai/           ANPR/OCR interfaces, mock/real adapters, video sources
    api/          dependency injection
    core/         validated settings and plate rules
    database/     MongoDB lifecycle, indexes and seed command
    models/       auxiliary document contracts
    schemas/      API request validation
    services/     movement engine, review, capture and live events
    routers/      vehicle, dashboard, WebSocket and image APIs
    main.py       application factory and lifespan
  tests/          isolated API/unit tests and opt-in MongoDB test
  requirements*.txt
frontend/
  src/
    components/   table, cards, forms, dialog, notices, demo controls
    hooks/        abortable data loading and reconnecting WebSocket
    layouts/      application navigation
    pages/        dashboard
    services/     API client
  tests/          browser workflow and mobile layout tests
database/seed/    deterministic fictional vehicle data
models/          model installation boundary
scripts/         Windows setup, server, seed and test commands
docs/            architecture and report alignment
```

Capture -> ANPRService -> normalized detection -> confidence/registry decision -> entry/exit engine -> MongoDB -> WebSocket notification -> React refetch.

Details: [architecture](docs/architecture.md), [database](database/README.md), [real model setup](models/README.md). Registry includes all seven required vehicle types. Unknown/uncertain detections are preserved in an additional review_items collection. Accepted entry/exit detections retain raw OCR evidence on the visit.

## MongoDB local or Atlas

Demo defaults to DATABASE_MODE=memory. **USE_MOCK_AI is independent of database mode.** You can use mock recognition against a real MongoDB database.

For local persistence install and start [MongoDB Community](https://www.mongodb.com/docs/manual/administration/install-community/), then edit .env:

```dotenv
DATABASE_MODE=mongodb
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=gatelog
USE_MOCK_AI=true
```

For [MongoDB Atlas](https://www.mongodb.com/docs/atlas/getting-started/), create a database user and permit the machine's IP in the project network access list. Put the supplied mongodb+srv URI in MONGODB_URI with credentials encoded correctly. Keep credentials only in .env; never prefix secrets with VITE_. TLS remains enabled by the Atlas URI.

Restart the backend and run:

```powershell
.\scripts\seed_demo.bat
```

Seed operations are idempotent and preserve existing records and edits. In memory mode this command explains that the running server must seed at startup; a separate process cannot seed another process's memory.

Startup pings MongoDB and builds indexes; a failed connection stops startup with an error. There is no silent database fallback. /health pings on each request and returns HTTP 503 for database unavailability. Shutdown closes the client.

Indexes include normalized plate uniqueness, one open visit per vehicle via a partial unique index, per-direction event IDs, query indexes and TTL indexes. TTL expires completed visits and resolved reviews after RETENTION_DAYS and audit records after their creation date plus RETENTION_DAYS. Open visits, pending reviews and the registry remain. Changing retention does not rewrite existing expiry timestamps.

## Configuration

All backend variables are read from the repository-root .env regardless of working directory. Shell environment values take precedence.

| Variable | Default / purpose |
| --- | --- |
| DATABASE_MODE | memory (explicit ephemeral adapter), or mongodb |
| MONGODB_URI | Local URI; mongodb+srv supported |
| MONGODB_DATABASE | gatelog |
| USE_MOCK_AI | true; selects mock vs real ANPR |
| SEED_ON_STARTUP | true; idempotent demo records |
| YOLO_MODEL_PATH | models/license_plate.pt; custom plate weights |
| OCR_CONFIDENCE_THRESHOLD | 0.80; inclusive acceptance threshold |
| DUPLICATE_COOLDOWN_SECONDS | 30; same vehicle, camera and direction |
| VIDEO_SOURCE | mock, rtsp, mp4 or webcam |
| RTSP_URL | RTSP address; backend-only secret |
| VIDEO_FILE | MP4 path; use an absolute path |
| WEBCAM_INDEX | 0 |
| FRAME_SAMPLE_RATE | 2 sampled frames per second |
| RUN_VIDEO_WORKER | false; opt in to continuous capture |
| CAMERA_ID | main-gate-in; must exist in cameras |
| CORS_ORIGINS | JSON array of frontend origins; also checked for WebSockets |
| CAMPUS_TIMEZONE | Asia/Kolkata; day-boundary calculation |
| RETENTION_DAYS | 90; completed/resolved records and audit retention |
| VITE_API_URL | http://127.0.0.1:8000; public frontend API origin |

Change frontend settings before rebuilding/restarting Vite. UI timestamps are explicitly shown in IST. Source FPS and FRAME_SAMPLE_RATE are different: sampling reduces inference calls; it is not a hardware performance guarantee.

## ANPR and video

Mock mode is enabled by default. The dashboard simulator calls POST /detections/mock and exercises the real registry/movement/review services.

The real adapter performs YOLO plate detection -> crop -> grayscale/resize/denoise/threshold -> replaceable OCR -> raw text preservation -> normalization -> Indian-format validation -> conservative confidence. Confidence below the threshold or invalid syntax always routes to review. Normalization uppercases and removes whitespace/hyphens; unsupported punctuation is retained so it cannot silently become a valid plate. O/0, I/1, B/8 and S/5 are never guessed.

To enable real recognition:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ai.txt
```

Install the Tesseract executable on PATH, provide licensed custom plate-detector YOLO weights, set USE_MOCK_AI=false and YOLO_MODEL_PATH, then restart. Neither weights nor optional AI dependencies are loaded until recognition is requested. No models are downloaded automatically. A GPU is optional. See models/README.md for the boundary and platform compatibility.

The image endpoint accepts **raw PNG/JPEG bytes**, not multipart:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/anpr/detect?camera_id=main-gate-in" -H "Content-Type: image/jpeg" --data-binary "@D:\clips\plate.jpg"
```

The endpoint runs recognition and processes the resulting movement/review. It is limited to 8 MiB uploads and 16 megapixels after decode. In mock mode a valid uploaded image produces the deterministic student scenario; image pixels are not interpreted.

For continuous video set RUN_VIDEO_WORKER=true, choose VIDEO_SOURCE, configure the corresponding address/path and CAMERA_ID. RTSP/webcam interruptions mark the camera offline and retry with backoff capped at 30 seconds. MP4 EOF stops capture; restart to replay. Capture closes the source on shutdown. Fixed IN/OUT camera directions are supported; tracking and virtual-line crossing are deferred. Do not point one fixed-direction configuration at a bidirectional lane.

## API surface

| Method | Endpoint | Result |
| --- | --- | --- |
| POST / GET | /vehicles | Register / filtered paginated registry |
| GET | /vehicles/by-plate/{plate} | Normalized lookup |
| GET / PUT / DELETE | /vehicles/{id} | Get / full update / soft deactivate |
| POST | /vehicles/{id}/entry | New visit (201) or duplicate (200) |
| POST | /vehicles/{id}/exit | Completed visit or duplicate (200) |
| GET | /vehicles/inside | Open visits with total count |
| GET | /vehicles/{id}/history | Paginated visits |
| GET | /logs/today | Visits entering or exiting within the campus day |
| GET | /dashboard /activity /cameras /purposes | Actual operational data |
| POST | /detections/mock | Named scenario and IN/OUT direction |
| POST | /anpr/detect | Raw image recognition and processing |
| GET | /reviews | Pending uncertain/unknown detections |
| POST | /reviews/{id}/dismiss | Resolve review without a movement |
| GET | /health | Database health and persistence mode |
| WS | /ws/events | Live notifications and heartbeat |

Movement bodies support camera_id, purpose, optional event_id/tracking_id, detection_confidence and an optional timezone-aware timestamp. Normal operations use server time. Use main-gate-out for exit requests. Event IDs make retries idempotent per direction; keep the same ID when retrying a request. Camera mismatch, low confidence, naive/future/out-of-order times return 422; missing resources return 404; duplicate plates or impossible state transitions return 409.

The API rejects negative durations, uses total_seconds for multi-day stays, and never creates two open visits. Cooldown suppresses even legitimate very rapid repeat passes at the same directional camera; tune it to the campus lane. A repeated exit from the previous visit cannot close a newly reopened visit within cooldown.

## Tests and verification

Backend, no MongoDB/camera/GPU required:

```powershell
.\scripts\test.bat
.\.venv\Scripts\ruff.exe check backend
```

The script uses a project-local pytest temporary directory to avoid shared Windows temp permission conflicts.

Real MongoDB test (creates and drops only a randomly named gatelog_test_* database):

```powershell
$env:TEST_MONGODB_URI="mongodb://127.0.0.1:27017"
.\scripts\test.bat
Remove-Item Env:TEST_MONGODB_URI
```

Browser tests use installed Microsoft Edge and start their own servers unless ports are already serving GateLog. Stop your demo servers first for an isolated run; tests create synthetic records.

```powershell
cd frontend
npm.cmd run test:e2e
npm.cmd run build
```

If Edge is unavailable, set Playwright's channel to chromium and install its browser with npx playwright install chromium. The tests check the full registry -> entry -> exit -> history -> low-confidence review path, live WebSocket connection, console errors and mobile width.

Do not interpret tests with injected OCR/detectors as measured real recognition accuracy. Optional physical camera, weights, Tesseract and MongoDB integration are independent of the synthetic demo.

## Current phase boundaries

Authentication/RBAC, exports, full visitor and bus CRUD, purpose administration, OCR confirmation/correction and single-camera tracking are later phases. The Review Queue currently supports inspection/dismissal and manual follow-up through registry/movement forms.

Run **one Uvicorn worker**: cooldown locks and the WebSocket hub are process-local. Production scaling requires distributed event delivery, shared atomic cooldown and transactional state/audit updates. This foundation has no login and identifies audit actions as local-operator; keep it on loopback with synthetic data until access control is implemented.

## Troubleshooting

- **Python/npm not found:** install the prerequisites with PATH enabled and reopen the terminal. Use npm.cmd in PowerShell if npm.ps1 is blocked by execution policy.
- **MongoDB server selection timeout:** verify the service/URI, Atlas IP allowlist and credentials; health never pretends the server is available. For disposable demos select DATABASE_MODE=memory explicitly.
- **Empty data after restart:** expected in memory mode. Use MongoDB for persistence and SEED_ON_STARTUP=true for demo records.
- **Missing model/OCR:** mock mode needs neither. Real image requests return 503 until weights, optional packages and Tesseract are configured.
- **Camera offline:** check VIDEO_SOURCE, address/path, CAMERA_ID and model dependencies. Live sources retry; MP4 ends normally when its frames run out.
- **No real-time connection:** check the API origin and CORS_ORIGINS including scheme, hostname and port. WebSocket route is /ws/events; the UI refetches on reconnect.
- **Port in use:** stop the existing GateLog process or adjust both server command and VITE_API_URL/CORS settings.
- **Entry ignored after a rapid round trip:** the configured same-direction cooldown is working. Wait or reduce the cooldown for a controlled demo.
- **Old records still present:** MongoDB TTL deletion is asynchronous; pending reviews and open visits intentionally have no expiry.
- **Test dependency warnings on Python 3.14:** mongomock and Starlette emit upstream deprecation warnings; these are not assertion failures. The tested versions are recorded in backend/requirements-lock.txt.

Framework references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [MongoDB partial indexes](https://www.mongodb.com/docs/manual/core/index-partial/), [Tailwind with Vite](https://tailwindcss.com/docs/installation/using-vite).
