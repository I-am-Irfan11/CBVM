from datetime import datetime, timezone

from app.services.auth import password_hash


def _user(app, username, role, department=None):
    app.state.db.users.insert_one({
        "_id": f"test-{username}", "username": username, "email": f"{username}@test.local",
        "full_name": username.title(), "role": role, "department": department, "active": True,
        "password_hash": password_hash("TestOnly-password-123!"), "created_at": datetime.now(timezone.utc),
    })


def test_authentication_and_backend_roles(client, app):
    assert client.get("/vehicles", headers={"Authorization": ""}).status_code == 401
    assert client.get("/vehicles", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post("/auth/login", json={"identifier": "admin", "password": "wrong"}).status_code == 401

    _user(app, "security", "security")
    login = client.post("/auth/login", json={"identifier": "security", "password": "TestOnly-password-123!"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).json()["user"]["role"] == "security"
    assert client.post("/vehicles", headers=headers, json={
        "number_plate": "TN09CD5432", "vehicle_type": "student", "owner_name": "Allowed",
    }).status_code == 201
    assert client.post("/detections/mock", headers=headers, json={"vehicle_id": "demo-student-1"}).status_code == 200


def test_department_scope_and_user_admin(client, app):
    vehicle = client.post("/vehicles", json={
        "number_plate": "TN09AB7654", "vehicle_type": "student", "owner_name": "CS Student",
        "department": "Computer Science",
    }).json()
    _user(app, "staff", "department_staff", "Mechanical")
    login = client.post("/auth/login", json={"identifier": "staff", "password": "TestOnly-password-123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/vehicles", headers=headers).json()["total"] == 0
    assert client.get(f"/vehicles/{vehicle['id']}", headers=headers).status_code == 403
    assert client.post("/users", headers=headers, json={}).status_code == 403


def test_visitor_bus_reports_and_audit(client, app):
    response = client.post("/visitors", json={
        "number_plate": "KA03MN7890", "visitor_name": "Demo Visitor", "organization": "Example Org",
        "host_department": "Computer Science", "person_to_visit": "Reception", "purpose": "Other",
        "custom_purpose": "Project meeting", "camera_id": "main-gate-in",
    })
    assert response.status_code == 201, response.text
    assert response.json()["movement"]["purpose"] == "Project meeting"
    assert client.get("/vehicles/inside").json()["total"] == 1

    db = app.state.db
    bus = db.buses.find_one({"bus_number": "C-01"})
    bus_vehicle = db.vehicles.find_one({"_id": bus["vehicle_id"]})
    assert client.post(f"/vehicles/{bus_vehicle['_id']}/entry", json={
        "camera_id": "main-gate-in", "purpose": "Bus route",
    }).status_code == 201
    trip = client.post(f"/buses/{bus['_id']}/trips?purpose=NSS%20Trip")
    assert trip.status_code == 201, trip.text
    assert trip.json()["status"] == "AWAY"
    returned = client.post(f"/buses/{bus['_id']}/trips/return")
    assert returned.status_code == 200 and returned.json()["status"] == "RETURNED"

    report = client.get("/reports.csv?vehicle_type=visitor")
    assert report.status_code == 200 and "KA03MN7890" in report.text
    assert client.get("/analytics").json()["visitor_count"] == 1
    assert client.get("/audit").status_code == 200
    assert any(item["action"] == "visitor.register" for item in client.get("/audit").json())


def test_confirm_review_registers_visitor_without_removed_fields(client, app):
    from app.ai.anpr import Detection

    detection = Detection(
        plate="KA03MN7890", raw_text="KA03MN7890", confidence=0.41,
        bounding_box=(10, 10, 100, 50), valid=False, processing_time=0.1,
        camera_id="main-gate-in", direction="IN", timestamp=datetime.now(timezone.utc),
    )
    review = app.state.processor.process(detection, "main-gate-in")["review"]
    response = client.post(f"/reviews/{review['id']}/resolve", json={
        "action": "confirm", "number_plate": "KA03MN7890", "visitor_name": "Test Visitor",
        "phone": "9876543210", "organization": "Example Org", "purpose": "Guest Visit",
        "direction": "IN",
    })

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["movement"]["status"] == "INSIDE"
    vehicle = app.state.db.vehicles.find_one({"number_plate": "KA03MN7890"})
    assert vehicle and vehicle["owner_name"] == "Test Visitor"
    visitor = app.state.db.visitors.find_one({"vehicle_id": vehicle["_id"]})
    assert visitor and visitor["phone"] == "9876543210"
    assert visitor["movement_id"] == result["movement"]["id"]
