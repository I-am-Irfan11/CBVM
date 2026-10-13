import { useEffect, useState } from "react";
import { api } from "../services/api";
import { Modal } from "./ui";

const options = [
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

export default function ReviewForm({ review, close, notify, refresh }) {
  const [plate, setPlate] = useState(review.plate || "");
  const [plateLookup, setPlateLookup] = useState({ status: "idle", vehicle: null });
  const [purpose, setPurpose] = useState("Guest Visit");
  const [direction, setDirection] = useState("IN");
  const [custom, setCustom] = useState("");
  const [visitorName, setVisitorName] = useState("");
  const [phone, setPhone] = useState("");
  const [organization, setOrganization] = useState("");
  const [pending, setPending] = useState(false);
  const [scanUrl, setScanUrl] = useState("");
  const normalizedPlate = plate.replace(/[\s-]+/g, "").toUpperCase();
  useEffect(() => {
    if (normalizedPlate.length < 6) {
      setPlateLookup({ status: "idle", vehicle: null });
      return;
    }
    let active = true;
    setPlateLookup((current) => ({ status: "checking", vehicle: current.vehicle }));
    const timer = setTimeout(() => {
      api(`/vehicles/by-plate/${encodeURIComponent(normalizedPlate)}`)
        .then((vehicle) => {
          if (active) setPlateLookup({ status: "registered", vehicle });
        })
        .catch((error) => {
          if (!active) return;
          setPlateLookup({
            status: error.message === "Vehicle not found" ? "unknown" : "error",
            vehicle: null,
          });
        });
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [normalizedPlate]);
  useEffect(() => {
    if (!review.capture_key) return;
    let active = true;
    const encodedKey = review.capture_key
      .split("/")
      .map(encodeURIComponent)
      .join("/");
    api(`/anpr/scans/${encodedKey}`)
      .then(({ url }) => {
        if (active) setScanUrl(url);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [review.capture_key]);
  async function resolve(action) {
    setPending(true);
    try {
      if (action === "reject") {
        await api(`/reviews/${review.id}/dismiss`, { method: "POST" });
        notify("Reading rejected. No vehicle movement was recorded.");
        refresh();
        close();
        return;
      }
      await api(`/reviews/${review.id}/resolve`, {
        method: "POST",
        body: {
          action,
          number_plate: plate,
          visitor_name: visitorName || null,
          phone: phone || null,
          organization: organization || null,
          purpose,
          direction,
          custom_purpose: custom || null,
        },
      });
      notify(
        action === "confirm"
          ? "Reading confirmed and movement recorded."
          : "Reading rejected.",
      );
      refresh();
      close();
    } catch (error) {
      notify(error.message, true);
    } finally {
      setPending(false);
    }
  }
  return (
    <Modal title="Review detected reading" close={close}>
      <div className="review-content">
      <p className="modal-description review-ocr">
        Raw OCR: <strong>{review.raw_text || "No text"}</strong> · confidence{" "}
        {Math.round(review.confidence * 100)}% · {review.reason}
      </p>
      {scanUrl ? (
        <img
          className="scan-preview"
          src={scanUrl}
          alt={`Plate scan from ${review.camera_id}`}
        />
      ) : null}
      <label className="review-field review-plate">
        Type or correct registration plate
        <input
          value={plate}
          onChange={(e) => setPlate(e.target.value.toUpperCase())}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="e.g. TN09AB1234"
          required
        />
      </label>
      {plateLookup.status === "checking" ? (
        <p className="review-plate-status" role="status">Checking vehicle registry…</p>
      ) : null}
      {plateLookup.status === "registered" ? (
        <p className="review-plate-status registered" role="status">
          Already registered as <strong>{plateLookup.vehicle.owner_name}</strong> ({plateLookup.vehicle.vehicle_type}). Confirming records this movement against the existing plate.
        </p>
      ) : null}
      {plateLookup.status === "unknown" ? (
        <p className="modal-description review-hint">This plate is not in the vehicle registry. Add a visitor name to register it and record entry.</p>
      ) : null}
      {plateLookup.status === "error" ? (
        <p className="review-plate-status" role="status">Could not check the registry. You can still confirm and the server will check the plate.</p>
      ) : null}
      <div className="review-grid">
      {plateLookup.status !== "registered" ? <>
      <label className="review-field">
        Visitor name
        <input value={visitorName} onChange={(e) => setVisitorName(e.target.value)} required={plateLookup.status === "unknown"} />
      </label>
      <label className="review-field">
        Phone (optional)
        <input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <label className="review-field">
        Organization (optional)
        <input value={organization} onChange={(e) => setOrganization(e.target.value)} />
      </label>
      </> : null}
      <label className="review-field">
        Purpose
        <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
          {options.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
      </label>
      <label className="review-field">
        Gate movement
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value)}
        >
          <option value="IN">Entry</option>
          <option value="OUT">Exit</option>
        </select>
      </label>
      {purpose === "Other" ? (
        <label className="review-field">
          Custom purpose
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            required
          />
        </label>
      ) : null}
      </div>
      </div>
      <div className="form-actions">
        <button
          className="button secondary"
          disabled={pending}
          onClick={() => resolve("reject")}
        >
          Reject vehicle
        </button>
        <button
          className="button"
          disabled={pending || plateLookup.status === "checking" || (plateLookup.status === "unknown" && !visitorName.trim())}
          onClick={() => resolve("confirm")}
        >
          Confirm movement
        </button>
      </div>
    </Modal>
  );
}
