import asyncio
from contextlib import suppress
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from app.api.auth import current_user, operator
from app.api.dependencies import operations
from app.database.connection import public
from app.schemas.vehicle import MockRequest
from app.ai.anpr import Detection
from app.services.operations import utcnow

router = APIRouter(tags=["Operations"])


@router.get("/health")
def health(request: Request):
    try:
        request.app.state.client.admin.command("ping")
    except PyMongoError:
        return JSONResponse({"status": "unhealthy", "database": "unavailable"}, status_code=503)
    return {
        "status": "ok",
        "database": request.app.state.settings.database_mode,
        "persistent": request.app.state.settings.database_mode == "mongodb",
    }


@router.get("/dashboard")
def dashboard(ops=Depends(operations), user=Depends(current_user)):
    return ops.dashboard(user)


@router.get("/logs/today")
def today(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ops=Depends(operations),
    user=Depends(current_user),
):
    start, end = ops.today_bounds()
    query = {"$or": [{"entry_time": {"$gte": start, "$lt": end}}, {"exit_time": {"$gte": start, "$lt": end}}]}
    if user["role"] == "department_staff":
        ids = [row["_id"] for row in ops.db.vehicles.find({"department": user.get("department")}, {"_id": 1})]
        query["vehicle_id"] = {"$in": ids}
    return {
        "items": [
            public(row)
            for row in ops.db.vehicle_logs.find(query).sort("entry_time", -1).skip(offset).limit(limit)
        ],
        "total": ops.db.vehicle_logs.count_documents(query),
    }


@router.get("/activity")
def activity(limit: int = Query(default=100, ge=1, le=500), ops=Depends(operations), user=Depends(current_user)):
    ids = None
    if user["role"] == "department_staff":
        ids = [row["_id"] for row in ops.db.vehicles.find({"department": user.get("department")}, {"_id": 1})]
    return ops.activity(limit, ids)


@router.get("/reviews")
def reviews(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ops=Depends(operations),
    user=Depends(operator),
):
    query = {"status": "pending"}
    return {
        "items": [
            public(row)
            for row in ops.db.review_items.find(query).sort("timestamp", -1).skip(offset).limit(limit)
        ],
        "total": ops.db.review_items.count_documents(query),
    }


@router.post("/reviews/{review_id}/dismiss")
async def dismiss(review_id: str, request: Request, ops=Depends(operations), user=Depends(operator)):
    def update():
        row = ops.db.review_items.find_one_and_update(
            {"_id": review_id, "status": "pending"},
            {
                "$set": {
                    "status": "dismissed",
                    "resolved_at": utcnow(),
                    "expires_at": utcnow() + timedelta(days=ops.settings.retention_days),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not row:
            raise HTTPException(404, "Pending review not found")
        ops.audit("review.dismiss", new=row)
        return public(row)

    row = await run_in_threadpool(update)
    await request.app.state.hub.publish("review.resolved", row)
    return row


@router.post("/detections/mock")
async def mock_detection(payload: MockRequest, request: Request, user=Depends(operator)):
    state = request.app.state
    if not state.settings.use_mock_ai:
        raise HTTPException(409, "Mock detections are disabled in real AI mode")
    vehicle = await run_in_threadpool(
        lambda: state.db.vehicles.find_one({"_id": payload.vehicle_id, "status": "active"})
    )
    if not vehicle:
        raise HTTPException(404, "Choose an active vehicle from the registry.")
    detection = Detection(
        plate=vehicle["number_plate"], raw_text=vehicle["number_plate"], confidence=0.97,
        bounding_box=(180, 180, 420, 260), valid=True, processing_time=0.1,
        timestamp=utcnow(), camera_id=f"main-gate-{payload.direction.lower()}", direction=payload.direction,
    )
    camera_id = f"main-gate-{payload.direction.lower()}"
    result = await run_in_threadpool(state.processor.process, detection, camera_id)
    if result["outcome"] == "accepted":
        await state.hub.publish(
            "vehicle.entry" if payload.direction == "IN" else "vehicle.exit", result["log"]
        )
    elif result["outcome"] == "review":
        await state.hub.publish("review.item", result["review"])
    await state.hub.publish("camera.status", {"id": camera_id, "health_status": "mock"})
    return result


@router.websocket("/ws/events")
async def websocket_events(socket: WebSocket):
    if getattr(socket.app.state, "startup_error", None):
        await socket.close(code=1013)
        return
    origin = socket.headers.get("origin")
    if origin and origin not in socket.app.state.settings.cors_origins:
        await socket.close(code=1008)
        return
    token = socket.cookies.get("gatelog_session")
    authorization = socket.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    try:
        if not token:
            raise HTTPException(401, "Sign in required")
        user, session = await run_in_threadpool(socket.app.state.auth.authenticate, token)
        if user["role"] not in ("admin", "security"):
            raise HTTPException(403, "Use scoped polling for department views")
    except HTTPException:
        await socket.close(code=1008)
        return
    await socket.accept()
    hub = socket.app.state.hub
    queue = hub.subscribe()

    async def send():
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                item = {"type": "heartbeat", "data": {}}
            try:
                await run_in_threadpool(socket.app.state.auth.authenticate, token)
            except HTTPException:
                await socket.close(code=1008)
                return
            await socket.send_json(item)

    sender = asyncio.create_task(send())
    try:
        await socket.send_json({"type": "connected", "data": {}})
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
        sender.cancel()
        with suppress(asyncio.CancelledError, RuntimeError, WebSocketDisconnect):
            await sender
