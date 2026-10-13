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
  const [purpose, setPurpose] = useState("Guest Visit");
  const [direction, setDirection] = useState("IN");
  const [custom, setCustom] = useState("");
  const [visitorName, setVisitorName] = useState("");
  const [phone, setPhone] = useState("");
  const [organization, setOrganization] = useState("");
  const [hostDepartment, setHostDepartment] = useState("");
  const [personToVisit, setPersonToVisit] = useState("");
  const [pending, setPending] = useState(false);
  const [scanUrl, setScanUrl] = useState("");
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
          host_department: hostDepartment || null,
          person_to_visit: personToVisit || null,
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
      <p className="modal-description review-hint">For an unregistered visitor vehicle, add their details. Confirming will register the plate and record entry.</p>
      <div className="review-grid">
      <label className="review-field">
        Visitor name
        <input value={visitorName} onChange={(e) => setVisitorName(e.target.value)} />
      </label>
      <label className="review-field">
        Phone (optional)
        <input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <label className="review-field">
        Organization (optional)
        <input value={organization} onChange={(e) => setOrganization(e.target.value)} />
      </label>
      <label className="review-field">
        Host department (optional)
        <input value={hostDepartment} onChange={(e) => setHostDepartment(e.target.value)} />
      </label>
      <label className="review-field">
        Person to visit (optional)
        <input value={personToVisit} onChange={(e) => setPersonToVisit(e.target.value)} />
      </label>
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
          disabled={pending}
          onClick={() => resolve("confirm")}
        >
          Confirm movement
        </button>
      </div>
    </Modal>
  );
}
