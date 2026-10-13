import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from app.ai.anpr import MockANPRService, RealANPRService
from app.core.config import Settings
from app.database.connection import connect
from app.database.seed import seed
from app.database.transport import SNAPSHOT, seed_transport
from app.routers import anpr, dashboard, vehicles, campus, auth
from app.services.auth import AuthService
from app.services.capture import CaptureWorker
from app.services.detections import DetectionProcessor
from app.services.events import EventHub
from app.services.operations import Operations
from app.services.scan_storage import ScanStorage


class ApiPrefixMiddleware:
    """Allow the API to work when the hosting layer preserves its public /api prefix."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[4:] or "/"
                raw_path = scope.get("raw_path")
                if raw_path and (raw_path == b"/api" or raw_path.startswith(b"/api/")):
                    scope["raw_path"] = raw_path[4:] or b"/"
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings
        app.state.startup_error = None
        try:
            if settings.app_env != "test" and not settings.jwt_secret_key:
                raise RuntimeError("JWT_SECRET_KEY must be configured. Run scripts/bootstrap_env.py locally.")
            if settings.demo_open_access and (
                settings.app_env == "production" or os.getenv("VERCEL") == "1"
            ):
                raise RuntimeError("DEMO_OPEN_ACCESS is forbidden on a public deployment. Configure Firebase Authentication instead.")
            if settings.app_env == "production" and not settings.cookie_secure:
                raise RuntimeError("Production requires COOKIE_SECURE=true and HTTPS.")
            client, db = await run_in_threadpool(connect, settings)
        except (PyMongoError, RuntimeError) as error:
            app.state.startup_error = ("MongoDB is unavailable. Check MONGODB_URI, database permissions and network access. No in-memory fallback is enabled."
                                       if isinstance(error, PyMongoError) else str(error))
            yield
            return
        worker = task = None
        try:
            app.state.settings = settings
            app.state.client, app.state.db = client, db
            app.state.auth = AuthService(db, settings)
            saved_retention = db.settings.find_one({"_id": "retention"})
            if saved_retention:
                settings.retention_days = saved_retention["retention_days"]
            if settings.seed_on_startup:
                await run_in_threadpool(seed, db, settings)
            elif SNAPSHOT.exists() and not db.transport_routes.find_one({}):
                await run_in_threadpool(seed_transport, db)
            app.state.operations = Operations(db, settings)
            app.state.scan_storage = ScanStorage(settings)
            app.state.processor = DetectionProcessor(app.state.operations)
            app.state.anpr = MockANPRService() if settings.use_mock_ai else RealANPRService(settings)
            app.state.image_anpr = RealANPRService(settings)
            app.state.hub = EventHub()
            if settings.run_video_worker:
                worker = CaptureWorker(app.state, asyncio.get_running_loop())
                task = asyncio.create_task(asyncio.to_thread(worker.run))
            yield
        finally:
            if worker:
                worker.stop_event.set()
                await task
            await run_in_threadpool(client.close)

    app = FastAPI(
        title="GateLog",
        version="0.1.0",
        description="Campus vehicle movement and trip-purpose logging",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )
    app.add_middleware(ApiPrefixMiddleware)
    @app.middleware("http")
    async def availability(request, call_next):
        error = getattr(request.app.state, "startup_error", None)
        if error:
            return JSONResponse({"detail": error, "status": "unavailable"}, status_code=503)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    app.include_router(vehicles.router)
    app.include_router(dashboard.router)
    app.include_router(anpr.router)
    app.include_router(campus.router)
    app.include_router(auth.router)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, error: PyMongoError):
        return JSONResponse({"detail": "Database unavailable. Check MongoDB and retry."}, status_code=503)

    return app


app = create_app()
