"""Campus visitor, transport, review, reporting and administration APIs."""

import csv
import io
from datetime import date, datetime, time as day_time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from app.api.auth import administrator, current_user, operator, restricted_vehicle, vehicle_scope
from app.database.connection import public
from app.schemas.campus import (
    BusInput, CameraInput, PurposeInput, RetentionInput, ReviewAction, UserInput, VisitorInput,
)
from app.schemas.vehicle import Movement, VehicleCreate, VehicleType
from app.services.auth import user_public, password_hash
from app.services.operations import utcnow

router = APIRouter(tags=["Campus operations"])


@router.get("/transport/routes")
def transport_routes(request: Request, user=Depends(current_user)):
    return [public(row) for row in request.app.state.db.transport_routes.find().sort("route_number", 1)]


def audit(ops, action, old=None, new=None):
    ops.audit(action, old, new)


@router.get("/purposes")
def list_purposes(request: Request, include_inactive: bool = False, user=Depends(current_user)):
    query = {} if include_inactive and user["role"] == "admin" else {"active": True}
    return [public(row) for row in request.app.state.db.purposes.find(query).sort("sort_order", 1)]


@router.post("/purposes", status_code=201)
def create_purpose(payload: PurposeInput, request: Request, user=Depends(administrator)):
    row = {"_id": str(uuid4()), **payload.model_dump(), "route": payload.route_number}
    row.pop("route_number", None)
    try:
        request.app.state.db.purposes.insert_one(row)
    except DuplicateKeyError:
        raise HTTPException(409, "That purpose already exists") from None
    audit(request.app.state.operations, "purpose.create", new=row)
    return public(row)


