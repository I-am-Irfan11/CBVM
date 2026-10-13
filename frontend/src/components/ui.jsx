import { useEffect, useRef } from "react";
import { X, ArrowRight } from "lucide-react";

export function Card({ children, className = "" }) {
  return <section className={`card ${className}`}>{children}</section>;
}
export function Badge({ children, tone = "" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Plate({ children }) {
  return <span className="plate">{children}</span>;
}
export function Notification({ item, dismiss }) {
  if (!item) return null;
  return (
    <div
      className={`notification ${item.error ? "failure" : ""}`}
      role={item.error ? "alert" : "status"}
    >
      <span>{item.text}</span>
      <button aria-label="Dismiss notification" onClick={dismiss}>
        <X size={18} />
      </button>
    </div>
  );
}
export function DataState({ state, children, retry }) {
  if (state.error)
    return (
      <div className="empty error" role="alert">
        <strong>Couldn’t load this view</strong>
        <p>{state.error}</p>
        <button className="button secondary" onClick={retry}>
          Try again
        </button>
      </div>
    );
  if (!state.data && state.loading)
    return (
      <div className="empty" role="status">
        Loading campus records…
      </div>
    );
  return children;
}
export function Table({
  columns,
  rows,
  empty = "No records yet.",
  rowKey = "id",
  className = "",
}) {
  return (
    <div className={`table-scroll ${className}`.trim()}>
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row) => (
              <tr key={row[rowKey]}>
                {columns.map((column) => (
                  <td key={column.key}>
                    {column.render
                      ? column.render(row)
                      : row[column.key] || "—"}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length}>
                <div className="empty">{empty}</div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
export function Pagination({ offset, total, onChange, size = 25 }) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + size, total)} of ${total}`
          : "0 records"}
      </span>
      <div className="flex gap-2">
        <button
          className="button secondary small"
          disabled={!offset}
          onClick={() => onChange(Math.max(0, offset - size))}
        >
          Previous
        </button>
        <button
          className="button secondary small"
          disabled={offset + size >= total}
          onClick={() => onChange(offset + size)}
        >
          Next <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
export function Modal({ title, children, close }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      aria-labelledby="modal-title"
    >
      <div className="modal-heading">
        <h2 id="modal-title">{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={close}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function time(value) {
  return value
    ? new Date(value).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}
export function duration(seconds) {
  if (seconds === null || seconds === undefined) return "In progress";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return String(Math.floor(seconds)) + "s";
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}h ${minutes % 60}m`
    : `${minutes}m`;
}
