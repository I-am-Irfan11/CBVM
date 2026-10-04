import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app():
    return create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_mode="memory",
            seed_operational_data=True,
            seed_on_startup=True,
            use_mock_ai=True,
            run_video_worker=False,
        )
    )


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        from app.services.auth import password_hash
        from datetime import datetime, timezone

        app.state.db.users.insert_one({
            "_id": "test-admin", "username": "admin", "email": "admin@test.local",
            "full_name": "Test Admin", "role": "admin", "department": None, "active": True,
            "password_hash": password_hash("TestOnly-password-123!"), "created_at": datetime.now(timezone.utc),
        })
        token = app.state.auth.login("admin", "TestOnly-password-123!", "test-client")["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        yield client


@pytest.fixture
def vehicle(client):
    result = client.post(
        "/vehicles",
        json={
            "number_plate": "TN09XY4321",
            "vehicle_type": "student",
            "owner_name": "Test Student",
            "student_id": "TEST-001",
            "department": "Testing",
        },
    )
    assert result.status_code == 201
    return result.json()
