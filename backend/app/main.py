import asyncio
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
from app.routers import anpr, dashboard, vehicles
from app.services.capture import CaptureWorker
from app.services.detections import DetectionProcessor
from app.services.events import EventHub
from app.services.operations import Operations


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        client, db = await run_in_threadpool(connect, settings)
        worker = task = None
        try:
            app.state.settings = settings
            app.state.client, app.state.db = client, db
            if settings.seed_on_startup:
                await run_in_threadpool(seed, db, settings)
            app.state.operations = Operations(db, settings)
            app.state.processor = DetectionProcessor(app.state.operations)
            app.state.anpr = MockANPRService() if settings.use_mock_ai else RealANPRService(settings)
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
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(vehicles.router)
    app.include_router(dashboard.router)
    app.include_router(anpr.router)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, error: PyMongoError):
        return JSONResponse({"detail": "Database unavailable. Check MongoDB and retry."}, status_code=503)

    return app


app = create_app()
