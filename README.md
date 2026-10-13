# GateLog

ANPR-based campus vehicle movement and trip-purpose logging, built with FastAPI, MongoDB/PyMongo, React, Vite and Tailwind CSS.

GateLog is an ANPR-based campus gate operations system built with FastAPI, MongoDB/PyMongo, React, Vite and Tailwind CSS. It supports Firebase sign-in with Google and email/password, vehicle entry and exit, visitor and bus workflows, human review of uncertain plates, audit records, analytics and CSV exports. Persistent use requires MongoDB. Real ANPR requires separately trained model weights; this project can use either a plate-box detector with Tesseract OCR or the supplied character-box model dataset.

## Start on Windows

Prerequisites: Python 3.10+ with pip and the Python launcher/PATH configured; Node.js 22 LTS or later with npm; a modern browser. The foundation was verified on Python 3.14 and Node.js 24.12. Optional AI libraries may require an older supported Python.

In PowerShell:

```powershell
cd D:\GateLog
.\scripts\setup.bat
.\scripts\run_backend.bat
```

Setup creates a private `.env` when needed and generates a local JWT secret. Existing `.env` values are preserved. Configure Firebase Authentication and set the Firebase variables described below before hosting GateLog. Open a second terminal:

```powershell
cd D:\GateLog
.\scripts\run_frontend.bat
```

