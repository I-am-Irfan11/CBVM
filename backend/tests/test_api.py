from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pymongo.errors import DuplicateKeyError

from app.database.seed import seed


def stamp(minutes=0):
    return (datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=minutes)).isoformat()


def entry(client, vehicle, **extra):
    return client.post(f"/vehicles/{vehicle['id']}/entry", json={"camera_id": "main-gate-in", **extra})


def exit_vehicle(client, vehicle, **extra):
    return client.post(f"/vehicles/{vehicle['id']}/exit", json={"camera_id": "main-gate-out", **extra})


def test_registration_lookup_update_duplicate_and_deactivate(client, vehicle):
    assert client.get(f"/vehicles/{vehicle['id']}").json()["owner_name"] == "Test Student"
    assert client.get("/vehicles/by-plate/tn09-xy4321").json()["id"] == vehicle["id"]
    duplicate = client.post(
        "/vehicles", json={"number_plate": "tn09 xy4321", "vehicle_type": "staff", "owner_name": "Test"}
    )
    assert duplicate.status_code == 409
    payload = {"number_plate": "TN09XY4321", "vehicle_type": "staff", "owner_name": "Updated Test"}
    assert client.put(f"/vehicles/{vehicle['id']}", json=payload).json()["owner_name"] == "Updated Test"
    assert client.delete(f"/vehicles/{vehicle['id']}").json()["status"] == "inactive"
    assert entry(client, vehicle).status_code == 409
    assert client.get(f"/vehicles/{vehicle['id']}/history").status_code == 200


def test_validation_and_missing_records(client):
    assert (
        client.post(
            "/vehicles", json={"number_plate": "bad", "vehicle_type": "student", "owner_name": "X"}
        ).status_code
        == 422
    )
    assert client.get("/vehicles/missing").status_code == 404
    assert client.get("/vehicles/by-plate/TN00AA0000").status_code == 404
    assert client.get("/vehicles?limit=0").status_code == 422


def test_entry_exit_duration_history_inside_dashboard(client, vehicle):
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    end = start + timedelta(seconds=120)
    result = entry(client, vehicle, timestamp=start.isoformat(), purpose="Classes", event_id="one")
    assert result.status_code == 201
    assert result.json()["log"]["status"] == "INSIDE"
    assert result.json()["log"]["exit_time"] is None
    assert client.get("/vehicles/inside").json()["total"] == 1
    assert client.get("/dashboard").json()["currently_inside"] == 1
    assert client.delete(f"/vehicles/{vehicle['id']}").status_code == 409
    result = exit_vehicle(client, vehicle, timestamp=end.isoformat(), event_id="two")
    assert result.status_code == 200
    assert result.json()["log"]["duration_seconds"] == 120
    assert result.json()["log"]["status"] == "COMPLETED"
    assert client.get("/vehicles/inside").json()["total"] == 0
    history = client.get(f"/vehicles/{vehicle['id']}/history").json()
    assert history["total"] == 1
    assert history["items"][0]["purpose"] == "Classes"
    activities = client.get("/activity").json()
    assert [row["type"] for row in activities] == ["vehicle.exit", "vehicle.entry"]


def test_no_negative_naive_or_future_time(client, vehicle):
    assert entry(client, vehicle, timestamp="2026-01-01T12:00:00").status_code == 422
    assert (
        entry(
            client, vehicle, timestamp=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        ).status_code
        == 422
    )
    assert entry(client, vehicle, timestamp=stamp(2)).status_code == 201
    assert exit_vehicle(client, vehicle, timestamp=stamp(3)).status_code == 422
    assert client.get("/vehicles/inside").json()["total"] == 1


def test_exit_without_entry_and_camera_validation(client, vehicle):
    assert exit_vehicle(client, vehicle).status_code == 409
    assert entry(client, vehicle, camera_id="unknown").status_code == 404
    assert entry(client, vehicle, camera_id="main-gate-out").status_code == 422
    assert entry(client, vehicle, detection_confidence=0.2).status_code == 422


