import { useState } from "react";
import { CarFront } from "lucide-react";

// Must match backend/app/routers/auth.py::DEMO_COOKIE.
const DEMO_COOKIE = "gatelog_demo";

// Mirrors backend/app/services/auth.py::demo_user. Rendered as admin so the demo
// can reach every page; nothing here is a real account.
function demoUser(fullName) {
  return {
    id: "demo-open-access",
    username: "demo",
    email: "demo@gatelog.local",
    full_name: fullName.trim() || "Demo Operator",
    role: "admin",
    department: null,
    auth_provider: "demo",
  };
}

export default function Login({ onAuthenticated }) {
  const [fullName, setFullName] = useState("");

  function enter(event) {
    event.preventDefault();
    // Tells /auth/me to report a signed-in demo identity so a reload stays
    // inside the console instead of returning to this screen.
    document.cookie = `${DEMO_COOKIE}=1; Path=/; SameSite=Lax`;
    onAuthenticated?.(demoUser(fullName));
  }

  return (
    <main className="login-screen">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-mark" aria-hidden="true">
          <CarFront size={24} strokeWidth={1.8} />
        </div>
        <h1 id="login-title">Sign in to GateLog</h1>
        <p className="login-sub">
          Demo entrance. No account or password is checked — continue straight
          into the console.
        </p>
        <form className="login-form" onSubmit={enter}>
          <label>
            Display name
            <input
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Demo Operator"
              autoComplete="off"
            />
          </label>
          <small className="field-hint">
            Optional. Leave blank to appear as Demo Operator.
          </small>
          <button className="button login-submit">Enter GateLog</button>
        </form>
        <p className="login-switch">
          Demo access only. Real accounts, passwords and roles are bypassed
          while <code>DEMO_OPEN_ACCESS</code> is enabled.
        </p>
      </section>
    </main>
  );
}
