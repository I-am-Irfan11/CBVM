import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.core.config import ROOT, Settings
from app.database.connection import connect
from app.database.transport import SNAPSHOT, seed_transport
from app.models.documents import Bus, Camera


def seed(db, settings):
    if settings.seed_operational_data and settings.app_env != "test":
        raise RuntimeError("Synthetic operational records are permitted only in isolated tests")
    now = datetime.now(timezone.utc)
    if settings.seed_operational_data:
        for source in json.loads((ROOT / "database/seed/vehicles.json").read_text()):
            row = dict(source)
            row["_id"] = row.pop("id")
            row.update(status="active", created_at=now, updated_at=now)
            db.vehicles.update_one({"number_plate": row["number_plate"]}, {"$setOnInsert": row}, upsert=True)
        for index, name in enumerate(
            [
            "Student Pickup",
            "Student Drop",
            "College Activity",
            "NSS Trip",
            "Industry Visit",
            "Industrial Training",
            "Staff Duty",
            "Official College Work",
            "Maintenance",
            "Delivery",
            "Guest Visit",
            "Parent Visit",
            "Event",
            "Emergency",
            "Other",
            "Campus visit",
            "Classes",
            "Bus route",
            ]
        ):
            db.purposes.update_one(
                {"purpose_name": name},
                {"$setOnInsert": {
                    "_id": f"purpose-{uuid5(NAMESPACE_URL, name).hex}", "purpose_name": name,
                    "active": True, "sort_order": index,
                }},
                upsert=True,
            )
        for number in (1, 2):
            vehicle = db.vehicles.find_one({"number_plate": f"TN01BC900{number}"})
            bus = Bus(vehicle_id=vehicle["_id"], bus_number=f"C-{number:02}",
                      route=f"Demo route {number}", driver_name=f"Demo Driver {number:02}", capacity=48)
            db.buses.update_one(
                {"vehicle_id": vehicle["_id"]},
                {"$setOnInsert": {"_id": f"bus-{number}", **bus.model_dump()}}, upsert=True,
            )
    for direction in ("IN", "OUT"):
        camera = Camera(camera_name=f"Main gate · {direction}", location="Main gate", direction=direction,
                        health_status="mock" if settings.use_mock_ai else "idle")
        db.cameras.update_one(
            {"_id": f"main-gate-{direction.lower()}"}, {"$setOnInsert": camera.model_dump()}, upsert=True
        )
    if SNAPSHOT.exists():
        seed_transport(db)


if __name__ == "__main__":
    settings = Settings()
    if settings.database_mode == "memory":
        print(
            "Memory mode: seeding is performed in the running server at startup; this process would be ephemeral."
        )
    else:
        client, db = connect(settings)
        try:
            seed(db, settings)
            print(f"Seeded {db.vehicles.count_documents({})} vehicles (existing records preserved).")
        finally:
            client.close()
