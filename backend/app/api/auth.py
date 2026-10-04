from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
import secrets

from app.core.identity import actor
from app.services.auth import demo_user


async def current_user(request: Request):
    settings = request.app.state.settings
    if settings.demo_open_access:
        # Demo entrance: no credential, session or CSRF check is performed. Only
        # reachable when DEMO_OPEN_ACCESS is explicitly enabled.
        user = demo_user()
        request.state.user, request.state.session = user, None
        actor.set({"user_id": user["_id"], "role": user["role"]})
        return user
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if origin and origin not in settings.cors_origins:
            raise HTTPException(403, "Origin is not allowed")

    authorization = request.headers.get("authorization", "")
    bearer = authorization.startswith("Bearer ")
    token = authorization[7:] if bearer else request.cookies.get("gatelog_session")
    if not token:
        raise HTTPException(401, "Sign in to access campus records")
    user, session = await run_in_threadpool(request.app.state.auth.authenticate, token)
    if not bearer and request.method not in ("GET", "HEAD", "OPTIONS"):
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"]):
            raise HTTPException(403, "Session verification failed. Refresh and try again.")
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
