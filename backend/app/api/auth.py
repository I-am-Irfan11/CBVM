from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.core.identity import actor


async def current_user(request: Request):
    assertion = request.headers.get("cf-access-jwt-assertion")
    if assertion:
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in request.app.state.settings.cors_origins:
            raise HTTPException(403, "Origin is not allowed")
        user = await run_in_threadpool(request.app.state.auth.cloudflare_login, assertion)
        request.state.user, request.state.session = user, None
        actor.set({"user_id": user["_id"], "role": user["role"]})
        return user
    raise HTTPException(401, "Sign in with your Google account through Cloudflare Access.",
                        headers={"WWW-Authenticate": "Bearer"})


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
