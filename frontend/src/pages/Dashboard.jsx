import {
  ArrowDownLeft,
  ArrowUpRight,
  CarFront,
  Camera,
  ArrowRight,
  CircleParking,
} from "lucide-react";
import { Badge, Card, Plate, Table, duration, time } from "../components/ui";
import DemoControls from "../components/DemoControls";

export function ActivityTable({ rows, navigate }) {
  return (
    <Table
      rows={rows}
      empty="No movements recorded. Run a detection or record an entry from the registry."
      columns={[
        {
          key: "number_plate",
          label: "Vehicle",
          render: (row) => (
            <button
              className="plate-link"
              onClick={() => navigate("history", row.vehicle_id)}
            >
              <Plate>{row.number_plate}</Plate>
            </button>
          ),
        },
        {
          key: "type",
          label: "Movement",
          render: (row) => (
            <Badge tone={row.type === "vehicle.entry" ? "green" : "blue"}>
              {row.type === "vehicle.entry" ? "↙ Entry" : "↗ Exit"}
            </Badge>
          ),
        },
        {
          key: "vehicle_type",
          label: "Category",
          render: (row) => (
            <span className="capitalize">{row.vehicle_type}</span>
          ),
        },
        { key: "purpose", label: "Trip purpose" },
        {
          key: "timestamp",
          label: "Time · IST",
          render: (row) => time(row.timestamp),
        },
      ]}
    />
  );
}
export default function Dashboard({ data, navigate, notify, refresh }) {
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!data) return null;
  const stats = [
    [
      "Registered vehicles",
      data.registered_vehicles,
      CarFront,
      "Active in the registry",
    ],
    [
      "Currently inside",
      data.currently_inside,
      CircleParking,
      "Open campus visits",
    ],
    [
      "Entries today",
      data.entries_today,
      ArrowDownLeft,
      "Arrivals since midnight",
    ],
    ["Exits today", data.exits_today, ArrowUpRight, "Completed departures"],
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">GATE OPERATIONS</span>
          <h1>Campus at a glance.</h1>
          <p>A clear view of every arrival and departure.</p>
        </div>
        <div className="date-stamp">
          {new Date().toLocaleDateString("en-IN", {
            timeZone: data.campus_timezone,
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric",
          })}
        </div>
      </div>
      <div className="stats-grid">
        {stats.map(([label, value, Icon, description], index) => (
          <Card key={label} className={`stat-card stat-${index}`}>
            <div className="stat-top">
              <span>{label}</span>
              <Icon size={20} />
            </div>
            <strong>{value.toLocaleString()}</strong>
            <p>{description}</p>
          </Card>
        ))}
      </div>
      <div className="overview-grid">
        <Card className="activity-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">MOVEMENT LOG</span>
              <h2>Recent activity</h2>
            </div>
            <button
              className="text-button"
              onClick={() => navigate("activity")}
            >
              View all <ArrowRight size={16} />
            </button>
          </div>
          <ActivityTable rows={data.recent_activity} navigate={navigate} />
        </Card>
        <Card className="gate-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">MAIN GATE</span>
              <h2>Camera status</h2>
            </div>
            <Camera size={21} />
          </div>
          <div className="gate-diagram" aria-hidden="true">
            <div className="gate-label">CAMPUS BOUNDARY</div>
            <div className="gate-road">
              <span className="gate-lane">
                IN
                <ArrowDownLeft size={36} />
              </span>
              <span className="gate-lane">
                OUT
                <ArrowUpRight size={36} />
              </span>
            </div>
            <div className="gate-barrier" />
          </div>
          <div className="camera-list">
            {data.cameras.map((camera) => (
              <div className="camera-row" key={camera.id}>
                <div>
                  <strong>{camera.camera_name}</strong>
                  <small>
                    {camera.last_frame_time
                      ? `Last frame ${time(camera.last_frame_time)}`
                      : "No frames received yet"}
                  </small>
                </div>
                <Badge
                  tone={camera.health_status === "offline" ? "amber" : "green"}
                >
                  {camera.health_status}
                </Badge>
              </div>
            ))}
          </div>
          <p className="camera-note">
            {data.mock_ai
              ? "Use the laptop camera demo below to capture a frame. Plate matching is simulated from the selected registered vehicle."
              : "Camera status updates when the capture worker receives frames."}
          </p>
        </Card>
      </div>
      <div className="section-heading dashboard-section-heading">
        <div><span className="eyebrow">OPEN MOVEMENTS</span><h2>Currently inside campus</h2></div>
        <button className="text-button" onClick={() => navigate("inside")}>View all <ArrowRight size={16} /></button>
      </div>
      <Card>
        <Table rows={data.inside_rows || []} empty="No vehicles are currently recorded inside campus." columns={[
          { key: "number_plate", label: "Plate", render: row => <Plate>{row.number_plate}</Plate> },
          { key: "identity", label: "Vehicle", render: row => <span>{row.owner_name || row.visitor_name || row.vehicle_type}</span> },
          { key: "vehicle_type", label: "Type", render: row => <span className="capitalize">{row.vehicle_type}</span> },
          { key: "purpose", label: "Purpose" },
          { key: "entry_time", label: "Entered", render: row => time(row.entry_time) },
          { key: "duration", label: "Time inside", render: row => duration(Math.max(0, (clock - new Date(row.entry_time).getTime()) / 1000)) },
        ]} />
      </Card>
      <div className="overview-grid dashboard-followup-grid">
        <Card>
          <div className="section-heading"><div><span className="eyebrow">OPERATOR REVIEW</span><h2>Readings needing attention</h2></div><Badge tone={data.unknown_vehicles ? "amber" : "green"}>{data.pending_reviews?.length || 0}</Badge></div>
          <p>{data.unknown_vehicles || 0} unknown vehicle{data.unknown_vehicles === 1 ? "" : "s"} awaiting registration or review.</p>
          {(data.pending_review_items || []).slice(0, 3).map(item => <div className="camera-row" key={item.id}><div><strong>{item.raw_text || item.plate || "Unreadable plate"}</strong><small>{item.reason} · {time(item.timestamp)}</small></div><button className="text-button" onClick={() => navigate("reviews")}>Review</button></div>)}
          {!data.pending_review_items?.length ? <p>No pending readings.</p> : null}
        </Card>
        <Card>
          <div className="section-heading"><div><span className="eyebrow">TRANSPORT</span><h2>Bus movements</h2></div><Badge>{data.bus_count || 0} active buses</Badge></div>
          {(data.bus_trips_away || []).slice(0, 5).map(trip => <div className="camera-row" key={trip.id}><div><strong>{trip.bus_number} · {trip.purpose}</strong><small>Departed {time(trip.departure_time)} · {trip.route}</small></div><Badge tone="amber">Away</Badge></div>)}
          {!data.bus_trips_away?.length ? <p>No buses are currently away on trips.</p> : null}
        </Card>
      </div>
      {data.mock_ai ? <DemoControls notify={notify} refresh={refresh} /> : null}
    </>
  );
}
import { useEffect, useState } from "react";
