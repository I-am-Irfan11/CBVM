import {
  ArrowDownLeft,
  ArrowUpRight,
  CarFront,
  Camera,
  ArrowRight,
  CircleParking,
} from "lucide-react";
import { Badge, Card, Plate, Table, time } from "../components/ui";
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
              ? "Simulated recognition is enabled. No physical camera is connected."
              : "Camera status updates when the capture worker receives frames."}
          </p>
        </Card>
      </div>
      {data.mock_ai ? <DemoControls notify={notify} refresh={refresh} /> : null}
    </>
  );
}
