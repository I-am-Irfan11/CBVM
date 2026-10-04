import { useState } from "react";
import { CarFront } from "lucide-react";
import { api, setCsrfToken } from "../services/api";

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState("signin");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");

  function switchMode(next) {
    setMode(next);
    setError("");
    setPending(false);
  }

  function authenticated(result) {
    if (result.csrf_token) setCsrfToken(result.csrf_token);
    onAuthenticated?.(result.user);
  }

  async function signIn(event) {
    event.preventDefault();
    const trimmed = identifier.trim();
    if (trimmed.includes(" ") && !trimmed.includes("@")) {
      setError("Use your username or email address, not your full name.");
      return;
    }
    setPending(true);
    setError("");
    try {
      authenticated(
        await api("/auth/login", {
          method: "POST",
          body: { identifier: trimmed, password },
        }),
      );
    } catch (requestError) {
      setError(requestError.message);
      setPending(false);
    }
  }

  async function signUp(event) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      authenticated(
        await api("/auth/signup", {
          method: "POST",
          body: {
            username: username.trim().toLowerCase(),
            email: email.trim().toLowerCase(),
            full_name: fullName.trim(),
            password: newPassword,
          },
        }),
      );
    } catch (requestError) {
      setError(requestError.message);
      setPending(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-mark" aria-hidden="true">
          <CarFront size={24} strokeWidth={1.8} />
        </div>
        {mode === "signin" ? (
          <>
            <h1 id="login-title">Sign in to GateLog</h1>
            <p className="login-sub">
              Use your GateLog username or email address.
            </p>
            <form className="login-form" onSubmit={signIn}>
              <label>
                Username or email
                <input
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  required
                  autoComplete="username"
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                />
              </label>
              {error ? (
                <div className="login-error" role="alert">
                  {error}
                </div>
              ) : null}
              <button className="button login-submit" disabled={pending}>
                {pending ? "Signing in…" : "Sign in"}
              </button>
            </form>
            <p className="login-switch">
              New to GateLog?{" "}
              <button type="button" onClick={() => switchMode("signup")}>
                Create an account
              </button>
            </p>
          </>
        ) : (
          <>
            <h1 id="login-title">Create your account</h1>
            <p className="login-sub">
              New accounts start with the security role. Your administrator can
              adjust access later.
            </p>
            <form className="login-form" onSubmit={signUp}>
              <label>
                Full name
                <input
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  required
                  autoComplete="name"
                />
              </label>
              <label>
                Username
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                  minLength={3}
                  autoComplete="username"
                />
                <small className="field-hint">
                  Letters, numbers, dot, dash and underscore only — no spaces.
                </small>
              </label>
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  autoComplete="email"
                />
              </label>
              <label>
                Password (12+ characters)
                <input
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  required
                  minLength={12}
                  autoComplete="new-password"
                />
              </label>
              {error ? (
                <div className="login-error" role="alert">
                  {error}
                </div>
              ) : null}
              <button className="button login-submit" disabled={pending}>
                {pending ? "Creating account…" : "Create account"}
              </button>
            </form>
            <p className="login-switch">
              Already have an account?{" "}
              <button type="button" onClick={() => switchMode("signin")}>
                Sign in
              </button>
            </p>
          </>
        )}
      </section>
    </main>
  );
}
