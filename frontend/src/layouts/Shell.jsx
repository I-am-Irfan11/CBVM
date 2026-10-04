import {
  LayoutDashboard,
  CarFront,
  LogIn,
  History,
  Radio,
  ScanLine,
  ShieldCheck,
  ArrowUpRight,
} from "lucide-react";

export const pages = [
  ["dashboard", "Dashboard", LayoutDashboard],
  ["registry", "Vehicle registry", CarFront],
  ["inside", "Currently inside", LogIn],
  ["history", "Vehicle history", History],
  ["activity", "Live activity", Radio],
  ["reviews", "Review queue", ScanLine],
  ["visitors", "Visitors", CarFront],
  ["buses", "Bus operations", CarFront],
  ["reports", "Reports", History],
  ["cameras", "Cameras", Radio],
  ["transport", "Transport references", CarFront],
  ["purposes", "Trip purposes", History],
  ["users", "User access", ShieldCheck],
  ["audit", "Audit log", ShieldCheck],
];
export default function Shell({
  page,
  navigate,
  status,
  dashboard,
  user,
  logout,
  children,
}) {
  const visiblePages =
    user?.role === "department_staff"
      ? pages.filter(([id]) => ["dashboard", "history", "reports"].includes(id))
      : user?.role === "security"
        ? pages.filter(([id]) => !["users", "audit", "purposes"].includes(id))
        : pages;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#dashboard"
          onClick={() => navigate("dashboard")}
        >
          <span className="brand-mark">
            <span />
            <span />
            <span />
          </span>
          <span>
            GateLog<small>CAMPUS OPERATIONS</small>
          </span>
        </a>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {visiblePages.map(([id, label, Icon]) => (
            <a
              href={`#${id}`}
              key={id}
              onClick={() => navigate(id)}
              className={page === id ? "active" : ""}
              aria-current={page === id ? "page" : undefined}
            >
              <Icon size={19} />
              <span>{label}</span>
              {id === "reviews" && dashboard?.pending_reviews > 0 ? (
                <b>{dashboard.pending_reviews}</b>
              ) : null}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <ShieldCheck size={24} />
          <strong>Campus security desk</strong>
          <p>Vehicle movement & trip-purpose records</p>
          <div className="desk-code">
            MAIN GATE <ArrowUpRight size={15} />
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            Campus security{" "}
            <span className="breadcrumb">
              / {visiblePages.find((item) => item[0] === page)?.[1]}
            </span>
          </span>
          <div className="topbar-status">
            <span
              className={`status-dot ${status === "connected" ? "" : "waiting"}`}
            />
            {status === "connected"
              ? "Live updates connected"
              : "Reconnecting live updates"}
            <span className="account-label">
              {user?.full_name} · {user?.role?.replaceAll("_", " ")}
            </span>
            <button
              className="button secondary small"
              onClick={logout}
              type="button"
            >
              Sign out
            </button>
          </div>
        </header>
        <main id="main-content">
          {dashboard?.database_mode === "memory" ? (
            <div className="demo-notice">
              DEMO WORKSPACE{" "}
              <span>In-memory data resets when the backend restarts.</span>
            </div>
          ) : null}
          {children}
        </main>
        <footer>
          GateLog / Campus vehicle operations{" "}
          <span>Campus gate operations · Times shown in IST</span>
        </footer>
      </div>
    </div>
  );
}
