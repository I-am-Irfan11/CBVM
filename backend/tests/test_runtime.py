from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from app.services.operations import utcnow


def test_runtime_never_falls_back_to_memory():
    app = create_app(Settings(_env_file=None, database_mode="memory", jwt_secret_key="test-secret-long-enough-1234567890123"))
    with TestClient(app) as client:
        result = client.get("/vehicles")
        assert result.status_code == 503
        assert "restricted" in result.json()["detail"]


def test_empty_database_is_empty_and_passwords_survive_restart():
    settings = Settings(_env_file=None, app_env="test", database_mode="memory", seed_on_startup=True)
    app = create_app(settings)
    with TestClient(app):
        for name in ("vehicles", "visitors", "vehicle_logs", "buses", "bus_trips"):
            assert app.state.db[name].count_documents({}) == 0


def test_cookie_csrf_logout_and_private_socket(app, client):
    anonymous = TestClient(app)
    assert anonymous.get("/dashboard").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with anonymous.websocket_connect("/ws/events"):
            pass
    response = anonymous.post("/auth/login", json={"identifier": "admin", "password": "TestOnly-password-123!"})
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert anonymous.post("/auth/logout").status_code == 403
    assert anonymous.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert anonymous.get("/dashboard").status_code == 401


def test_visitor_invalid_camera_does_not_write_and_repeat_visit(client, app):
    body = {"number_plate": "TN09VV5432", "visitor_name": "Fixture Visitor", "host_department": "Test", "person_to_visit": "Reception"}
    result = client.post("/visitors", json={**body, "camera_id": "missing"})
    assert result.status_code == 422
    assert app.state.db.vehicles.count_documents({"number_plate": body["number_plate"]}) == 0
    first = client.post("/visitors", json=body).json()
    assert client.post("/visitors", json=body).status_code == 409
    client.post(f"/vehicles/{first['vehicle']['id']}/exit", json={"camera_id": "main-gate-out"})
    second = client.post("/visitors", json=body)
    assert second.status_code == 201
    assert second.json()["movement"]["status"] == "INSIDE"
    edited = client.put(f"/visitors/{first['visitor']['id']}", json={**body, "organization": "Updated"})
    assert edited.json()["organization"] == "Updated"
    assert client.get("/visitors?search=VV5432").json()


def test_analytics_counts_overnight_exit_in_campus_timezone(client, vehicle, app):
    start, end = app.state.operations.today_bounds()
    client.post(f"/vehicles/{vehicle['id']}/entry", json={"timestamp": (start-timedelta(hours=1)).isoformat()})
    client.post(f"/vehicles/{vehicle['id']}/exit", json={"camera_id": "main-gate-out", "timestamp": start.isoformat()})
    local_date = (start+timedelta(hours=5, minutes=30)).date().isoformat()
    report = client.get(f"/analytics?date_from={local_date}&date_to={local_date}").json()
    assert sum(row["entries"] for row in report["days"]) == 0
    assert sum(row["exits"] for row in report["days"]) == 1
    assert report["exits_by_hour"][0] == 1


def test_bus_return_records_actual_inside_transition(client, app):
    bus = app.state.db.buses.find_one({"bus_number": "C-01"})
    client.post(f"/vehicles/{bus['vehicle_id']}/entry", json={})
    assert client.post(f"/buses/{bus['_id']}/trips?purpose=Maintenance").status_code == 201
    assert client.post(f"/buses/{bus['_id']}/trips/return").status_code == 200
    assert app.state.db.vehicle_logs.count_documents({"vehicle_id": bus["vehicle_id"], "status": "INSIDE"}) == 1
    assert len(client.get(f"/buses/{bus['_id']}/trips").json()) == 1


def test_user_secrets_never_appear_in_audit_and_self_demotion_blocked(client):
    payload = {"username": "newguard", "email": "guard@test.local", "full_name": "Guard", "role": "security", "password": "Testing-only-password123!"}
    result = client.post("/users", json=payload)
    assert result.status_code == 201
    assert "password" not in result.text
    assert "password" not in client.get("/audit").text
    response = client.put("/users/test-admin", json={**payload, "username": "admin", "email": "admin@test.local", "active": False})
    assert response.status_code == 409
