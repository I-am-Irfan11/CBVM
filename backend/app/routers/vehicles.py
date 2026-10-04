import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.auth import administrator, current_user, operator, guard_vehicle, restricted_vehicle, vehicle_scope
from app.api.dependencies import operations
from app.core.plates import normalize_plate
from app.database.connection import public
from app.schemas.vehicle import Movement, VehicleCreate, VehicleType

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.post("", status_code=201)
def create_vehicle(payload: VehicleCreate, ops=Depends(operations), user=Depends(current_user)):
    return ops.register(payload)


@router.get("")
def list_vehicles(
    search: str = Query(default="", max_length=100),
    vehicle_type: VehicleType | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ops=Depends(operations),
    user=Depends(current_user),
):
    query = vehicle_scope(user)
    if search:
        query["$or"] = [
            {"number_plate": {"$regex": re.escape(normalize_plate(search)), "$options": "i"}},
            {"owner_name": {"$regex": re.escape(search), "$options": "i"}},
        ]
    if vehicle_type:
        query["vehicle_type"] = vehicle_type
    return {
        "items": [
            restricted_vehicle(user, public(row))
            for row in ops.db.vehicles.find(query).sort("number_plate", 1).skip(offset).limit(limit)
        ],
        "total": ops.db.vehicles.count_documents(query),
    }


@router.get("/inside")
def inside(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ops=Depends(operations),
    user=Depends(current_user),
):
    query = {"status": "INSIDE"}
    if user["role"] == "department_staff":
        ids = [row["_id"] for row in ops.db.vehicles.find(vehicle_scope(user), {"_id": 1})]
        query["vehicle_id"] = {"$in": ids}
    return {
        "items": [
            ({**public(row), "owner_name": (ops.db.vehicles.find_one({"_id": row["vehicle_id"]}) or {}).get("owner_name")}
             if user["role"] != "department_staff" else {key: public(row).get(key) for key in
                 ("id", "number_plate", "vehicle_type", "purpose", "entry_time", "status")})
            for row in ops.db.vehicle_logs.find(query).sort("entry_time", -1).skip(offset).limit(limit)
        ],
        "total": ops.db.vehicle_logs.count_documents(query),
    }


@router.get("/by-plate/{plate}")
def by_plate(plate: str, ops=Depends(operations), user=Depends(current_user)):
    row = ops.db.vehicles.find_one({"number_plate": normalize_plate(plate)})
    if not row:
        raise HTTPException(404, "Vehicle not found")
    guard_vehicle(user, row)
    return restricted_vehicle(user, public(row))


@router.get("/{vehicle_id}")
def get_vehicle(vehicle_id: str, ops=Depends(operations), user=Depends(current_user)):
    row = ops.vehicle(vehicle_id)
    guard_vehicle(user, row)
    return restricted_vehicle(user, public(row))


@router.put("/{vehicle_id}")
def update_vehicle(vehicle_id: str, payload: VehicleCreate, ops=Depends(operations), user=Depends(administrator)):
    return ops.update(vehicle_id, payload)


@router.delete("/{vehicle_id}")
def deactivate_vehicle(vehicle_id: str, ops=Depends(operations), user=Depends(administrator)):
    return ops.deactivate(vehicle_id)


async def movement(request, response, ops, vehicle_id, direction, payload):
    result = await run_in_threadpool(ops.move, vehicle_id, direction, payload)
    if not result["duplicate"]:
        if direction == "IN":
            response.status_code = 201
        await request.app.state.hub.publish(
            "vehicle.entry" if direction == "IN" else "vehicle.exit", result["log"]
        )
    return result


@router.post("/{vehicle_id}/entry")
async def entry(
    vehicle_id: str, payload: Movement, request: Request, response: Response, ops=Depends(operations), user=Depends(operator)
):
    return await movement(request, response, ops, vehicle_id, "IN", payload)


@router.post("/{vehicle_id}/exit")
async def exit_vehicle(
    vehicle_id: str, payload: Movement, request: Request, response: Response, ops=Depends(operations), user=Depends(operator)
):
    return await movement(request, response, ops, vehicle_id, "OUT", payload)


@router.get("/{vehicle_id}/history")
def history(
    vehicle_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ops=Depends(operations),
    user=Depends(current_user),
):
    vehicle = ops.vehicle(vehicle_id)
    guard_vehicle(user, vehicle)
    query = {"vehicle_id": vehicle_id}
    return {
        "items": [
            public(row)
            for row in ops.db.vehicle_logs.find(query).sort("entry_time", -1).skip(offset).limit(limit)
        ],
        "total": ops.db.vehicle_logs.count_documents(query),
    }
