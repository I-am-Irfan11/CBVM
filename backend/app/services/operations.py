from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.database.connection import public


def utcnow():
    return datetime.now(timezone.utc)


class Operations:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        # Phase 1 runs one worker. DB uniqueness also guards open visits across processes.
        self.lock = RLock()

    def audit(self, action, old=None, new=None):
        now = utcnow()
        self.db.audit_logs.insert_one(
            {
                "_id": str(uuid4()),
                "user": "local-operator",
                "action": action,
                "time": now,
                "old_values": public(old),
                "new_values": public(new),
                "expires_at": now + timedelta(days=self.settings.retention_days),
            }
        )

    def vehicle(self, vehicle_id):
        vehicle = self.db.vehicles.find_one({"_id": vehicle_id})
        if not vehicle:
            raise HTTPException(404, "Vehicle not found")
        return vehicle

    def register(self, payload):
        now = utcnow()
        row = {"_id": str(uuid4()), **payload.model_dump(), "created_at": now, "updated_at": now}
        try:
            self.db.vehicles.insert_one(row)
        except DuplicateKeyError:
            raise HTTPException(409, "That registration is already in the registry") from None
        self.audit("vehicle.register", new=row)
        return public(row)

    def update(self, vehicle_id, payload):
        with self.lock:
            old = self.vehicle(vehicle_id)
            changes = payload.model_dump()
            if self.db.vehicle_logs.find_one({"vehicle_id": vehicle_id, "status": "INSIDE"}):
                if changes["number_plate"] != old["number_plate"] or changes["status"] == "inactive":
                    raise HTTPException(
                        409, "Record an exit before changing the plate or deactivating this vehicle"
                    )
            changes["updated_at"] = utcnow()
            try:
                row = self.db.vehicles.find_one_and_update(
                    {"_id": vehicle_id}, {"$set": changes}, return_document=ReturnDocument.AFTER
                )
            except DuplicateKeyError:
                raise HTTPException(409, "That registration is already in the registry") from None
            self.audit("vehicle.update", old, row)
            return public(row)

    def deactivate(self, vehicle_id):
        from app.schemas.vehicle import VehicleCreate

        vehicle = self.vehicle(vehicle_id)
        payload = VehicleCreate(**{key: vehicle.get(key) for key in VehicleCreate.model_fields})
        payload.status = "inactive"
        return self.update(vehicle_id, payload)

    def move(self, vehicle_id, direction, payload, detection=None):
        with self.lock:
            vehicle = self.vehicle(vehicle_id)
            camera = self.db.cameras.find_one({"_id": payload.camera_id})
            if not camera:
                raise HTTPException(404, "Camera not found")
            if camera["direction"] != direction:
                raise HTTPException(422, "Camera direction does not match this movement")
            if payload.detection_confidence < self.settings.ocr_confidence_threshold:
                raise HTTPException(422, "Detection confidence requires review")
            now = payload.timestamp or utcnow()
            if now > utcnow() + timedelta(seconds=5):
                raise HTTPException(422, "Movement timestamp is in the future")
            event_field = "entry_event_id" if direction == "IN" else "exit_event_id"
            if payload.event_id:
                previous = self.db.vehicle_logs.find_one({event_field: payload.event_id})
                if previous:
                    if previous["vehicle_id"] != vehicle_id:
                        raise HTTPException(409, "Event ID belongs to a different vehicle")
                    return {"duplicate": True, "log": public(previous)}
            opened = self.db.vehicle_logs.find_one({"vehicle_id": vehicle_id, "status": "INSIDE"})
            latest = self.db.vehicle_logs.find_one({"vehicle_id": vehicle_id}, sort=[("entry_time", -1)])
            if direction == "IN" and opened:
                return {"duplicate": True, "log": public(opened)}
            if latest:
                last_time = latest.get("exit_time") or latest["entry_time"]
                if now < last_time:
                    raise HTTPException(422, "Movement predates the latest vehicle event")
            time_field = "entry_time" if direction == "IN" else "exit_time"
            camera_field = "camera_id" if direction == "IN" else "exit_camera_id"
            last_same_direction = self.db.vehicle_logs.find_one(
                {"vehicle_id": vehicle_id, camera_field: payload.camera_id, time_field: {"$ne": None}},
                sort=[(time_field, -1)],
            )
            if last_same_direction:
                elapsed = (now - last_same_direction[time_field]).total_seconds()
                if 0 <= elapsed < self.settings.duplicate_cooldown_seconds:
                    return {"duplicate": True, "log": public(last_same_direction)}
            if direction == "IN":
                if vehicle["status"] != "active":
                    raise HTTPException(409, "Inactive vehicles cannot enter")
                row = {
                    "_id": str(uuid4()),
                    "vehicle_id": vehicle_id,
                    "number_plate": vehicle["number_plate"],
                    "vehicle_type": vehicle["vehicle_type"],
                    "entry_time": now,
                    "exit_time": None,
                    "duration_seconds": None,
                    "purpose": payload.purpose,
                    "camera_id": payload.camera_id,
                    "tracking_id": payload.tracking_id,
                    "detection_confidence": payload.detection_confidence,
                    "status": "INSIDE",
                    "entry_event_id": payload.event_id or str(uuid4()),
                }
                if detection is not None:
                    row["entry_detection"] = detection.model_dump()
                try:
                    self.db.vehicle_logs.insert_one(row)
                except DuplicateKeyError:
                    row = self.db.vehicle_logs.find_one({"vehicle_id": vehicle_id, "status": "INSIDE"})
                    if row:
                        return {"duplicate": True, "log": public(row)}
                    raise HTTPException(409, "Duplicate movement event") from None
                self.audit("vehicle.entry", new=row)
            else:
                if not opened:
                    raise HTTPException(409, "Vehicle has no open visit")
                seconds = (now - opened["entry_time"]).total_seconds()
                if seconds < 0:
                    raise HTTPException(422, "Exit cannot precede entry")
                row = self.db.vehicle_logs.find_one_and_update(
                    {"_id": opened["_id"], "status": "INSIDE"},
                    {
                        "$set": {
                            "exit_time": now,
                            "duration_seconds": seconds,
                            "status": "COMPLETED",
                            "exit_camera_id": payload.camera_id,
                            "exit_event_id": payload.event_id or str(uuid4()),
                            "exit_detection": detection.model_dump() if detection is not None else None,
                            "expires_at": now + timedelta(days=self.settings.retention_days),
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if row is None:
                    return {
                        "duplicate": True,
                        "log": public(self.db.vehicle_logs.find_one({"_id": opened["_id"]})),
                    }
                self.audit("vehicle.exit", opened, row)
            return {"duplicate": False, "log": public(row)}

    def today_bounds(self):
        local = utcnow().astimezone(ZoneInfo(self.settings.campus_timezone))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)

    def dashboard(self):
        start, end = self.today_bounds()
        window = {"$gte": start, "$lt": end}
        return {
            "registered_vehicles": self.db.vehicles.count_documents({"status": "active"}),
            "currently_inside": self.db.vehicle_logs.count_documents({"status": "INSIDE"}),
            "entries_today": self.db.vehicle_logs.count_documents({"entry_time": window}),
            "exits_today": self.db.vehicle_logs.count_documents({"exit_time": window}),
            "pending_reviews": self.db.review_items.count_documents({"status": "pending"}),
            "recent_activity": self.activity(10),
            "cameras": [public(row) for row in self.db.cameras.find()],
            "database_mode": self.settings.database_mode,
            "mock_ai": self.settings.use_mock_ai,
            "campus_timezone": self.settings.campus_timezone,
        }

    def activity(self, limit=100):
        events = []
        for field, kind in (("entry_time", "vehicle.entry"), ("exit_time", "vehicle.exit")):
            for row in self.db.vehicle_logs.find({field: {"$ne": None}}).sort(field, -1).limit(limit):
                events.append(
                    {
                        "id": f"{row['_id']}-{kind}",
                        "type": kind,
                        "timestamp": row[field],
                        "number_plate": row["number_plate"],
                        "vehicle_type": row["vehicle_type"],
                        "purpose": row["purpose"],
                        "vehicle_id": row["vehicle_id"],
                    }
                )
        return sorted(events, key=lambda row: row["timestamp"], reverse=True)[:limit]
