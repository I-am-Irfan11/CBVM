import { useCallback, useEffect, useState } from "react";
import {
  Plus,
  Search,
  Pencil,
  ArrowDownLeft,
  ArrowUpRight,
  History,
  RefreshCw,
} from "lucide-react";
import { api } from "./services/api";
import { useApi } from "./hooks/useApi";
import { useLiveEvents } from "./hooks/useLiveEvents";
import Shell, { pages } from "./layouts/Shell";
import Dashboard, { ActivityTable } from "./pages/Dashboard";
import {
  Badge,
  Card,
  DataState,
  Modal,
  Notification,
  Pagination,
  Plate,
  Table,
  duration,
  time,
} from "./components/ui";
import VehicleForm, { vehicleTypes } from "./components/VehicleForm";
import MovementForm from "./components/MovementForm";
import DemoControls from "./components/DemoControls";

const initialPage = () =>
  pages.some((item) => item[0] === location.hash.slice(1))
    ? location.hash.slice(1)
    : "dashboard";
export default function App() {
  const [page, setPage] = useState(initialPage);
  const [revision, setRevision] = useState(0);
  const [notification, setNotification] = useState(null);
  const [form, setForm] = useState(null);
  const [movement, setMovement] = useState(null);
  const [deactivate, setDeactivate] = useState(null);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);
  const [vehicleId, setVehicleId] = useState("");
  const [plateSearch, setPlateSearch] = useState("");
  const [pending, setPending] = useState(false);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const liveStatus = useLiveEvents(refresh);
  const dashboard = useApi("/dashboard", revision);
  const path =
    page === "registry"
      ? `/vehicles?limit=25&offset=${offset}&search=${encodeURIComponent(search)}${type ? `&vehicle_type=${type}` : ""}`
      : page === "inside"
        ? `/vehicles/inside?limit=25&offset=${offset}`
        : page === "history" && vehicleId
          ? `/vehicles/${vehicleId}/history?limit=25&offset=${offset}`
          : page === "activity"
            ? "/activity?limit=100"
            : page === "reviews"
              ? `/reviews?limit=25&offset=${offset}`
              : null;
  const view = useApi(path, revision);
  const notify = useCallback(
    (text, error = false) => setNotification({ text, error }),
    [],
  );
  useEffect(() => {
    const change = () => {
      setPage(initialPage());
      setOffset(0);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    if (!notification || notification.error) return;
    const timer = setTimeout(() => setNotification(null), 6500);
    return () => clearTimeout(timer);
  }, [notification]);
  function navigate(next, id) {
    setPage(next);
    location.hash = next;
    setOffset(0);
    if (id) setVehicleId(id);
  }
  async function saveVehicle(payload, id) {
    await api(id ? `/vehicles/${id}` : "/vehicles", {
      method: id ? "PUT" : "POST",
      body: payload,
    });
    notify(id ? "Vehicle updated." : "Vehicle registered.");
    refresh();
  }
  async function saveMovement(id, direction, payload) {
    const result = await api(
      `/vehicles/${id}/${direction === "IN" ? "entry" : "exit"}`,
      { method: "POST", body: payload },
    );
    notify(
      result.duplicate
        ? "Repeated event ignored. No new movement recorded."
        : `${direction === "IN" ? "Entry" : "Exit"} recorded.`,
    );
    refresh();
  }
  async function findHistory(event) {
    event.preventDefault();
    setPending(true);
    try {
      const vehicle = await api(
        `/vehicles/by-plate/${encodeURIComponent(plateSearch)}`,
      );
      setVehicleId(vehicle.id);
      setOffset(0);
    } catch (error) {
      setVehicleId("");
      notify(error.message, true);
    } finally {
      setPending(false);
    }
  }
  async function dismissReview(id) {
    setPending(true);
    try {
      await api(`/reviews/${id}/dismiss`, { method: "POST" });
      notify("Review dismissed. No vehicle movement was recorded.");
      refresh();
    } catch (error) {
      notify(error.message, true);
    } finally {
      setPending(false);
    }
  }
  const historyColumns = [
    {
      key: "number_plate",
      label: "Vehicle",
      render: (row) => <Plate>{row.number_plate}</Plate>,
    },
    {
      key: "entry_time",
      label: "Entry · IST",
      render: (row) => time(row.entry_time),
    },
    {
      key: "exit_time",
      label: "Exit · IST",
      render: (row) => time(row.exit_time),
    },
    {
      key: "duration_seconds",
      label: "Duration",
      render: (row) => duration(row.duration_seconds),
    },
    { key: "purpose", label: "Trip purpose" },
    {
      key: "status",
      label: "Status",
      render: (row) => (
        <Badge tone={row.status === "INSIDE" ? "green" : "blue"}>
          {row.status === "INSIDE" ? "Inside" : "Completed"}
        </Badge>
      ),
    },
  ];
  const headings = {
    registry: [
      "Vehicle registry",
      "Manage the vehicles that belong on campus.",
    ],
    inside: ["Currently inside", "Open visits awaiting a departure."],
    history: [
      "Vehicle history",
      "Trace arrivals, departures, and time on campus.",
    ],
    activity: [
      "Live activity",
      "The latest 100 entry and exit events, updated as they happen.",
    ],
    reviews: [
      "Review queue",
      "Inspect uncertain readings before taking action.",
    ],
  };
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <Shell
        page={page}
        navigate={navigate}
        status={liveStatus}
        dashboard={dashboard.data}
      >
        {page === "dashboard" ? (
          <DataState state={dashboard} retry={refresh}>
            <Dashboard
              data={dashboard.data}
              navigate={navigate}
              notify={notify}
              refresh={refresh}
            />
          </DataState>
        ) : (
          <>
            <div className="page-heading">
              <div>
                <span className="eyebrow">CAMPUS OPERATIONS</span>
                <h1>{headings[page]?.[0]}</h1>
                <p>{headings[page]?.[1]}</p>
              </div>
              {page === "registry" ? (
                <button className="button" onClick={() => setForm({})}>
                  <Plus size={18} />
                  Register vehicle
                </button>
              ) : (
                <button className="button secondary" onClick={refresh}>
                  <RefreshCw size={16} />
                  Refresh
                </button>
              )}
            </div>
            {page === "registry" ? (
              <Card>
                <div className="toolbar">
                  <div className="search-box">
                    <Search size={18} />
                    <input
                      aria-label="Search vehicles"
                      placeholder="Search registration or owner"
                      value={search}
                      onChange={(event) => {
                        setSearch(event.target.value);
                        setOffset(0);
                      }}
                    />
                  </div>
                  <select
                    aria-label="Filter vehicle type"
                    value={type}
                    onChange={(event) => {
                      setType(event.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All vehicle types</option>
                    {vehicleTypes.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </div>
                <DataState state={view} retry={refresh}>
                  <Table
                    rows={view.data?.items || []}
                    empty="No vehicles found. Register a vehicle or adjust your search."
                    columns={[
                      {
                        key: "number_plate",
                        label: "Registration",
                        render: (row) => <Plate>{row.number_plate}</Plate>,
                      },
                      {
                        key: "owner_name",
                        label: "Owner",
                        render: (row) => (
                          <div className="owner">
                            <strong>{row.owner_name}</strong>
                            <small>
                              {row.department ||
                                row.vehicle_model ||
                                "No department"}
                            </small>
                          </div>
                        ),
                      },
                      {
                        key: "vehicle_type",
                        label: "Type",
                        render: (row) => (
                          <span className="capitalize">{row.vehicle_type}</span>
                        ),
                      },
                      {
                        key: "status",
                        label: "Status",
                        render: (row) => (
                          <Badge tone={row.status === "active" ? "green" : ""}>
                            {row.status}
                          </Badge>
                        ),
                      },
                      {
                        key: "actions",
                        label: "Actions",
                        render: (row) => (
                          <div className="row-actions">
                            <button
                              title="Edit vehicle"
                              aria-label={`Edit ${row.number_plate}`}
                              onClick={() => setForm(row)}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              title="Vehicle history"
                              aria-label={`History ${row.number_plate}`}
                              onClick={() => navigate("history", row.id)}
                            >
                              <History size={16} />
                            </button>
                            <button
                              className="entry-button"
                              disabled={row.status !== "active"}
                              onClick={() =>
                                setMovement({ vehicle: row, direction: "IN" })
                              }
                            >
                              <ArrowDownLeft size={15} />
                              Entry
                            </button>
                            {row.status === "active" ? (
                              <button
                                className="deactivate-button"
                                onClick={() => setDeactivate(row)}
                              >
                                Deactivate
                              </button>
                            ) : null}
                          </div>
                        ),
                      },
                    ]}
                  />
                  <Pagination
                    offset={offset}
                    total={view.data?.total || 0}
                    onChange={setOffset}
                  />
                </DataState>
              </Card>
            ) : null}
            {page === "inside" ? (
              <Card>
                <DataState state={view} retry={refresh}>
                  <Table
                    rows={view.data?.items || []}
                    empty="No vehicles are currently inside. Record an entry from the registry."
                    columns={[
                      ...historyColumns.filter(
                        (item) =>
                          !["exit_time", "status", "duration_seconds"].includes(
                            item.key,
                          ),
                      ),
                      {
                        key: "elapsed",
                        label: "Time inside",
                        render: (row) =>
                          duration(
                            Math.max(
                              0,
                              (Date.now() -
                                new Date(row.entry_time).getTime()) /
                                1000,
                            ),
                          ),
                      },
                      {
                        key: "actions",
                        label: "Departure",
                        render: (row) => (
                          <button
                            className="button secondary small"
                            onClick={() =>
                              setMovement({ vehicle: row, direction: "OUT" })
                            }
                          >
                            <ArrowUpRight size={16} />
                            Record exit
                          </button>
                        ),
                      },
                    ]}
                  />
                  <Pagination
                    offset={offset}
                    total={view.data?.total || 0}
                    onChange={setOffset}
                  />
                </DataState>
              </Card>
            ) : null}
            {page === "history" ? (
              <Card>
                <form className="toolbar" onSubmit={findHistory}>
                  <div className="search-box">
                    <Search size={18} />
                    <input
                      aria-label="History registration number"
                      placeholder="Registration number, e.g. TN09AB1234"
                      value={plateSearch}
                      required
                      onChange={(event) => setPlateSearch(event.target.value)}
                    />
                  </div>
                  <button className="button" disabled={pending}>
                    Find history
                  </button>
                </form>
                {vehicleId ? (
                  <DataState state={view} retry={refresh}>
                    <Table
                      rows={view.data?.items || []}
                      columns={historyColumns}
                      empty="This vehicle has no recorded visits."
                    />
                    <Pagination
                      offset={offset}
                      total={view.data?.total || 0}
                      onChange={setOffset}
                    />
                  </DataState>
                ) : (
                  <div className="empty">
                    Enter a registration number to view its visit history.
                  </div>
                )}
              </Card>
            ) : null}
            {page === "activity" ? (
              <>
                <Card>
                  <DataState state={view} retry={refresh}>
                    <ActivityTable rows={view.data || []} navigate={navigate} />
                  </DataState>
                </Card>
                {dashboard.data?.mock_ai ? (
                  <DemoControls notify={notify} refresh={refresh} />
                ) : null}
              </>
            ) : null}
            {page === "reviews" ? (
              <>
                <div className="info-note">
                  Review foundation: inspect the original reading, register a
                  verified vehicle in the registry, and record its movement
                  manually. Dismissing a review does not record an entry or
                  exit.
                </div>
                <Card>
                  <DataState state={view} retry={refresh}>
                    <Table
                      rows={view.data?.items || []}
                      empty="No readings need review."
                      columns={[
                        {
                          key: "raw_text",
                          label: "Original reading",
                          render: (row) => (
                            <div className="owner">
                              <strong className="mono">
                                {row.raw_text || "(empty reading)"}
                              </strong>
                              <small>
                                {row.sightings} sighting
                                {row.sightings === 1 ? "" : "s"}
                              </small>
                            </div>
                          ),
                        },
                        {
                          key: "confidence",
                          label: "Confidence",
                          render: (row) => (
                            <Badge tone="amber">
                              {Math.round(row.confidence * 100)}%
                            </Badge>
                          ),
                        },
                        { key: "reason", label: "Review reason" },
                        {
                          key: "timestamp",
                          label: "First seen · IST",
                          render: (row) => time(row.timestamp),
                        },
                        {
                          key: "actions",
                          label: "Action",
                          render: (row) => (
                            <button
                              className="button secondary small"
                              disabled={pending}
                              onClick={() => dismissReview(row.id)}
                            >
                              Dismiss review
                            </button>
                          ),
                        },
                      ]}
                    />
                    <Pagination
                      offset={offset}
                      total={view.data?.total || 0}
                      onChange={setOffset}
                    />
                  </DataState>
                </Card>
              </>
            ) : null}
          </>
        )}
      </Shell>
      <Notification item={notification} dismiss={() => setNotification(null)} />
      {form ? (
        <VehicleForm
          vehicle={form.id ? form : null}
          close={() => setForm(null)}
          save={saveVehicle}
        />
      ) : null}
      {movement ? (
        <MovementForm
          {...movement}
          cameras={dashboard.data?.cameras || []}
          save={saveMovement}
          close={() => setMovement(null)}
        />
      ) : null}
      {deactivate ? (
        <Modal title="Deactivate vehicle" close={() => setDeactivate(null)}>
          <p className="modal-description">
            <Plate>{deactivate.number_plate}</Plate> will remain in the registry
            and keep its history. New entries will be blocked until it is
            reactivated.
          </p>
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={pending}
              onClick={() => setDeactivate(null)}
            >
              Cancel
            </button>
            <button
              className="button"
              disabled={pending}
              onClick={async () => {
                setPending(true);
                try {
                  await api(`/vehicles/${deactivate.id}`, { method: "DELETE" });
                  setDeactivate(null);
                  notify("Vehicle deactivated.");
                  refresh();
                } catch (error) {
                  notify(error.message, true);
                } finally {
                  setPending(false);
                }
              }}
            >
              Deactivate vehicle
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
