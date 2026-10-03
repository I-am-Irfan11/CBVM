from uuid import uuid4

from pymongo import ReturnDocument

from app.database.connection import public
from app.schemas.vehicle import Movement


class DetectionProcessor:
    def __init__(self, operations):
        self.ops = operations

    def process(self, detection, camera_id):
        from fastapi import HTTPException

        db = self.ops.db
        camera = db.cameras.find_one({"_id": camera_id})
        if not camera:
            raise HTTPException(404, "Camera not found")
        db.cameras.update_one(
            {"_id": camera_id},
            {
                "$set": {
                    "last_frame_time": detection.timestamp,
                    "health_status": "mock" if self.ops.settings.use_mock_ai else "online",
                }
            },
        )
        vehicle = db.vehicles.find_one({"number_plate": detection.plate})
        reason = None
        if not detection.valid or detection.confidence < self.ops.settings.ocr_confidence_threshold:
            reason = "Low confidence or unsupported plate format"
        elif not vehicle:
            reason = "Unregistered vehicle"
        elif vehicle["status"] != "active":
            reason = "Inactive vehicle"
        if reason is None:
            try:
                direction = detection.direction or camera["direction"]
                if direction not in ("IN", "OUT"):
                    raise HTTPException(422, "Gate crossing direction requires review")
                result = self.ops.move(
                    vehicle["_id"],
                    direction,
                    Movement(
                        camera_id=camera_id,
                        detection_confidence=detection.confidence,
                        timestamp=detection.timestamp,
                    ),
                    detection=detection,
                )
                return {
                    "outcome": "duplicate" if result["duplicate"] else "accepted",
                    **result,
                    "detection": detection.model_dump(),
                }
            except HTTPException as error:
                reason = str(error.detail)
        with self.ops.lock:
            item = db.review_items.find_one_and_update(
                {"plate": detection.plate, "camera_id": camera_id, "reason": reason, "status": "pending"},
                {
                    "$setOnInsert": {
                        "_id": str(uuid4()),
                        **detection.model_dump(),
                        "camera_id": camera_id,
                        "reason": reason,
                        "status": "pending",
                    },
                    "$set": {"last_seen": detection.timestamp},
                    "$inc": {"sightings": 1},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        return {"outcome": "review", "review": public(item), "detection": detection.model_dump()}
