import { useEffect, useState } from "react";
import { api } from "../services/api";
import { Modal } from "./ui";

const options = ["Student Pickup", "Student Drop", "College Activity", "NSS Trip", "Industry Visit", "Industrial Training", "Staff Duty", "Official College Work", "Maintenance", "Delivery", "Guest Visit", "Parent Visit", "Event", "Emergency", "Other"];

export default function ReviewForm({ review, close, notify, refresh }) {
  const [plate, setPlate] = useState(review.plate || "");
  const [purpose, setPurpose] = useState("Guest Visit");
  const [direction, setDirection] = useState("IN");
  const [custom, setCustom] = useState("");
  const [pending, setPending] = useState(false);
  const [scanUrl, setScanUrl] = useState("");
  useEffect(() => {
    if (!review.capture_key) return;
    let active = true;
    const encodedKey = review.capture_key.split("/").map(encodeURIComponent).join("/");
    api(`/anpr/scans/${encodedKey}`).then(({ url }) => {
      if (active) setScanUrl(url);
    }).catch(() => {});
    return () => { active = false; };
  }, [review.capture_key]);
  async function resolve(action) {
    setPending(true);
    try {
      await api(`/reviews/${review.id}/resolve`, { method: "POST", body: { action, number_plate: plate, purpose, direction, custom_purpose: custom || null } });
      notify(action === "confirm" ? "Reading confirmed and movement recorded." : "Reading rejected.");
      refresh(); close();
    } catch (error) { notify(error.message, true); }
    finally { setPending(false); }
  }
  return <Modal title="Review detected reading" close={close}>
    <p className="modal-description">Raw OCR: <strong>{review.raw_text || "No text"}</strong> · confidence {Math.round(review.confidence * 100)}% · {review.reason}</p>
    {scanUrl ? <img className="scan-preview" src={scanUrl} alt={`Plate scan from ${review.camera_id}`} /> : null}
    <label className="review-field">Corrected registration plate<input value={plate} onChange={e=>setPlate(e.target.value.toUpperCase())} required /></label>
    <label className="review-field">Purpose<select value={purpose} onChange={e=>setPurpose(e.target.value)}>{options.map(p=><option key={p}>{p}</option>)}</select></label>
    <label className="review-field">Gate movement<select value={direction} onChange={e=>setDirection(e.target.value)}><option value="IN">Entry</option><option value="OUT">Exit</option></select></label>
    {purpose === "Other" ? <label className="review-field">Custom purpose<input value={custom} onChange={e=>setCustom(e.target.value)} required /></label> : null}
    <div className="form-actions"><button className="button secondary" disabled={pending} onClick={()=>resolve("reject")}>Reject reading</button><button className="button" disabled={pending} onClick={()=>resolve("confirm")}>Confirm movement</button></div>
  </Modal>;
}
