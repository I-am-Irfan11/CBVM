import { useState } from "react";
import { Modal } from "./ui";

export const vehicleTypes = [
  "student",
  "staff",
  "bus",
  "visitor",
  "service",
  "emergency",
  "other",
];
export default function VehicleForm({ vehicle, close, save }) {
  const [values, setValues] = useState(
    vehicle || {
      number_plate: "",
      owner_name: "",
      vehicle_type: "student",
      student_id: "",
      department: "",
      vehicle_model: "",
      status: "active",
    },
  );
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const field = (name) => ({
    value: values[name] || "",
    onChange: (event) =>
      setValues((old) => ({ ...old, [name]: event.target.value })),
  });
  async function submit(event) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const payload = Object.fromEntries(
        [
          "number_plate",
          "owner_name",
          "vehicle_type",
          "student_id",
          "department",
          "vehicle_model",
          "status",
        ].map((key) => [key, values[key] || null]),
      );
      await save(payload, vehicle?.id);
      close();
    } catch (error) {
      setError(error.message);
    } finally {
      setPending(false);
    }
  }
  return (
    <Modal title={vehicle ? "Edit vehicle" : "Register vehicle"} close={close}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Registration number
            <input
              {...field("number_plate")}
              required
              maxLength={20}
              placeholder="TN09AB1234"
              autoFocus
            />
          </label>
          <label>
            Vehicle type
            <select {...field("vehicle_type")}>
              {vehicleTypes.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </label>
          <label className="full">
            Owner name
            <input
              {...field("owner_name")}
              required
              maxLength={100}
              placeholder="Name or organization"
            />
          </label>
          <label>
            Department
            <input {...field("department")} maxLength={100} />
          </label>
          <label>
            Student ID
            <input {...field("student_id")} maxLength={40} />
          </label>
          <label>
            Vehicle model
            <input {...field("vehicle_model")} maxLength={80} />
          </label>
          <label>
            Status
            <select {...field("status")}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="form-actions">
          <button
            type="button"
            className="button secondary"
            disabled={pending}
            onClick={close}
          >
            Cancel
          </button>
          <button className="button" disabled={pending}>
            {pending
              ? "Saving…"
              : vehicle
                ? "Save changes"
                : "Register vehicle"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
