import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app():
    return create_app(
        Settings(
            _env_file=None,
            database_mode="memory",
            seed_on_startup=True,
            use_mock_ai=True,
            run_video_worker=False,
        )
    )


@pytest.fixture
def client(app):
    with TestClient(app) as client:
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
