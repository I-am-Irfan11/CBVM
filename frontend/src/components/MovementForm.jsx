import { useState } from "react";
import { Modal, Plate } from "./ui";
import { useApi } from "../hooks/useApi";

export default function MovementForm({
  vehicle,
  direction,
  cameras,
  save,
  close,
}) {
  const purposes = useApi("/purposes", 0);
  const eligible = cameras.filter((camera) => camera.direction === direction);
  const [purpose, setPurpose] = useState("Campus visit");
  const [camera, setCamera] = useState(eligible[0]?.id || "");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await save(vehicle.vehicle_id || vehicle.id, direction, {
        purpose,
        camera_id: camera,
        event_id: crypto.randomUUID(),
      });
      close();
    } catch (error) {
      setError(error.message);
    } finally {
      setPending(false);
    }
  }
  return (
    <Modal
      title={`Record ${direction === "IN" ? "entry" : "exit"}`}
      close={close}
    >
      <p className="mb-6">
        <Plate>{vehicle.number_plate}</Plate>
      </p>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label className="full">
            Gate camera
            <select
              required
              value={camera}
              onChange={(event) => setCamera(event.target.value)}
            >
              {eligible.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.camera_name}
                </option>
              ))}
            </select>
          </label>
          {direction === "IN" ? (
            <label className="full">
              Trip purpose
              <input
                required
                list="purposes"
                value={purpose}
                maxLength={120}
                onChange={(event) => setPurpose(event.target.value)}
              />
              <datalist id="purposes">
                {(purposes.data || []).map((item) => (
                  <option key={item.id} value={item.purpose_name} />
                ))}
              </datalist>
            </label>
          ) : null}
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button secondary"
            type="button"
            onClick={close}
            disabled={pending}
          >
            Cancel
          </button>
          <button className="button" disabled={pending || !camera}>
            {pending
              ? "Recording…"
              : `Record ${direction === "IN" ? "entry" : "exit"}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