def test_duplicate_cooldown_and_event_retry(client, vehicle):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    assert (
        entry(
            client, vehicle, timestamp=(now - timedelta(seconds=20)).isoformat(), event_id="entry-once"
        ).status_code
        == 201
    )
    assert entry(client, vehicle).json()["duplicate"] is True
    assert (
        exit_vehicle(
            client, vehicle, timestamp=(now - timedelta(seconds=10)).isoformat(), event_id="exit-once"
        ).status_code
        == 200
    )
    assert exit_vehicle(client, vehicle, event_id="exit-once").json()["duplicate"] is True
    assert entry(client, vehicle).json()["duplicate"] is True
    assert entry(client, vehicle, event_id="entry-once").json()["duplicate"] is True
    assert client.get(f"/vehicles/{vehicle['id']}/history").json()["total"] == 1


def test_reentry_after_cooldown(client, vehicle):
    entry(client, vehicle, timestamp=stamp(5))
    exit_vehicle(client, vehicle, timestamp=stamp(4))
    assert entry(client, vehicle).status_code == 201
    assert client.get(f"/vehicles/{vehicle['id']}/history").json()["total"] == 2


def test_concurrent_entry_is_single_visit(client, vehicle):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: entry(client, vehicle), range(20)))
    assert sum(result.status_code == 201 for result in results) == 1
    assert all(result.status_code in (200, 201) for result in results)
    assert client.get("/vehicles/inside").json()["total"] == 1


def test_unique_index_guards_direct_duplicate(app, client, vehicle):
    entry(client, vehicle)
    original = app.state.db.vehicle_logs.find_one({"vehicle_id": vehicle["id"]})
    original["_id"] = "different"
    original["entry_event_id"] = "different"
    with pytest.raises(DuplicateKeyError):
        app.state.db.vehicle_logs.insert_one(original)


def test_seed_idempotent_preserves_changes(app, client):
    db = app.state.db
    db.vehicles.update_one({"_id": "demo-student-1"}, {"$set": {"owner_name": "Edited"}})
    seed(db, app.state.settings)
    assert db.vehicles.count_documents({}) == 7
    assert db.buses.count_documents({}) == 2
    assert db.vehicles.find_one({"_id": "demo-student-1"})["owner_name"] == "Edited"
    assert set(db.list_collection_names()) >= {
        "vehicles",
        "vehicle_logs",
        "purposes",
        "visitors",
        "buses",
        "cameras",
        "audit_logs",
    }


def test_websocket_receives_entry(client, vehicle):
    with client.websocket_connect("/ws/events") as socket:
        assert socket.receive_json()["type"] == "connected"
        entry(client, vehicle)
        event = socket.receive_json()
        assert event["type"] == "vehicle.entry"
        assert event["data"]["number_plate"] == vehicle["number_plate"]


def test_health_and_filtering(client):
    assert client.get("/health").json() == {"status": "ok", "database": "memory", "persistent": False}
    assert client.get("/vehicles?vehicle_type=bus").json()["total"] == 2
    assert client.get("/vehicles?search=TN09").json()["total"] == 1
    assert client.get("/vehicles?limit=2&offset=2").json()["total"] == 7
    assert len(client.get("/vehicles?limit=2&offset=2").json()["items"]) == 2


def test_today_counts_overnight_exit(app, client, vehicle):
    start, _ = app.state.operations.today_bounds()
    entry(client, vehicle, timestamp=(start - timedelta(hours=2)).isoformat())
    exit_vehicle(client, vehicle, timestamp=start.isoformat())
    dashboard = client.get("/dashboard").json()
    assert dashboard["entries_today"] == 0
    assert dashboard["exits_today"] == 1
    assert client.get("/logs/today").json()["total"] == 1


def test_repeated_exit_does_not_close_a_new_visit(client, vehicle):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    entry(client, vehicle, timestamp=(now - timedelta(minutes=5)).isoformat())
    exit_vehicle(client, vehicle, timestamp=(now - timedelta(seconds=10)).isoformat())
    assert entry(client, vehicle, timestamp=(now - timedelta(seconds=5)).isoformat()).status_code == 201
    repeated_exit = exit_vehicle(client, vehicle, timestamp=now.isoformat())
    assert repeated_exit.json()["duplicate"] is True
    assert client.get("/vehicles/inside").json()["total"] == 1
