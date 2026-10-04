"""Real persistence test: unique disposable database, never an existing campus DB."""
import os
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from app.core.config import Settings
from app.main import create_app
from app.services.auth import password_hash


@pytest.mark.mongodb
def test_real_mongodb_lifecycle():
    uri = os.getenv("TEST_MONGODB_URI")
    if not uri:
        pytest.skip("Set TEST_MONGODB_URI to run the isolated real MongoDB integration test")
    database = "gatelog_test_" + uuid4().hex
    settings = Settings(_env_file=None, app_env="test", database_mode="mongodb", mongodb_uri=uri,
                        mongodb_database=database, seed_on_startup=True, use_mock_ai=False,
                        jwt_secret_key="isolated-test-secret-never-deploy-123456789")
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            assert client.get("/health").json()["persistent"] is True
            db = app.state.db
            db.users.insert_one({"_id": "test-admin", "username": "admin", "email": "test@example.invalid",
                "full_name": "Test Admin", "role": "admin", "active": True, "department": None,
                "password_hash": password_hash("TestOnly-password-123!"), "created_at": datetime.now(timezone.utc)})
            login = client.post("/auth/login", json={"identifier": "admin", "password": "TestOnly-password-123!"}).json()
            client.headers["Authorization"] = "Bearer " + login["access_token"]
            vehicle = client.post("/vehicles", json={"number_plate": "TN09ZZ9876", "vehicle_type": "bus", "owner_name": "Isolated integration fixture"}).json()
            payload = {"camera_id": "main-gate-in", "event_id": "test-entry"}
            assert client.post(f"/vehicles/{vehicle['id']}/entry", json=payload).status_code == 201
            assert client.post(f"/vehicles/{vehicle['id']}/entry", json=payload).json()["duplicate"]
            assert client.post(f"/vehicles/{vehicle['id']}/exit", json={"camera_id": "main-gate-out"}).json()["log"]["status"] == "COMPLETED"
            visitor = client.post("/visitors", json={"number_plate": "KA03ZZ5432", "visitor_name": "Test Visitor", "host_department": "Testing", "person_to_visit": "Reception"})
            assert visitor.status_code == 201
            purpose = client.post("/purposes", json={"purpose_name": "Test purpose"}).json()
            assert client.put(f"/purposes/{purpose['id']}", json={"purpose_name": "Updated test purpose"}).status_code == 200
            bus = client.post("/buses", json={"vehicle_id": vehicle["id"], "bus_number": "TEST-01", "route_number": "01", "driver_name": "Fixture"})
            assert bus.status_code == 201, bus.text
            assert "TN09ZZ9876" in client.get("/reports.csv").text
            assert client.get("/analytics").json()["movement_count"] == 2
            assert client.get("/audit").json()
        # Fresh application and MongoClient prove data survives disconnect/reconnect.
        with TestClient(create_app(settings)) as reopened:
            login = reopened.post("/auth/login", json={"identifier": "admin", "password": "TestOnly-password-123!"})
            assert login.status_code == 200  # Existing password hashes are preserved.
            reopened.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            assert reopened.get(f"/vehicles/{vehicle['id']}/history").json()["total"] == 1
            assert reopened.get("/visitors").json()[0]["visitor_name"] == "Test Visitor"
            assert reopened.get("/buses").json()[0]["bus_number"] == "TEST-01"
            assert reopened.get("/purposes").json()[0]["purpose_name"] == "Updated test purpose"
    finally:
        # This exact UUID database was allocated by this test; existing DBs never touched.
        with MongoClient(uri, serverSelectionTimeoutMS=4000) as mongo:
            mongo.drop_database(database)
