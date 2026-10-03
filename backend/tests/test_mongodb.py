import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.mongodb
def test_real_mongodb_lifecycle():
    uri = os.getenv("TEST_MONGODB_URI")
    if not uri:
        pytest.skip("Set TEST_MONGODB_URI to opt in to the real MongoDB integration test")
    database = "gatelog_test_" + uuid4().hex
    settings = Settings(
        _env_file=None,
        database_mode="mongodb",
        mongodb_uri=uri,
        mongodb_database=database,
        seed_on_startup=True,
        use_mock_ai=True,
        run_video_worker=False,
    )
    try:
        with TestClient(create_app(settings)) as client:
            assert client.get("/health").json()["persistent"] is True
            result = client.post("/detections/mock", json={"scenario": "student"})
            assert result.json()["outcome"] == "accepted"
            assert (
                client.post("/detections/mock", json={"scenario": "student"}).json()["outcome"] == "duplicate"
            )
            assert client.get("/vehicles/inside").json()["total"] == 1
            result = client.post("/detections/mock", json={"scenario": "student", "direction": "OUT"})
            assert result.json()["log"]["status"] == "COMPLETED"
    finally:
        with MongoClient(uri, serverSelectionTimeoutMS=4000) as mongo:
            mongo.drop_database(database)
