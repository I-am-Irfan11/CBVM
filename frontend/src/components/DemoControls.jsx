import { useState } from "react";
import { ScanLine } from "lucide-react";
import { api } from "../services/api";

export default function DemoControls({ notify, refresh }) {
  const [scenario, setScenario] = useState("student");
  const [direction, setDirection] = useState("IN");
  const [pending, setPending] = useState(false);
  async function detect() {
    setPending(true);
    try {
      const data = await api("/detections/mock", {
        method: "POST",
        body: { scenario, direction },
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
        <h3>Put a vehicle through the gate</h3>
        <p>Test recognition, movement logging, and review routing.</p>
      </div>
      <div className="demo-controls">
        <label className="sr-only" htmlFor="scenario">
          Detection scenario
        </label>
        <select
          id="scenario"
          value={scenario}
          onChange={(event) => setScenario(event.target.value)}
        >
          {[
            "student",
            "staff",
            "bus",
            "service",
            "unknown",
            "low_confidence",
          ].map((item) => (
            <option key={item} value={item}>
              {item.replace("_", " ")}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="direction">
          Detection direction
        </label>
        <select
          id="direction"
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
        >
          <option value="IN">Entry</option>
          <option value="OUT">Exit</option>
        </select>
        <button className="button" onClick={detect} disabled={pending}>
          <ScanLine size={17} />
          {pending ? "Detecting…" : "Run detection"}
        </button>
      </div>
    </section>
  );
}
