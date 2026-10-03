import { useEffect, useState } from "react";
import { ScanLine } from "lucide-react";
import { api } from "../services/api";

export default function DemoControls({ notify, refresh }) {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleId, setVehicleId] = useState("");
  const [direction, setDirection] = useState("IN");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let active = true;
    api("/vehicles?limit=100").then((data) => {
      if (!active) return;
      const activeVehicles = (data.items || []).filter((vehicle) => vehicle.status === "active");
      setVehicles(activeVehicles);
      setVehicleId((current) => current || activeVehicles[0]?.id || "");
    }).catch((error) => notify(error.message, true));
    return () => { active = false; };
  }, [notify]);

  async function detect() {
    setPending(true);
    try {
      const data = await api("/detections/mock", {
        method: "POST",
        body: { vehicle_id: vehicleId, direction },
      });
      notify(
        data.outcome === "review"
          ? `Sent to review: ${data.review.reason}`
          : data.outcome === "duplicate"
            ? "Repeated detection ignored; no new movement recorded."
            : `${data.detection.plate} · ${direction === "IN" ? "entry" : "exit"} recorded`,
      );
      refresh();
    } catch (error) {
      notify(error.message, true);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="demo-panel">
      <div>
        <span className="eyebrow">DETECTION SIMULATOR</span>
        <h3>Put a registered vehicle through the gate</h3>
        <p>The simulator reads the plate and vehicle details from your registry.</p>
      </div>
      <div className="demo-controls">
        <label className="sr-only" htmlFor="mock-vehicle">Registered vehicle</label>
        <select id="mock-vehicle" value={vehicleId} onChange={(event) => setVehicleId(event.target.value)}>
          <option value="">Select registered vehicle</option>
          {vehicles.map((vehicle) => (
            <option key={vehicle.id} value={vehicle.id}>
              {vehicle.number_plate} · {vehicle.owner_name}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="mock-direction">Direction</label>
        <select id="mock-direction" value={direction} onChange={(event) => setDirection(event.target.value)}>
          <option value="IN">Entry</option>
          <option value="OUT">Exit</option>
        </select>
        <button className="button" onClick={detect} disabled={pending || !vehicleId}>
          <ScanLine size={17} />
          {pending ? "Detecting…" : "Run detection"}
        </button>
      </div>
      {!vehicles.length ? <p className="demo-empty">Register an active vehicle first. It will appear here automatically.</p> : null}
    </section>
  );
}
