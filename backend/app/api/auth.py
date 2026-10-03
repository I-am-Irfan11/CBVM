import secrets

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.core.identity import actor


async def current_user(request: Request):
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if origin and origin not in settings.cors_origins:
            raise HTTPException(403, "Origin is not allowed")

    token = request.cookies.get("gatelog_session")
    if not token:
        raise HTTPException(401, "Sign in with Google to continue.", headers={"WWW-Authenticate": "Bearer"})

    user, session = await run_in_threadpool(request.app.state.auth.authenticate, token)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not secrets.compare_digest(csrf, session.get("csrf", "")):
            raise HTTPException(403, "Session verification failed. Refresh the page and try again.")
    request.state.user, request.state.session = user, session
    actor.set({"user_id": user["_id"], "role": user["role"]})
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
