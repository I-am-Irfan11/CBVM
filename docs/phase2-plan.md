# Phase 2 implementation plan

Spec: user's Prompt 2 attachment and GateLog_Design_Project_Report.docx. Work in the existing D:/GateLog checkout on codex/phase-1, as explicitly requested. Do not start over. Preserve the technology stack. No real credentials or public staff contacts in source. No fabricated transport facts or AI measurements.

## Task 1: Transport reference and tracking/video boundary

Own only backend/app/ai (including existing anpr.py/video.py), backend/app/services/capture.py, backend/app/database/transport.py, database/seed/hits_transport.json, backend/tests/test_tracking.py, backend/tests/test_transport.py, docs/transport-source.md. Do not edit settings, main, operations, routers, dependencies, requirements or existing tests. Do not spawn agents or commit other workers' files.

Retrieve https://hindustanuniv.ac.in/facilities/transport/ and implement a retryable CLI importer using requests/urllib and BeautifulSoup if needed (notify parent of dependencies). Save only route number/name, bus name, ordered boarding points/times and endpoint. Exclude all personal incharge names/phones. Record fetch date, URL and source timetable label (currently 2023-2024), distinguish from fictional operating buses. Implement seed_transport(db) and CLI --refresh to update checked-in sanitized snapshot, preserving source provenance and not claiming page publication date equals fetch time. Fetch first, validate, atomic replacement; failed refresh must preserve snapshot. Use transport_routes collection with stable route-number IDs. Add fixtures/tests against actual snapshot plus malformed page rejection.

Implement a replaceable Tracker abstraction, bounded centroid/IoU tracker with per-camera tracks, expiry, stable tracking IDs and virtual gate-line direction using normalized line coordinates, minimum movement/hysteresis and one event per crossing. Extend Detection with optional tracking_id, camera_id and direction. Provide FrameTracker.process(detections, camera, frame_shape) returning candidate detections for fixed IN/OUT cameras or crossings for BOTH. Do not infer motion direction from OCR alone. Camera fields: direction IN/OUT/BOTH, gate_line [0.1,0.5,0.9,0.5], inward_sign 1 or -1, minimum_movement 0.03. Repeated detections must retain tracks; no crossing on first appearance. Add tests for both directions, jitter, expiry and separate cameras.

Integrate FrameTracker into CaptureWorker before state.processor.process; processor will be updated by parent to honor Detection.direction for BOTH cameras. Use settings.reconnect_delay_seconds (parent adds setting default 1). Preserve mock mode and lazy YOLO. Capture worker must expose actual offline/restored status, last frame and source, stop gracefully, use bounded retry backoff, emit camera.offline/camera.restored events. Fixed-camera mock frames remain supported. No GPU or physical camera for tests. Optional frames may be retained only in bounded app-memory preview store (if implemented) and never written by default.

## Task 2: Backend identity and campus services (controller)

Implement Argon2id passwords, JWT with required expiry/issuer/audience/jti and database sessions, HttpOnly cookie and CSRF double submit, bearer support for API clients, active-user lookup and immediate revocation. Roles security/admin/department_staff enforced on backend including scoped department queries and WebSockets. Seed passwords only via env; bootstrap generates random local secrets. Complete visitors, purposes, buses/trips, reviews, cameras, users, retention, audit, filtered history, analytics and CSV reports. Preserve and expand tests. Audit actor comes from backend identity.

## Task 3: Operational frontend

Replace the decorative dashboard with compact security operations UI, login/logout/session, role-protected pages, all 14 navigation destinations, dense API-backed tables, filters, forms and actions. Integrate the API contract docs/phase2-api.md supplied by controller. Frontend owns frontend/src and frontend/tests only. Use React/Vite/Tailwind, no hardcoded stats. Auth uses HttpOnly cookie, CSRF returned by login/me, credentials include. No token/password localStorage. Existing components may be reused. Run frontend build and browser tests after backend integration.

## Task 4: Portability, seed, verification and review (controller)

Complete Windows/macOS scripts, development-only generated credentials, deterministic operational seed and guarded reset. Rewrite README. Verify JWT/RBAC, all business flows, CSV, camera/tracking, WebSockets, frontend responsiveness. Security review and independent final review. Real MongoDB/camera/model/macOS execution can be externally dependent; report actual evidence only.