@router.put("/purposes/{purpose_id}")
def update_purpose(purpose_id: str, payload: PurposeInput, request: Request, user=Depends(administrator)):
    db = request.app.state.db
    old = db.purposes.find_one({"_id": purpose_id})
    if not old:
        raise HTTPException(404, "Purpose not found")
    try:
        row = db.purposes.find_one_and_update({"_id": purpose_id}, {"$set": payload.model_dump()},
                                              return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        raise HTTPException(409, "That purpose already exists") from None
    audit(request.app.state.operations, "purpose.update", old, row)
    return public(row)


@router.get("/visitors")
def list_visitors(request: Request, user=Depends(operator), limit: int = Query(100, ge=1, le=500), search: str = ""):
    query = {"$or": [{key: {"$regex": re.escape(search), "$options": "i"}} for key in ("number_plate", "visitor_name", "host_department")]} if search else {}
    return [public(row) for row in request.app.state.db.visitors.find(query).sort("created_at", -1).limit(limit)]


@router.get("/visitors/{visitor_id}")
def visitor_detail(visitor_id: str, request: Request, user=Depends(operator)):
    row = request.app.state.db.visitors.find_one({"_id": visitor_id})
    if not row:
        raise HTTPException(404, "Visitor not found")
    return {"visitor": public(row), "movement": public(request.app.state.db.vehicle_logs.find_one({"_id": row.get("movement_id")}))}


@router.put("/visitors/{visitor_id}")
def visitor_update(visitor_id: str, payload: VisitorInput, request: Request, user=Depends(operator)):
    db = request.app.state.db
    old = db.visitors.find_one({"_id": visitor_id})
    if not old:
        raise HTTPException(404, "Visitor not found")
    if payload.number_plate != old["number_plate"]:
        raise HTTPException(409, "A visit's plate is immutable. Correct the vehicle registry after departure.")
    changes = {k: v for k, v in payload.model_dump().items() if k not in ("camera_id", "review_id", "vehicle_type", "custom_purpose")}
    changes["purpose"] = payload.custom_purpose if payload.purpose == "Other" and payload.custom_purpose else payload.purpose
    changes["updated_at"] = utcnow()
    row = db.visitors.find_one_and_update({"_id": visitor_id}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    audit(request.app.state.operations, "visitor.update", old, row)
    return public(row)


@router.post("/visitors", status_code=201)
async def register_visitor(payload: VisitorInput, request: Request, user=Depends(operator)):
    db, ops = request.app.state.db, request.app.state.operations
    purpose = payload.custom_purpose.strip() if payload.purpose == "Other" and payload.custom_purpose else payload.purpose
    existing = db.vehicles.find_one({"number_plate": payload.number_plate})
    camera = db.cameras.find_one({"_id": payload.camera_id, "direction": {"$in": ["IN", "BOTH"]}})
    if not camera or not camera.get("active", True):
        raise HTTPException(422, "Select an active entry camera")
    if payload.review_id and not db.review_items.find_one({"_id": payload.review_id, "status": "pending"}):
        raise HTTPException(409, "This review has already been resolved or does not exist")
    if existing and existing["vehicle_type"] not in ("visitor", "service", "emergency", "other"):
        raise HTTPException(409, "Use the registered campus vehicle's entry action")
    if existing and db.vehicle_logs.find_one({"vehicle_id": existing["_id"], "status": "INSIDE"}):
        raise HTTPException(409, "This vehicle is already inside")
    now = utcnow()
    visitor_vehicle = VehicleCreate(number_plate=payload.number_plate, vehicle_type=payload.vehicle_type,
                                    owner_name=payload.visitor_name, department=payload.host_department)
    if existing:
        vehicle = ops.update(existing["_id"], visitor_vehicle)
    else:
        vehicle = ops.register(visitor_vehicle)
    visitor = {
        "_id": str(uuid4()), "vehicle_id": vehicle["id"], "number_plate": payload.number_plate,
        "visitor_name": payload.visitor_name,
        "organization": payload.organization, "phone": payload.phone,
        "host_department": payload.host_department, "person_to_visit": payload.person_to_visit,
        "expected_exit_time": payload.expected_exit_time, "purpose": purpose, "created_at": now,
        "created_by": user["_id"],
    }
    result = ops.move(vehicle["id"], "IN", Movement(camera_id=payload.camera_id, purpose=purpose), verified_transition=True)
    if result["duplicate"]:
        raise HTTPException(409, "This visitor entry was already recorded")
    visitor["movement_id"] = result["log"]["id"]
    db.visitors.insert_one(visitor)
    audit(ops, "visitor.register", new={"visitor_id": visitor["_id"], "vehicle_id": vehicle["id"],
        "number_plate": payload.number_plate, "purpose": purpose,
        "host_department": payload.host_department, "movement_id": result["log"]["id"]})
    if payload.review_id:
        review = db.review_items.find_one_and_update(
            {"_id": payload.review_id, "status": "pending"},
            {"$set": {"status": "confirmed", "resolved_at": now, "resolved_by": user["_id"],
                      "vehicle_id": vehicle["id"], "expires_at": now + timedelta(days=ops.settings.retention_days)}},
            return_document=ReturnDocument.AFTER,
        )
        if review:
            audit(ops, "review.confirm_visitor", new=review)
    await request.app.state.hub.publish("visitor.registered", {"visitor": public(visitor), "movement": result["log"]})
    await request.app.state.hub.publish("vehicle.entry", result["log"])
    return {"visitor": public(visitor), "vehicle": vehicle, "movement": result["log"]}


@router.get("/buses")
def list_buses(request: Request, user=Depends(current_user)):
    rows = []
    for bus in request.app.state.db.buses.find().sort("bus_number", 1):
        vehicle = request.app.state.db.vehicles.find_one({"_id": bus["vehicle_id"]})
        if user["role"] == "department_staff" and (not vehicle or vehicle.get("department") != user.get("department")):
            continue
        rows.append({**public(bus), "vehicle": restricted_vehicle(user, public(vehicle)) if vehicle else None,
                     "active_trip": public(request.app.state.db.bus_trips.find_one(
                         {"vehicle_id": bus["vehicle_id"], "status": "AWAY"}))})
    return rows


@router.post("/buses", status_code=201)
def create_bus(payload: BusInput, request: Request, user=Depends(administrator)):
    db = request.app.state.db
    vehicle = db.vehicles.find_one({"_id": payload.vehicle_id, "vehicle_type": "bus"})
    if not vehicle:
        raise HTTPException(422, "Select a registered bus vehicle")
    row_data = payload.model_dump()
    row_data["route"] = row_data.pop("route_number")
    row = {"_id": str(uuid4()), **row_data}
    try:
        db.buses.insert_one(row)
    except DuplicateKeyError:
        raise HTTPException(409, "This bus or vehicle already has a bus record") from None
    audit(request.app.state.operations, "bus.create", new=row)
    return public(row)


@router.get("/buses/{bus_id}/trips")
def bus_history(bus_id: str, request: Request, user=Depends(operator)):
    if not request.app.state.db.buses.find_one({"_id": bus_id}):
        raise HTTPException(404, "Bus not found")
    return [public(row) for row in request.app.state.db.bus_trips.find({"bus_id": bus_id}).sort("departure_time", -1).limit(500)]


@router.put("/buses/{bus_id}")
def update_bus(bus_id: str, payload: BusInput, request: Request, user=Depends(administrator)):
    db = request.app.state.db
    old = db.buses.find_one({"_id": bus_id})
    if not old:
        raise HTTPException(404, "Bus not found")
    if db.bus_trips.find_one({"bus_id": bus_id, "status": "AWAY"}):
        raise HTTPException(409, "Complete the active bus trip before editing this bus")
    vehicle = db.vehicles.find_one({"_id": payload.vehicle_id, "vehicle_type": "bus"})
    if not vehicle:
        raise HTTPException(422, "Select a registered bus vehicle")
    changes = payload.model_dump()
    changes["route"] = changes.pop("route_number")
    try:
        row = db.buses.find_one_and_update({"_id": bus_id}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        raise HTTPException(409, "This bus or vehicle already has a bus record") from None
    audit(request.app.state.operations, "bus.update", old, row)
    return public(row)


@router.post("/buses/{bus_id}/trips", status_code=201)
async def depart_bus(bus_id: str, request: Request, purpose: str = Query(min_length=1, max_length=120),
                     note: str = Query(default="", max_length=500), user=Depends(operator)):
    db, ops = request.app.state.db, request.app.state.operations
    bus = db.buses.find_one({"_id": bus_id, "status": "active"})
    if not bus:
        raise HTTPException(404, "Active bus not found")
    if db.bus_trips.find_one({"vehicle_id": bus["vehicle_id"], "status": "AWAY"}):
        raise HTTPException(409, "This bus is already away")
    opened = db.vehicle_logs.find_one({"vehicle_id": bus["vehicle_id"], "status": "INSIDE"})
    if not opened:
        raise HTTPException(409, "Record the bus entry before starting a campus departure")
    now = utcnow()
    trip = {"_id": str(uuid4()), "vehicle_id": bus["vehicle_id"], "bus_id": bus_id,
            "bus_number": bus["bus_number"], "route": bus["route"], "purpose": purpose,
            "note": note, "departure_time": now, "return_time": None, "status": "AWAY"}
    try:
        db.bus_trips.insert_one(trip)
    except DuplicateKeyError:
        raise HTTPException(409, "This bus is already away") from None
    try:
        movement = await run_in_threadpool(
            ops.move, bus["vehicle_id"], "OUT",
            Movement(camera_id="main-gate-out", purpose=purpose),
            verified_transition=True,
        )
    except Exception:
        db.bus_trips.delete_one({"_id": trip["_id"], "status": "AWAY"})
        raise
    audit(ops, "bus.depart", new=trip)
    await request.app.state.hub.publish("vehicle.exit", movement["log"])
    await request.app.state.hub.publish("bus.departed", public(trip))
    return public(trip)


@router.post("/buses/{bus_id}/trips/return")
async def return_bus(bus_id: str, request: Request, user=Depends(operator)):
    db, ops = request.app.state.db, request.app.state.operations
    trip = db.bus_trips.find_one({"bus_id": bus_id, "status": "AWAY"})
    if not trip:
        raise HTTPException(404, "No open trip for this bus")
    now = utcnow()
    movement = await run_in_threadpool(
        ops.move, trip["vehicle_id"], "IN",
        Movement(camera_id="main-gate-in", purpose=trip["purpose"]),
        verified_transition=True,
    )
    row = db.bus_trips.find_one_and_update({"_id": trip["_id"], "status": "AWAY"},
        {"$set": {"status": "RETURNED", "return_time": now,
                   "duration_seconds": (now - trip["departure_time"]).total_seconds(),
                   "expires_at": now + timedelta(days=ops.settings.retention_days)}},
        return_document=ReturnDocument.AFTER)
    audit(ops, "bus.return", trip, row)
    await request.app.state.hub.publish("vehicle.entry", movement["log"])
    await request.app.state.hub.publish("bus.returned", public(row))
    return public(row)


@router.get("/cameras")
def list_cameras(request: Request, user=Depends(operator)):
    return [public(row) for row in request.app.state.db.cameras.find()]


@router.post("/cameras", status_code=201)
def create_camera(payload: CameraInput, request: Request, user=Depends(administrator)):
    camera = {"_id": str(uuid4()), **payload.model_dump(), "health_status": "idle", "last_frame_time": None,
              "source": payload.source}
    try:
        request.app.state.db.cameras.insert_one(camera)
    except DuplicateKeyError:
        raise HTTPException(409, "Camera name already exists") from None
    audit(request.app.state.operations, "camera.create", new=camera)
    return public(camera)


@router.put("/cameras/{camera_id}")
def update_camera(camera_id: str, payload: CameraInput, request: Request, user=Depends(administrator)):
    db = request.app.state.db
    old = db.cameras.find_one({"_id": camera_id})
    if not old:
        raise HTTPException(404, "Camera not found")
    try:
        row = db.cameras.find_one_and_update({"_id": camera_id}, {"$set": payload.model_dump()},
                                             return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        raise HTTPException(409, "Camera name already exists") from None
    audit(request.app.state.operations, "camera.update", old, row)
    return public(row)


@router.get("/reviews/{review_id}")
def get_review(review_id: str, request: Request, user=Depends(operator)):
    review = request.app.state.db.review_items.find_one({"_id": review_id})
    if not review:
        raise HTTPException(404, "Review not found")
    vehicle = request.app.state.db.vehicles.find_one({"number_plate": review.get("plate")})
    return {"review": public(review), "vehicle": public(vehicle) if vehicle else None}


@router.post("/reviews/{review_id}/resolve")
async def resolve_review(review_id: str, payload: ReviewAction, request: Request, user=Depends(operator)):
    db, ops = request.app.state.db, request.app.state.operations
    old = db.review_items.find_one({"_id": review_id, "status": "pending"})
    if not old:
        raise HTTPException(404, "Pending review not found")
    now = utcnow()
    changes = {"status": "rejected" if payload.action == "reject" else "confirmed", "resolved_at": now,
               "resolved_by": user["_id"], "resolution_note": payload.note,
               "expires_at": now + timedelta(days=ops.settings.retention_days)}
    movement = None
    if payload.action == "confirm":
        from app.core.plates import normalize_plate, valid_plate
        plate = normalize_plate(payload.number_plate or old.get("plate", ""))
        if not valid_plate(plate):
            raise HTTPException(422, "Correct the plate to a valid Indian registration")
        vehicle = db.vehicles.find_one({"number_plate": plate, "status": "active"})
        if not vehicle:
            raise HTTPException(404, "Register this vehicle or visitor before confirming the movement")
        direction = old.get("direction") or "IN"
        camera = db.cameras.find_one({"_id": old["camera_id"]})
        if camera:
            direction = camera["direction"] if camera["direction"] in ("IN", "OUT") else payload.direction
        result = ops.move(vehicle["_id"], direction,
                          Movement(camera_id=old["camera_id"], purpose=payload.purpose, custom_purpose=payload.custom_purpose,
                                   event_id=f"review:{review_id}",
                                   detection_confidence=1.0), detection=None)
        movement = result["log"]
        changes["vehicle_id"] = vehicle["_id"]
        changes["corrected_plate"] = plate
        changes["custom_purpose"] = payload.custom_purpose if payload.purpose == "Other" else None
    row = db.review_items.find_one_and_update({"_id": review_id, "status": "pending"}, {"$set": changes},
                                              return_document=ReturnDocument.AFTER)
    audit(ops, f"review.{payload.action}", old, row)
    await request.app.state.hub.publish("review.resolved", public(row))
    if movement:
        await request.app.state.hub.publish("vehicle.entry" if movement["status"] == "INSIDE" else "vehicle.exit", movement)
    return {"review": public(row), "movement": movement}


@router.get("/analytics")
def analytics(request: Request, user=Depends(current_user), days: int = Query(30, ge=1, le=366),
              vehicle_type: str | None = None, purpose: str | None = None, status: str | None = None,
              date_from: date | None = None, date_to: date | None = None):
    db = request.app.state.db
    start = datetime.combine(date_from, day_time.min, tzinfo=ZoneInfo(request.app.state.settings.campus_timezone)).astimezone(timezone.utc) if date_from else utcnow() - timedelta(days=days)
    end = datetime.combine(date_to + timedelta(days=1), day_time.min, tzinfo=ZoneInfo(request.app.state.settings.campus_timezone)).astimezone(timezone.utc) if date_to else utcnow()
    if start > end:
        raise HTTPException(422, "Start date must be before end date")
    query = {"$or": [{"entry_time": {"$gte": start, "$lt": end}}, {"exit_time": {"$gte": start, "$lt": end}}]}
    if vehicle_type:
        query["vehicle_type"] = vehicle_type
    if purpose:
        query["purpose"] = purpose
    if status:
        query["status"] = status
    if user["role"] == "department_staff":
        vehicle_ids = [row["_id"] for row in db.vehicles.find(vehicle_scope(user), {"_id": 1})]
        query["vehicle_id"] = {"$in": vehicle_ids}
    rows = list(db.vehicle_logs.find(query))
    per_day, entry_hours, exit_hours, types, purposes = {}, [0] * 24, [0] * 24, {}, {}
    for row in rows:
        zone = ZoneInfo(request.app.state.settings.campus_timezone)
        for key, counter, hours in (("entry_time", "entries", entry_hours), ("exit_time", "exits", exit_hours)):
            moment = row.get(key)
            if moment and start <= moment < end:
                local = moment.astimezone(zone)
                day = local.date().isoformat()
                per_day.setdefault(day, {"date": day, "entries": 0, "exits": 0})[counter] += 1
                hours[local.hour] += 1
        types[row["vehicle_type"]] = types.get(row["vehicle_type"], 0) + 1
        purposes[row["purpose"]] = purposes.get(row["purpose"], 0) + 1
    complete = [row["duration_seconds"] for row in rows if row.get("duration_seconds") is not None]
    visits = len(rows)
    return {"days": sorted(per_day.values(), key=lambda x: x["date"]), "entries_by_hour": entry_hours,
            "exits_by_hour": exit_hours, "average_stay_seconds": sum(complete) / len(complete) if complete else None,
            "visitor_count": sum(row["vehicle_type"] == "visitor" for row in rows),
            "bus_movements": sum(row["vehicle_type"] == "bus" for row in rows),
            "student_movements": sum(row["vehicle_type"] == "student" for row in rows),
            "service_movements": sum(row["vehicle_type"] == "service" for row in rows),
            "vehicle_types": types, "purposes": purposes, "movement_count": visits,
            "date_from": start.date().isoformat(), "date_to": end.date().isoformat()}


@router.get("/reports.csv")
def export_report(request: Request, user=Depends(current_user), vehicle_type: VehicleType | None = None,
                  purpose: str | None = None, status: str | None = None,
                  days: int = Query(30, ge=1, le=366), date_from: date | None = None,
                  date_to: date | None = None):
    query = {}
    if vehicle_type:
        query["vehicle_type"] = vehicle_type
    if purpose:
        query["purpose"] = purpose
    if status:
        query["status"] = status
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "Start date must be before end date")
    zone = ZoneInfo(request.app.state.settings.campus_timezone)
    start = (datetime.combine(date_from, day_time.min, tzinfo=zone).astimezone(timezone.utc)
             if date_from else utcnow() - timedelta(days=days))
    end = (datetime.combine(date_to + timedelta(days=1), day_time.min, tzinfo=zone).astimezone(timezone.utc)
           if date_to else utcnow())
    if start >= end:
        raise HTTPException(422, "Start date must be before end date")
    window = {"$gte": start, "$lt": end}
    query["$or"] = [{"entry_time": window}, {"exit_time": window}]
    rows = request.app.state.db.vehicle_logs.find(query).sort("entry_time", -1)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["plate", "vehicle_type", "purpose", "entry_time", "exit_time", "duration_seconds", "status"])
    for row in rows:
        if user["role"] == "department_staff":
            vehicle = request.app.state.db.vehicles.find_one({"_id": row["vehicle_id"]})
            if not vehicle or vehicle.get("department") != user.get("department"):
                continue
        values = [row.get("number_plate"), row.get("vehicle_type"), row.get("purpose"), row.get("entry_time"),
                  row.get("exit_time"), row.get("duration_seconds"), row.get("status")]
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip()[:1] in "=+-@" else value for value in values])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=gatelog-report.csv"})


