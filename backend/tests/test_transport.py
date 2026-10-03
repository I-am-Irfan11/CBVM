import json
import re

import pytest

from app.database.transport import parse_transport, refresh_snapshot, seed_transport
from app.core.config import ROOT


TABLE = """<h2>Bus Route Timings 2023-2024</h2><h3>Avadi</h3>
<p>Route No : 01 – Avadi</p><p>Bus Name : Meghna</p><table>
<tr><th>S.No</th><th>BOARDING POINT</th><th>TIMING (A.M)</th></tr>
<tr><td>1</td><td>AVADI CIRCLE</td><td>6.00</td></tr>
<tr><td>2</td><td>HINDUSTAN UNIVERSITY CAMPUS</td><td>8.00</td></tr></table>"""


def test_official_snapshot_is_sanitized_and_seeded(client):
    db = client.app.state.db
    snapshot = json.loads((ROOT / "database/seed/hits_transport.json").read_text(encoding="utf-8"))
    assert snapshot["reference_only"] is True
    assert snapshot["source_timetable_label"] == "Bus Route Timings 2023-2024"
    assert len(snapshot["routes"]) == 23
    serialized = json.dumps(snapshot["routes"])
    assert not re.search(r"\b\d{10}\b|incharge|@", serialized, re.I)
    assert seed_transport(db) == 23
    assert db.transport_routes.count_documents({"reference_only": True}) == 23
    assert db.transport_routes.find_one({"route_number": "19A"})["bus_name"] == "Colombia"


def test_parser_deduplicates_consistent_tables_and_rejects_malformed_data():
    parsed = parse_transport(TABLE + TABLE)
    assert len(parsed["routes"]) == 1
    assert parsed["routes"][0]["boarding_points"][0] == {
        "sequence": 1, "name": "AVADI CIRCLE", "time": "06:00",
    }
    with pytest.raises(ValueError):
        parse_transport(TABLE.replace("HINDUSTAN UNIVERSITY CAMPUS", "AIRPORT"))


def test_failed_refresh_leaves_existing_snapshot_untouched(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("original", encoding="utf-8")
    with pytest.raises(ValueError):
        refresh_snapshot(snapshot, attempts=1, fetch=lambda: "<html>broken</html>")
    assert snapshot.read_text(encoding="utf-8") == "original"
