import { useState } from "react";
import { api, API_URL } from "../services/api";
import { useApi } from "../hooks/useApi";
import {
  Badge,
  Card,
  DataState,
  Table,
  time,
  duration,
} from "../components/ui";

const purposes = [
  "Student Pickup",
  "Student Drop",
  "College Activity",
  "NSS Trip",
  "Industry Visit",
  "Industrial Training",
  "Staff Duty",
  "Official College Work",
  "Maintenance",
  "Delivery",
  "Guest Visit",
  "Parent Visit",
  "Event",
  "Emergency",
  "Other",
];

export default function OperationsPages({
  page,
  state,
  user,
  notify,
  refresh,
  reviewId,
  reviewPlate = "",
  clearReviewId,
}) {
  const [visitorOpen, setVisitorOpen] = useState(false);
  const [busOpen, setBusOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [days, setDays] = useState(30);
  const [vehicleType, setVehicleType] = useState("");
  const [purpose, setPurpose] = useState("");
  const [movementStatus, setMovementStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const vehicles = useApi(
    page === "buses" ? "/vehicles?vehicle_type=bus&limit=500" : null,
    0,
  );
  const routes = useApi(page === "buses" ? "/transport/routes" : null, 0);
  const analytics = useApi(
    page === "reports"
      ? `/analytics?days=${days}${vehicleType ? `&vehicle_type=${encodeURIComponent(vehicleType)}` : ""}${purpose ? `&purpose=${encodeURIComponent(purpose)}` : ""}${movementStatus ? `&status=${movementStatus}` : ""}${dateFrom ? `&date_from=${dateFrom}` : ""}${dateTo ? `&date_to=${dateTo}` : ""}`
      : null,
    `${days}:${vehicleType}:${purpose}:${movementStatus}:${dateFrom}:${dateTo}:${state.data?.length || 0}`,
  );
  async function act(fn, message) {
    setPending(true);
    try {
      await fn();
      notify(message);
      refresh();
      return true;
    } catch (error) {
      notify(error.message, true);
      return false;
    } finally {
      setPending(false);
    }
  }
  async function download() {
    const query = new URLSearchParams();
    if (vehicleType) query.set("vehicle_type", vehicleType);
    if (purpose) query.set("purpose", purpose);
    if (movementStatus) query.set("status", movementStatus);
    if (dateFrom) query.set("date_from", dateFrom);
    if (dateTo) query.set("date_to", dateTo);
    const response = await fetch(`${API_URL}/reports.csv?${query}`, {
      credentials: "include",
    });
    if (!response.ok) throw new Error("Report export failed");
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement("a"), {
      href: url,
      download: "gatelog-report.csv",
    });
    link.click();
    URL.revokeObjectURL(url);
  }

  if (page === "reports")
    return (
      <>
        <div className="toolbar report-filters">
          <label>
            Period{" "}
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
              <option value={366}>12 months</option>
            </select>
          </label>
          <label>
            Vehicle type{" "}
            <select
              value={vehicleType}
              onChange={(e) => setVehicleType(e.target.value)}
            >
              <option value="">All types</option>
              {[
                "student",
                "staff",
                "bus",
                "visitor",
                "service",
                "emergency",
                "other",
              ].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label>
            Purpose{" "}
            <input
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="Any purpose"
            />
          </label>
          <label>
            Status{" "}
            <select
              value={movementStatus}
              onChange={(e) => setMovementStatus(e.target.value)}
            >
              <option value="">All</option>
              <option value="INSIDE">Inside</option>
              <option value="COMPLETED">Completed</option>
            </select>
          </label>
          <label>
            From{" "}
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label>
            To{" "}
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <button
            className="button secondary"
            onClick={() => act(download, "CSV report downloaded.")}
          >
            Export CSV
          </button>
        </div>
        <DataState state={analytics} retry={refresh}>
          <div className="stats-grid">
            {[
              ["Movements", analytics.data?.movement_count],
              ["Visitors", analytics.data?.visitor_count],
              ["Bus movements", analytics.data?.bus_movements],
              [
                "Average stay",
                analytics.data?.average_stay_seconds == null
                  ? "—"
                  : duration(analytics.data.average_stay_seconds),
              ],
            ].map(([label, value]) => (
              <Card key={label}>
                <div className="eyebrow">{label}</div>
                <strong>{value ?? 0}</strong>
              </Card>
            ))}
          </div>
          <Card>
            <h2>Entries and exits by day</h2>
            <Table
              rows={analytics.data?.days || []}
              empty="No movements in this period."
              columns={[
                { key: "date", label: "Date" },
                { key: "entries", label: "Entries" },
                { key: "exits", label: "Exits" },
              ]}
            />
          </Card>
          <Card>
            <h2>Movement purpose</h2>
            <Table
              rows={Object.entries(analytics.data?.purposes || {}).map(
                ([name, count]) => ({ name, count }),
              )}
              empty="No purpose data."
              columns={[
                { key: "name", label: "Purpose" },
                { key: "count", label: "Movements" },
              ]}
            />
          </Card>
        </DataState>
      </>
    );

  if (page === "visitors")
    return (
      <>
        {user.role !== "department_staff" ? (
          <div className="page-action">
            <button
              className="button"
              onClick={() => setVisitorOpen((x) => !x)}
            >
              {visitorOpen ? "Cancel" : "Register visitor"}
            </button>
          </div>
        ) : null}
        {visitorOpen ? (
          <Card>
            <h2>Record a vehicle arrival</h2>
            <form
              className="ops-form"
              onSubmit={(e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                act(
                  () =>
                    api("/visitors", {
                      method: "POST",
                      body: {
                        number_plate: form.get("plate"),
                        visitor_name: form.get("name"),
                        phone: form.get("phone") || null,
                        purpose: form.get("purpose"),
                        custom_purpose: form.get("custom") || null,
                        camera_id: "main-gate-in",
                        review_id: reviewId || null,
                      },
                    }),
                  "Visitor registered and entry recorded.",
                ).then((ok) => {
                  if (ok) {
                    setVisitorOpen(false);
                    clearReviewId?.();
                  }
                });
              }}
            >
              <label>
                Registration plate
                <input
                  name="plate"
                  required
                  placeholder="TN09AB1234"
                  defaultValue={reviewPlate}
                />
              </label>
              <label>
                Person or student name
                <input name="name" required />
              </label>
              <label>
                Phone (optional)
                <input name="phone" />
              </label>
              <label>
                Purpose
                <select name="purpose">
                  {purposes.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label>
                Custom purpose for Other
                <input name="custom" />
              </label>
              <button className="button" disabled={pending}>
                Record entry
              </button>
            </form>
          </Card>
        ) : null}
        <DataState state={state} retry={refresh}>
          <Card>
            <Table
              rows={state.data || []}
              empty="No visitors have been registered."
              columns={[
                { key: "visitor_name", label: "Visitor" },
                {
                  key: "number_plate",
                  label: "Plate",
                  render: (row) => row.number_plate || row.vehicle_id,
                },
                { key: "purpose", label: "Purpose" },
                {
                  key: "created_at",
                  label: "Registered",
                  render: (row) => time(row.created_at),
                },
              ]}
            />
          </Card>
        </DataState>
      </>
    );

  if (page === "buses")
    return (
      <>
        {user.role === "admin" ? (
          <div className="page-action">
            <button className="button" onClick={() => setBusOpen((x) => !x)}>
              {busOpen ? "Cancel" : "Add bus"}
            </button>
          </div>
        ) : null}
        <Card>
          <h2>College buses in the published timetable</h2>
          <p className="muted">
            The timetable lists route bus names only. Add each vehicle’s actual registration plate in Vehicle registry before recording trips.
          </p>
          <Table
            rows={routes.data || []}
            empty="College route timetable is loading or unavailable."
            columns={[
              { key: "bus_name", label: "College bus name" },
              { key: "route_number", label: "Route" },
              { key: "route_name", label: "Area" },
            ]}
          />
        </Card>
        {busOpen ? (
          <Card>
            <h2>Link registered bus</h2>
            <form
              className="ops-form"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                act(
                  () =>
                    api("/buses", {
                      method: "POST",
                      body: {
                        vehicle_id: f.get("vehicle"),
                        bus_number: f.get("number"),
                        route_number: f.get("route"),
                        driver_name: f.get("driver"),
                        driver_phone: f.get("phone") || null,
                        capacity: Number(f.get("capacity")),
                      },
                    }),
                  "Bus added.",
                );
                setBusOpen(false);
              }}
            >
              <label>
                Registered bus vehicle
                <select name="vehicle" required>
                  {(vehicles.data?.items || []).map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.number_plate} · {v.owner_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Bus number
                <input name="number" required />
              </label>
              <label>
                Route
                <input name="route" list="college-routes" placeholder="Select or enter a route" required />
                <datalist id="college-routes">
                  {(routes.data || []).map((route) => (
                    <option key={route.id} value={`${route.route_number} · ${route.route_name}`} />
                  ))}
                </datalist>
              </label>
              <label>
                Driver name
                <input name="driver" required />
              </label>
              <label>
                Driver phone (optional)
                <input name="phone" />
              </label>
              <label>
                Capacity
                <input
                  name="capacity"
                  type="number"
                  min="1"
                  max="100"
                  defaultValue="48"
                />
              </label>
              <button className="button" disabled={pending}>
                Save bus
              </button>
            </form>
          </Card>
        ) : null}
        <DataState state={state} retry={refresh}>
          <Card>
            <Table
              rows={state.data || []}
              empty="No buses with vehicle registration plates are configured yet."
              columns={[
                { key: "bus_number", label: "Bus" },
                { key: "route", label: "Route" },
                { key: "driver_name", label: "Driver" },
                { key: "capacity", label: "Capacity" },
                { key: "status", label: "Status" },
                {
                  key: "trip",
                  label: "Movement",
                  render: (row) =>
                    row.active_trip ? (
                      <>
                        <Badge tone="amber">Away</Badge>{" "}
                        <button
                          className="button secondary small"
                          onClick={() =>
                            act(
                              () =>
                                api(`/buses/${row.id}/trips/return`, {
                                  method: "POST",
                                }),
                              "Bus return recorded.",
                            )
                          }
                        >
                          Record return
                        </button>
                      </>
                    ) : (
                      <button
                        className="button secondary small"
                        onClick={() => {
                          const why = window.prompt("Trip purpose", "NSS Trip");
                          if (why)
                            act(
                              () =>
                                api(
                                  `/buses/${row.id}/trips?purpose=${encodeURIComponent(why)}`,
                                  { method: "POST" },
                                ),
                              "Bus departure recorded.",
                            );
                        }}
                      >
                        Record departure
                      </button>
                    ),
                },
              ]}
            />
          </Card>
        </DataState>
      </>
    );

  if (page === "cameras")
    return (
      <>
        {user.role === "admin" ? (
          <div className="page-action">
            <button className="button" onClick={() => setCameraOpen((x) => !x)}>
              {cameraOpen ? "Cancel" : "Add camera"}
            </button>
          </div>
        ) : null}
        {cameraOpen ? (
          <Card>
            <h2>Configure camera source</h2>
            <form
              className="ops-form"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                act(
                  () =>
                    api("/cameras", {
                      method: "POST",
                      body: {
                        camera_name: f.get("name"),
                        location: f.get("location"),
                        direction: f.get("direction"),
                        source: f.get("source"),
                      },
                    }),
                  "Camera added.",
                ).then((ok) => ok && setCameraOpen(false));
              }}
            >
              <label>
                Name
                <input name="name" required />
              </label>
              <label>
                Location
                <input name="location" required />
              </label>
              <label>
                Direction
                <select name="direction">
                  <option>IN</option>
                  <option>OUT</option>
                  <option>BOTH</option>
                </select>
              </label>
              <label>
                Source
                <select name="source">
                  <option>mock</option>
                  <option>webcam</option>
                  <option>mp4</option>
                  <option>rtsp</option>
                </select>
              </label>
              <button className="button" disabled={pending}>
                Save camera
              </button>
            </form>
          </Card>
        ) : null}
        <DataState state={state} retry={refresh}>
          <Card>
            <Table
              rows={state.data || []}
              empty="No cameras configured."
              columns={[
                { key: "camera_name", label: "Camera" },
                { key: "location", label: "Location" },
                { key: "direction", label: "Direction" },
                { key: "source", label: "Source" },
                {
                  key: "health_status",
                  label: "Health",
                  render: (row) => (
                    <Badge
                      tone={
                        row.health_status === "online"
                          ? "green"
                          : row.health_status === "offline"
                            ? "amber"
                            : ""
                      }
                    >
                      {row.health_status}
                    </Badge>
                  ),
                },
                {
                  key: "last_frame_time",
                  label: "Last frame",
                  render: (row) =>
                    row.last_frame_time
                      ? time(row.last_frame_time)
                      : "No frame received",
                },
              ]}
            />
          </Card>
        </DataState>
      </>
    );

  if (page === "purposes")
    return (
      <>
        <div className="page-action">
          <button
            className="button"
            onClick={() => {
              const name = window.prompt("Purpose name");
              if (name?.trim())
                act(
                  () =>
                    api("/purposes", {
                      method: "POST",
                      body: {
                        purpose_name: name.trim(),
                        active: true,
                        sort_order: 100,
                      },
                    }),
                  "Purpose added.",
                );
            }}
          >
            Add purpose
          </button>
        </div>
        <DataState state={state} retry={refresh}>
          <Card>
            <Table
              rows={state.data || []}
              empty="No purposes are configured."
              columns={[
                { key: "purpose_name", label: "Purpose" },
                {
                  key: "active",
                  label: "Active",
                  render: (row) => (row.active ? "Yes" : "No"),
                },
                {
                  key: "action",
                  label: "Action",
                  render: (row) => (
                    <button
                      className="button secondary small"
                      onClick={() =>
                        act(
                          () =>
                            api(`/purposes/${row.id}`, {
                              method: "PUT",
                              body: {
                                purpose_name: row.purpose_name,
                                active: !row.active,
                                sort_order: row.sort_order || 0,
                              },
                            }),
                          row.active
                            ? "Purpose deactivated."
                            : "Purpose activated.",
                        )
                      }
                    >
                      {row.active ? "Deactivate" : "Activate"}
                    </button>
                  ),
                },
              ]}
            />
          </Card>
        </DataState>
      </>
    );

  if (page === "users")
    return (
      <>
        <div className="page-action">
          <button className="button" onClick={() => setUserOpen((x) => !x)}>
            {userOpen ? "Cancel" : "Add user"}
          </button>
        </div>
        {userOpen ? (
          <Card>
            <h2>Grant account access</h2>
            <form
              className="ops-form"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                act(
                  () =>
                    api("/users", {
                      method: "POST",
                      body: {
                        username: f.get("username"),
                        email: f.get("email"),
                        full_name: f.get("name"),
                        role: f.get("role"),
                        department: f.get("department") || null,
                      },
                    }),
                  "Access added. The user can sign in through Firebase with this email.",
                ).then((ok) => ok && setUserOpen(false));
              }}
            >
              <label>
                Username
                <input name="username" required minLength="3" />
              </label>
              <label>
                Email
                <input name="email" type="email" required />
              </label>
              <label>
                Full name
                <input name="name" required />
              </label>
              <label>
                Role
                <select name="role">
                  <option>security</option>
                  <option>department_staff</option>
                  <option>admin</option>
                </select>
              </label>
              <label>
                Department
                <input name="department" />
              </label>
              <button className="button" disabled={pending}>
                Add access
              </button>
            </form>
          </Card>
        ) : null}
        <DataState state={state} retry={refresh}>
          <Card>
            <Table
              rows={state.data || []}
              empty="No users configured."
              columns={[
                { key: "username", label: "Username" },
                { key: "full_name", label: "Name" },
                { key: "email", label: "Email" },
                { key: "role", label: "Role" },
                { key: "department", label: "Department" },
                {
                  key: "active",
                  label: "Active",
                  render: (row) => (row.active ? "Yes" : "No"),
                },
                {
                  key: "action",
                  label: "Action",
                  render: (row) => (
                    <button
                      className="button secondary small"
                      disabled={row.id === user.id}
                      onClick={() =>
                        act(
                          () =>
                            api(`/users/${row.id}`, {
                              method: "PUT",
                              body: {
                                username: row.username,
                                email: row.email,
                                full_name: row.full_name,
                                role: row.role,
                                department: row.department,
                                active: !row.active,
                              },
                            }),
                          row.active ? "Account disabled." : "Account enabled.",
                        )
                      }
                    >
                      {row.active ? "Disable" : "Enable"}
                    </button>
                  ),
                },
              ]}
            />
          </Card>
        </DataState>
      </>
    );

  if (page === "audit")
    return (
      <DataState state={state} retry={refresh}>
        <Card>
          <Table
            rows={state.data || []}
            empty="No administrative actions recorded."
            columns={[
              { key: "time", label: "Time", render: (row) => time(row.time) },
              { key: "user", label: "User" },
              { key: "role", label: "Role" },
              { key: "action", label: "Action" },
              {
                key: "new_values",
                label: "Changed values",
                render: (row) => JSON.stringify(row.new_values || {}),
              },
            ]}
          />
        </Card>
      </DataState>
    );
  if (page === "transport")
    return (
      <DataState state={state} retry={refresh}>
        <Card>
          {(state.data || []).length === 0 ? <p>No college routes have been imported yet.</p> : null}
          {(state.data || []).map((route) => (
            <details key={route.id} className="transport-route">
              <summary>{route.route_number} · {route.route_name} — {route.bus_name}</summary>
              <Table rows={route.boarding_points || []} columns={[
                { key: "sequence", label: "Stop" },
                { key: "name", label: "Boarding point" },
                { key: "time", label: "Morning time" },
              ]} />
              <p><a href={route.source_url} target="_blank" rel="noreferrer">College transport source</a> · {route.source_timetable_label}</p>
            </details>
          ))}
        </Card>
      </DataState>
    );
  return null;
}
