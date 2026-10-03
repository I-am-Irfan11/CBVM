# GateLog architecture

FastAPI routes validate requests, apply authentication and role checks, then call the services. PyMongo is the persistent database client. Explicit memory mode uses mongomock for disposable demos and tests.

VideoSource -> ANPRService -> optional tracker and gate-line direction -> DetectionProcessor -> Operations -> MongoDB -> WebSocket EventHub -> React API refetch.

ANPRService has deterministic mock and lazily loaded real adapters. OCRService can be replaced independently. OpenCV supports RTSP, MP4 and webcam sources. Frames are processed in memory and are not retained by default. The capture worker supervises one configured source per process.

Authentication uses Cloudflare Access with Google as the identity provider. FastAPI validates each `Cf-Access-Jwt-Assertion` signature against the Access JWKS, and checks its issuer and application audience before mapping the Google email to a GateLog role. The backend stores account metadata only, never a password. Keep the origin behind Cloudflare Tunnel and restrict eligible Google accounts in the Access policy. Roles are enforced by backend dependencies, and department staff queries are scoped. Audit entries record actor ID and role. Audit writes and business writes are separate, so MongoDB transactions are needed for atomic audit guarantees.

The movement engine stores UTC timestamps, checks the configured campus timezone for day boundaries, pairs exits with open visits, rejects invalid chronology, and calculates total seconds. A partial unique database index enforces one open visit per vehicle. MongoDB stores plate and movement metadata; when R2 is configured, the original uploaded image goes to a private bucket and its object key is attached to the detection. Operators receive short-lived signed image URLs after the backend confirms the key belongs to a stored detection. Set an R2 lifecycle rule to match `RETENTION_DAYS`. Process-local locks and the in-memory WebSocket hub mean GateLog must run with one Uvicorn worker until shared coordination/event delivery is added.

The HITS transport collection is a historical reference dataset and is not used to seed operational buses. Vehicle, bus, visitor and movement records marked demo are fictional. See [transport source notes](transport-source.md) and [report alignment](report-alignment.md).
