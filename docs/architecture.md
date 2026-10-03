# GateLog Phase 1 architecture

FastAPI routers validate requests and call synchronous services in a thread pool. PyMongo is the production database client. An explicitly selected mongomock adapter supports disposable demos and tests with the same queries/index declarations.

Capture -> ANPRService -> DetectionProcessor -> Operations -> MongoDB -> EventHub -> React

ANPRService has mock and real adapters. OCRService is independently replaceable. VideoSource has OpenCV RTSP/MP4/webcam and mock adapters. Models load lazily and capture is opt-in. Images are processed in memory and not retained.

The movement engine normalizes registration at the registry boundary, uses server UTC timestamps by default, pairs exits with open visits, rejects out-of-order/future/naive timestamps, and uses total_seconds for multi-day durations. Dates are stored in UTC; today's counts use CAMPUS_TIMEZONE. The UI displays IST.

A unique partial MongoDB index enforces one open visit. A process lock serializes state transitions and registry deactivation. Event IDs are unique per direction and retries return duplicate=true. Completed logs retain entry and exit events. Phase 1 supports **one Uvicorn worker**. Multi-process cooldown, distributed WebSocket fan-out and transactional audit persistence are later work.

WebSocket clients get connected, vehicle.entry, vehicle.exit, review.item, review.resolved and camera.status events. The server sends heartbeats. Each client has a bounded 100-event queue; slow clients can lose transient events. The browser reconnects with capped backoff and refetches canonical API state on reconnect/events, plus every 30 seconds. Events are notifications, not a durable delivery queue.

Audit events identify local-operator because authentication/RBAC is not implemented in this foundation. Bind to loopback and use fictional data until authorization is added. MongoDB operations and audit insertion are separate writes; a write can persist even if its subsequent audit insert fails. Movement event IDs permit safe retries. Automatic barrier control is absent.

The report's full ten-module vision exceeds this prompt's explicit Phase 1 definition. See report-alignment.md for implemented boundaries and deferred work.
