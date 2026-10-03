"""Import a sanitized reference timetable; never create operational vehicles."""

import argparse
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from app.core.config import ROOT

SOURCE_URL = "https://hindustanuniv.ac.in/facilities/transport/"
SNAPSHOT = ROOT / "database/seed/hits_transport.json"


class TimetableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.prefix = []
        self.tables = []
        self.rows = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.rows is not None:
                raise ValueError("Nested timetable tables are unsupported")
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br":
            (self.cell if self.cell is not None else self.prefix).append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.tables.append(("".join(self.prefix), self.rows))
            self.prefix = []
            self.rows = None
        elif tag in ("p", "strong", "h2", "h3", "h4", "h5"):
            self.prefix.append("\n")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif self.rows is None:
            self.prefix.append(data)


def parse_transport(html, *, fetched_at=None):
    parser = TimetableParser()
    parser.feed(html)
    all_text = "\n".join(prefix for prefix, _ in parser.tables)
    label = re.search(r"Bus Route Timings\s+(\d{4}\s*[-–]\s*\d{4})", all_text, re.I)
    if not label:
        raise ValueError("Source timetable label is missing")
    routes = []
    for prefix, rows in parser.tables:
        route = re.search(r"Route\s+No\s*:\s*(\d+[A-Z]?)\s*[-–]\s*([^\n]+)", prefix, re.I)
        if not route:
            if any("boarding point" in cell.lower() for row in rows for cell in row):
                raise ValueError("Timetable has no route identity")
            continue
        bus = re.search(r"Bus\s+Name\s*:\s*([^\n]+)", prefix, re.I)
        if not bus or not rows or len(rows[0]) < 3 or "boarding point" not in rows[0][1].lower():
            raise ValueError("Timetable header is malformed")
        points = []
        for row in rows[1:]:
            if not row or not any(row):
                continue
            if len(row) < 3 or not row[0].isdigit() or not row[1]:
                raise ValueError("Timetable boarding row is malformed")
            timing = re.fullmatch(r"(\d{1,2})[.:](\d{2})(?:\s*[Aa]\.?[Mm]\.?)?", row[2])
            if not timing or not 0 <= int(timing[1]) < 12 or not 0 <= int(timing[2]) < 60:
                raise ValueError("Timetable morning time is malformed")
            points.append({"sequence": len(points) + 1, "name": row[1],
                           "time": f"{int(timing[1]):02}:{timing[2]}"})
        if len(points) < 2 or "HINDUSTAN" not in points[-1]["name"].upper():
            raise ValueError("Timetable campus endpoint is missing")
        number = route[1].zfill(2)
        item = {"route_number": number, "route_name": route[2].strip(),
                "bus_name": bus[1].strip(), "boarding_points": points,
                "endpoint": points[-1]["name"]}
        existing = next((saved for saved in routes if saved["route_number"] == number), None)
        if existing and existing != item:
            raise ValueError(f"Conflicting copies of route {number}")
        if not existing:
            routes.append(item)
    if not routes:
        raise ValueError("Timetable is empty")
    snapshot = {"source_url": SOURCE_URL,
                "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
                "source_timetable_label": "Bus Route Timings " + re.sub(r"\s*[-–]\s*", "-", label[1]),
                "reference_only": True, "routes": routes}
    # Only allow timetable fields; reject unexpected contact-like data even in accepted cells.
    if re.search(r"\b\d{10}\b|incharge|@", json.dumps(snapshot["routes"]), re.I):
        raise ValueError("Unexpected personal contact data in route fields")
    return snapshot


def fetch_html():
    request = Request(SOURCE_URL, headers={"User-Agent": "GateLog transport reference importer/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read(5_000_001).decode("utf-8")


def refresh_snapshot(path=SNAPSHOT, *, attempts=3, fetch=fetch_html, sleep=time.sleep):
    if not 1 <= attempts <= 5:
        raise ValueError("Use one to five fetch attempts")
    for attempt in range(attempts):
        try:
            html = fetch()
            if len(html) > 5_000_000:
                raise ValueError("Transport page exceeds size limit")
            snapshot = parse_transport(html)
            break
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep(min(2 ** attempt, 8))
    path = Path(path)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if len(snapshot["routes"]) < len(existing["routes"]):
            raise ValueError("Route count decreased; review the source before replacing the snapshot")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as output:
            temporary = output.name
            json.dump(snapshot, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return snapshot


def seed_transport(db, path=SNAPSHOT):
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    provenance = {key: value for key, value in snapshot.items() if key != "routes"}
    for route in snapshot["routes"]:
        db.transport_routes.update_one({"_id": "hits-route-" + route["route_number"]},
                                       {"$set": {**route, **provenance}}, upsert=True)
    return len(snapshot["routes"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Fetch and atomically replace the reference snapshot")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    if args.refresh:
        snapshot = refresh_snapshot(attempts=args.attempts)
        print(f"Saved {len(snapshot['routes'])} reference routes ({snapshot['source_timetable_label']}).")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
