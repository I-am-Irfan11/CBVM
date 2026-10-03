# MongoDB model

The authoritative connection and index definitions are in backend/app/database/connection.py. Identifiers are UUID strings (stable readable IDs for seeded records), avoiding ObjectId serialization leaks.

Collections: vehicles, vehicle_logs, purposes, visitors, buses, cameras, audit_logs. review_items is an additional queue collection. Vehicle and movement validation is in schemas/vehicle.py; auxiliary visitor, bus and camera contracts are in models/documents.py.

Unique indexes cover normalized plates, open visits (partial index on vehicle_id when status=INSIDE), movement event IDs, bus numbers and one pending review per plate/camera/reason. Query indexes cover plate, vehicle, entry/exit times, status and camera.

TTL uses expires_at on completed visits, resolved reviews and audit records. Open visits and pending reviews never expire automatically. MongoDB's TTL monitor runs asynchronously. Existing expiry dates are not retroactively changed when RETENTION_DAYS changes. In-memory storage has no durable retention guarantee.

Seed data is fictional. Seed updates use setOnInsert, preserve operator changes and never reset movement records. There are no sample movement timestamps: demonstrate arrivals through the simulator so statistics reflect real API writes.

For MongoDB run scripts/seed_demo.bat. For memory mode enable SEED_ON_STARTUP and restart the backend; each process has its own disposable database.
