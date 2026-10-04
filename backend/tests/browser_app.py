"""Isolated browser-test fixture. Never imported by the deployed app."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.core.config import Settings
from app.main import create_app
from app.services.auth import password_hash

app = create_app(Settings(_env_file=None, app_env="test", database_mode="memory", use_mock_ai=False,
                          seed_on_startup=True, seed_operational_data=False,
                          jwt_secret_key="isolated-browser-test-key-not-for-deployment", cookie_secure=False))
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def fixtures(application):
    async with original_lifespan(application):
        application.state.db.users.insert_one({
            "_id": "test-admin", "username": "admin", "email": "admin@test.local", "active": True,
            "role": "admin", "full_name": "Test Admin", "department": None,
            "password_hash": password_hash("TestOnly-password-123!"), "created_at": datetime.now(timezone.utc),
        })
        yield


app.router.lifespan_context = fixtures