@router.get("/audit")
def audit_logs(request: Request, user=Depends(administrator), limit: int = Query(100, ge=1, le=500)):
    return [public(row) for row in request.app.state.db.audit_logs.find().sort("time", -1).limit(limit)]


@router.get("/settings/retention")
def get_retention(request: Request, user=Depends(administrator)):
    return {"retention_days": request.app.state.settings.retention_days}


@router.put("/settings/retention")
def set_retention(payload: RetentionInput, request: Request, user=Depends(administrator)):
    old = request.app.state.settings.retention_days
    request.app.state.settings.retention_days = payload.retention_days
    request.app.state.db.settings.update_one({"_id": "retention"}, {"$set": {"retention_days": payload.retention_days}}, upsert=True)
    audit(request.app.state.operations, "retention.update", {"retention_days": old}, payload.model_dump())
    return payload.model_dump()


@router.get("/users")
def list_users(request: Request, user=Depends(administrator)):
    return [user_public(row) for row in request.app.state.db.users.find().sort("username", 1)]


@router.post("/users", status_code=201)
def create_user(payload: UserInput, request: Request, user=Depends(administrator)):
    data = payload.model_dump()
    password = data.pop("password")
    row = {"_id": str(uuid4()), **data, "auth_provider": "firebase-invited",
           "created_at": utcnow(), "updated_at": utcnow()}
    if request.app.state.settings.app_env == "test" and password:
        row["auth_provider"] = "local"
        row["password_hash"] = password_hash(password)
    try:
        request.app.state.db.users.insert_one(row)
    except DuplicateKeyError:
        raise HTTPException(409, "Username or email already exists") from None
    audit(request.app.state.operations, "user.create", new=row)
    return user_public(row)


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserInput, request: Request, user=Depends(administrator)):
    db = request.app.state.db
    old = db.users.find_one({"_id": user_id})
    if not old:
        raise HTTPException(404, "User not found")
    changes = payload.model_dump()
    password = changes.pop("password")
    if request.app.state.settings.app_env == "test" and password:
        changes["password_hash"] = password_hash(password)
    if user_id == user["_id"] and (not payload.active or payload.role != "admin"):
        raise HTTPException(409, "You cannot disable or demote your own administrator account")
    changes["updated_at"] = utcnow()
    if not payload.active or payload.role != old["role"] or payload.department != old.get("department"):
        db.sessions.delete_many({"user_id": user_id})
    try:
        row = db.users.find_one_and_update({"_id": user_id}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        raise HTTPException(409, "Username or email already exists") from None
    audit(request.app.state.operations, "user.update", old, row)
    return user_public(row)
