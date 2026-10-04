from pymongo import ASCENDING, DESCENDING, MongoClient


def connect(settings):
    if settings.app_env != "test" and (settings.database_mode == "memory" or settings.use_mock_ai or settings.seed_operational_data):
        raise RuntimeError("Memory storage, mock recognition and synthetic records are restricted to APP_ENV=test. Configure MongoDB for normal operation.")
    if settings.database_mode == "memory":
        import mongomock

        client = mongomock.MongoClient(tz_aware=True)
    else:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=4000, tz_aware=True)
    try:
        client.admin.command("ping")
        db = client[settings.mongodb_database]
        create_indexes(db)
        return client, db
    except Exception:
        client.close()
        raise


def create_indexes(db):
    db.users.create_index("username", unique=True)
    db.users.create_index("email", unique=True)
    db.users.create_index("provider_subject", unique=True, sparse=True)
    db.sessions.create_index("expires_at", expireAfterSeconds=0)
    db.sessions.create_index("user_id")
    db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    db.transport_routes.create_index("route_number", unique=True)
    db.visitors.create_index([("host_department", ASCENDING), ("created_at", DESCENDING)])
    db.bus_trips.create_index("vehicle_id", unique=True, partialFilterExpression={"status": "AWAY"})
    db.bus_trips.create_index([("vehicle_id", ASCENDING), ("departure_time", DESCENDING)])
    db.bus_trips.create_index("expires_at", expireAfterSeconds=0)
    db.vehicles.create_index("number_plate", unique=True)
    db.vehicles.create_index([("status", ASCENDING), ("vehicle_type", ASCENDING)])
    db.vehicle_logs.create_index(
        "vehicle_id", unique=True, partialFilterExpression={"status": "INSIDE"}, name="one_open_visit"
    )
    for key in ("entry_event_id", "exit_event_id"):
        db.vehicle_logs.create_index(key, unique=True, sparse=True)
    for key in ("vehicle_id", "number_plate", "camera_id", "status"):
        db.vehicle_logs.create_index([(key, ASCENDING), ("entry_time", DESCENDING)])
    db.vehicle_logs.create_index([("entry_time", DESCENDING)])
    db.vehicle_logs.create_index([("exit_time", DESCENDING)])
    db.vehicle_logs.create_index(
        [("vehicle_id", ASCENDING), ("exit_camera_id", ASCENDING), ("exit_time", DESCENDING)]
    )
    db.purposes.create_index("purpose_name", unique=True)
    db.visitors.create_index("vehicle_id")
    db.buses.create_index("vehicle_id", unique=True)
    db.buses.create_index("bus_number", unique=True)
    db.cameras.create_index("camera_name", unique=True)
    db.audit_logs.create_index([("time", DESCENDING)])
    db.review_items.create_index([("status", ASCENDING), ("timestamp", DESCENDING)])
    db.review_items.create_index(
        [("plate", ASCENDING), ("camera_id", ASCENDING), ("reason", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "pending"},
    )
    for collection in ("vehicle_logs", "audit_logs", "review_items", "visitors"):
        db[collection].create_index("expires_at", expireAfterSeconds=0)


def public(document):
    if document is None:
        return None
    return {("id" if key == "_id" else key): value for key, value in document.items()}
