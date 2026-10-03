from fastapi import Depends, HTTPException, Request

from app.core.identity import actor


async def current_user(request: Request):
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if origin and origin not in settings.cors_origins:
            raise HTTPException(403, "Origin is not allowed")

    user = {
        "_id": "public:anonymous",
        "username": "public",
        "full_name": "Public access",
        "role": "admin",
        "department": None,
        "active": True,
    }
    request.state.user, request.state.session = user, None
    actor.set({"user_id": user["_id"], "role": "public"})
    return user


def roles(*allowed):
    async def require(user=Depends(current_user)):
        if user["role"] not in allowed:
            raise HTTPException(403, "Your role does not permit this operation")
        return user
    return require


operator = roles("admin", "security")
administrator = roles("admin")


def vehicle_scope(user):
    return {"department": user.get("department")} if user["role"] == "department_staff" else {}


def guard_vehicle(user, vehicle):
    if user["role"] == "department_staff" and vehicle.get("department") != user.get("department"):
        raise HTTPException(403, "This vehicle is outside your department")


def restricted_vehicle(user, row):
    if user["role"] != "department_staff":
        return row
    return {key: row.get(key) for key in ("id", "number_plate", "vehicle_type", "department", "vehicle_model", "status")}