Open [GateLog](http://127.0.0.1:5173), [API docs](http://127.0.0.1:8000/docs), or [health](http://127.0.0.1:8000/health). Stop either server with Ctrl+C. Scripts bind to loopback and run one backend worker.

Setup creates `.venv`, installs backend/dev dependencies, installs the frontend from `package-lock.json`, and bootstraps local auth secrets. Download Python from [python.org](https://www.python.org/downloads/windows/) and Node from [nodejs.org](https://nodejs.org/en/download) if missing; reopen the terminal after installation.

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env
python scripts\bootstrap_env.py
cd frontend
npm.cmd ci
npm.cmd run build
```

Use the virtual environment's Python directly; activation is optional. Avoid overwriting an existing .env when doing manual setup.

## macOS setup

Install Python 3.10+ and Node.js 22+, then run `bash scripts/setup.sh`. Start the backend and frontend in separate terminals with `bash scripts/start-backend.sh` and `bash scripts/start-frontend.sh`. `bash scripts/seed-demo.sh` loads optional sample records into persistent MongoDB. `bash scripts/test.sh` runs the backend suite and frontend production build. These scripts use paths relative to the repository.

## Authentication and roles

Sign in through Firebase with Google or email/password. Administrators are assigned through `FIREBASE_ADMIN_EMAILS` or the User access page. The backend verifies Firebase tokens, issues a short-lived HttpOnly session cookie and enforces CSRF checks for writes. The frontend API remains same-origin at `/api`.

Vehicle registry, plate readings, movement history, review decisions and audit records belong in MongoDB Atlas (`DATABASE_MODE=mongodb`). Original uploaded ANPR images can be stored in a private Cloudflare R2 bucket. Create a bucket-scoped R2 API token and set `R2_ENDPOINT_URL`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`. GateLog stores only the private object key beside the detection record; an operator can request a short-lived signed read URL from `/anpr/scans/{object_key}`. The upload is skipped when R2 is not configured. Add an R2 lifecycle rule for the `scans/` prefix matching your retention policy (90 days by default).

## Demonstrate the full flow

1. Start with an empty vehicle registry. Register a vehicle through **Vehicle Registry**.
2. On Dashboard select that registered vehicle and **Entry**, then click **Run detection**. Currently Inside and Entries Today increase; live activity records the plate.
3. Repeat the detection. No extra visit is created.
4. Select **Exit** and run detection. The visit completes, duration is saved, and the inside count falls.
5. The simulator uses the selected registry plate; detections for unregistered vehicles are handled by real ANPR review flow.
6. Register another vehicle through Vehicle Registry. Record an entry with a purpose, open Currently Inside to record its exit, and search Vehicle History.
7. Edit or deactivate a registry record. Open visits must be closed before changing a plate or deactivating a vehicle.

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
    routers/      auth, vehicle, campus workflows, dashboard, WebSocket and image APIs
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
database/seed/    deterministic demo inputs for isolated development
models/          model installation boundary
scripts/         Windows setup, server, seed and test commands
docs/            architecture and report alignment
```

Capture -> detector/OCR adapter -> tracking and plate validation -> confidence/registry decision -> movement engine -> MongoDB -> WebSocket notification -> React refetch.

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
| USE_MOCK_AI | false; selects mock vs real ANPR |
| SEED_ON_STARTUP | false; creates configured development seed records |
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
| FIREBASE_PROJECT_ID | Firebase project ID used to verify Firebase ID tokens on the backend |
| FIREBASE_ALLOWED_EMAILS / FIREBASE_ALLOWED_DOMAINS | Comma-separated sign-in allowlist; add your own account and permitted operators. `*` permits every identity |
| FIREBASE_ALLOWED_UIDS | Optional comma-separated Firebase user IDs when phone access is managed by UID |
| FIREBASE_ADMIN_EMAILS | Comma-separated verified email accounts assigned the GateLog administrator role |
| R2_ENDPOINT_URL / R2_BUCKET | R2 S3 endpoint and private bucket name |
| R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | Bucket-scoped R2 S3 credentials; backend only |
| R2_PRESIGNED_URL_EXPIRY_SECONDS | Signed scan image link lifetime; 300 seconds by default |
| SEED_OPERATIONAL_DATA | false by default; set true only to load fictional sample vehicles and operations |
| RECONNECT_DELAY_SECONDS | 1 second initial capture reconnect delay; backoff is capped |
| VITE_API_URL | /api; public API base path the frontend calls (override with an absolute origin when the API is on a different hostname) |

Change frontend settings before rebuilding/restarting Vite. UI timestamps are explicitly shown in IST. Source FPS and FRAME_SAMPLE_RATE are different: sampling reduces inference calls; it is not a hardware performance guarantee.

## Firebase sign-in

Enable Google and Email/Password in Firebase Authentication. Add `cbvm.vercel.app` and `localhost` to Firebase's authorized domains. In Vercel, set the five public `VITE_FIREBASE_*` web-app values and backend `FIREBASE_PROJECT_ID`; these are Firebase client settings, not database credentials. Add your email to `FIREBASE_ADMIN_EMAILS` to receive the admin role. Other users need to be added in User access first or included in `FIREBASE_ALLOWED_EMAILS` (or an allowed domain). Unknown accounts are denied if no allowlist or invitation exists. GateLog verifies Firebase ID-token signatures and claims, then creates its own HttpOnly session; Firebase handles passwords. Never put MongoDB or JWT secrets in `VITE_*` variables.

The browser login offers email/password account creation and sign-in plus Google popup sign-in. The first administrator can be invited with `scripts/create_admin.py` or automatically granted by `FIREBASE_ADMIN_EMAILS`. Production never accepts GateLog-local passwords; legacy password endpoints are enabled only in automated tests.

## ANPR and video

Mock mode is enabled by default. The dashboard simulator calls POST /detections/mock and exercises the real registry/movement/review services.

The real adapter performs YOLO plate detection -> crop -> grayscale/resize/denoise/threshold -> replaceable OCR -> raw text preservation -> normalization -> Indian-format validation -> conservative confidence. Confidence below the threshold or invalid syntax always routes to review. Normalization uppercases and removes whitespace/hyphens; unsupported punctuation is retained so it cannot silently become a valid plate. O/0, I/1, B/8 and S/5 are never guessed.

To enable real recognition:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ai.txt
```

Set `USE_MOCK_AI=false` and `YOLO_MODEL_PATH` to the trained `.pt` file, install `backend/requirements-ai.txt` in the local backend environment, and restart. The Roboflow character-box model does not need Tesseract; a single-class full-plate detector does. No weights are downloaded automatically or committed. For the laptop webcam demo, run the backend locally on the laptop and open the site over HTTPS or localhost. Vercel's serverless backend is not the place to run a webcam or load large PyTorch weights. See models/README.md for details.

Mock mode does not interpret uploaded pixels; use the dashboard simulator to exercise a vehicle currently in the registry. The image endpoint accepts **raw PNG/JPEG bytes**, not multipart:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/anpr/detect?camera_id=main-gate-in" -H "Content-Type: image/jpeg" --data-binary "@D:\clips\plate.jpg"
```

The endpoint runs recognition and processes the resulting movement/review. It is limited to 8 MiB uploads and 16 megapixels after decode. Mock mode does not interpret uploaded pixels; use the dashboard simulator to exercise a vehicle currently in the registry.

For continuous video set RUN_VIDEO_WORKER=true, choose VIDEO_SOURCE, configure the corresponding address/path and CAMERA_ID. The replaceable tracker supports fixed IN/OUT cameras and a BOTH camera with a configured virtual gate line. RTSP/webcam interruptions mark the camera offline and retry with backoff capped at 30 seconds. MP4 EOF stops capture; restart to replay. Capture closes the source on shutdown. Configure source URLs and camera credentials only in backend environment variables.

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
| GET | /dashboard /activity | Live operational summary and activity |
| GET / POST / PUT | /visitors | Visitor registration and host/visit details |
| GET / POST / PUT | /buses | Bus registry linked to a registered vehicle and operator-entered route |
| POST | /buses/{id}/trips and /trips/return | Departure and return records linked to gate movements |
| GET / POST / PUT | /cameras | Camera configuration and health records |
| GET / POST / PUT | /purposes | Configurable trip purposes (admin writes) |
| GET | /analytics | Filtered daily/hourly counts, purpose and vehicle summaries |
| GET | /reports.csv | Filtered CSV export |
| GET | /audit | Administrative and manual audit records (admin) |
| GET / POST / PUT | /users | Account administration (admin) |
| GET / PUT | /settings/retention | Retention configuration (admin) |
| POST | /detections/mock | Simulate a registered vehicle and IN/OUT direction |
| POST | /anpr/detect | Raw image recognition and processing |
| GET | /reviews | Pending uncertain/unknown detections |
| POST | /reviews/{id}/resolve | Confirm/correct or reject a reading with audit record |
| POST | /reviews/{id}/dismiss | Dismiss without recording a movement |
| GET | /auth/config /auth/me | Auth setup status / signed-in identity and CSRF token |
| POST | /auth/firebase | Verify a Firebase ID token and issue a protected GateLog session |
| POST | /auth/logout | Sign out of GateLog |
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

Run **one Uvicorn worker**: movement locks and the WebSocket hub are process-local. Multi-process production deployment needs shared event delivery, distributed movement coordination and transactional state/audit writes. The capture worker currently runs one configured source per backend process. PDF export is not included; CSV export is implemented. Real OCR accuracy and camera throughput have not been measured.

## Troubleshooting

- **Python/npm not found:** install the prerequisites with PATH enabled and reopen the terminal. Use npm.cmd in PowerShell if npm.ps1 is blocked by execution policy.
- **MongoDB server selection timeout:** verify the service/URI, Atlas IP allowlist and credentials; health never pretends the server is available. For disposable demos select DATABASE_MODE=memory explicitly.
- **Empty data after restart:** expected in memory mode. Use MongoDB for persistence.
- **Missing model:** real image requests return 503 until weights and Ultralytics are installed. A character-box model does not need Tesseract; a one-class plate-box model does.
- **Firebase sign-in unavailable:** check the Vercel `VITE_FIREBASE_*` web-app settings, backend `FIREBASE_PROJECT_ID`, the authorized domain in Firebase, and the backend allowlist.
- **Camera offline:** check VIDEO_SOURCE, address/path, CAMERA_ID and model dependencies. Live sources retry; MP4 ends normally when its frames run out.
- **No real-time connection:** check the API origin and CORS_ORIGINS including scheme, hostname and port. WebSocket route is /ws/events; the UI refetches on reconnect.
- **Port in use:** stop the existing GateLog process or adjust both server command and VITE_API_URL/CORS settings.
- **Entry ignored after a rapid round trip:** the configured same-direction cooldown is working. Wait or reduce the cooldown for a controlled demo.
- **Old records still present:** MongoDB TTL deletion is asynchronous; pending reviews and open visits intentionally have no expiry.
- **Test dependency warnings on Python 3.14:** mongomock and Starlette emit upstream deprecation warnings; these are not assertion failures. The tested versions are recorded in backend/requirements-lock.txt.

Framework references: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [MongoDB partial indexes](https://www.mongodb.com/docs/manual/core/index-partial/), [Tailwind with Vite](https://tailwindcss.com/docs/installation/using-vite).
