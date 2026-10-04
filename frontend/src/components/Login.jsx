import { useEffect, useState } from "react";
import { ArrowUpRight, CarFront, ShieldCheck } from "lucide-react";
import { api, setCsrfToken } from "../services/api";
import { supabase } from "../services/supabase";

export default function Login({ authError = "", onAuthenticated }) {
  const [mode, setMode] = useState("signin");
  const [googleAvailable, setGoogleAvailable] = useState(false);
  const [pending, setPending] = useState(false);
  const [googlePending, setGooglePending] = useState(false);
  const [error, setError] = useState(authError);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  useEffect(() => {
    let active = true;
    api("/auth/config")
      .then((value) => {
        if (active)
          setGoogleAvailable(value.google_sign_in && Boolean(supabase));
      })
      .catch(() => {
        if (active) setGoogleAvailable(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function authenticated(result) {
    if (result.csrf_token) setCsrfToken(result.csrf_token);
    onAuthenticated?.(result.user);
  }

  async function signIn(event) {
    event.preventDefault();
    setPending(true);
    setError("");
    const trimmed = identifier.trim();
    if (trimmed.includes(" ") && !trimmed.includes("@")) {
      setError(
        "That looks like a full name. Sign in with the username or email address you registered with instead.",
      );
      setPending(false);
      return;
    }
    try {
      const result = await api("/auth/login", {
        method: "POST",
        body: { identifier: trimmed, password },
      });
      authenticated(result);
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
      const result = await api("/auth/signup", {
        method: "POST",
        body: {
          username: username.trim().toLowerCase(),
          email: email.trim().toLowerCase(),
          full_name: fullName.trim(),
          password: newPassword,
        },
      });
      authenticated(result);
    } catch (requestError) {
      setError(requestError.message);
      setPending(false);
    }
  }

  async function signInWithGoogle() {
    if (!supabase) return;
    setGooglePending(true);
    setError("");
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (signInError) {
      setError(signInError.message);
      setGooglePending(false);
    }
  }

  return (
    <main className="signup-page">
      <section className="signup-card" aria-labelledby="signup-title">
        <div className="signup-mark" aria-hidden="true">
          <CarFront size={24} strokeWidth={1.8} />
        </div>
        <span className="eyebrow">CAMPUS GATE OPERATIONS</span>
        <h1 id="signup-title">Your gate, in view.</h1>
        <p className="signup-copy">
          Sign in with your GateLog account or create one. New accounts start
          with the security role; your administrator can adjust access.
        </p>
        <div className="signup-rule" />
        <div
          className="tab-row"
          role="tablist"
          aria-label="Sign in or create account"
        >
          <button
            className={`button${mode === "signin" ? "" : " secondary"}`}
            role="tab"
            aria-selected={mode === "signin"}
            type="button"
            onClick={() => {
              setMode("signin");
              setError("");
            }}
          >
            Sign in
          </button>
          <button
            className={`button${mode === "signup" ? "" : " secondary"}`}
            role="tab"
            aria-selected={mode === "signup"}
            type="button"
            onClick={() => {
              setMode("signup");
              setError("");
            }}
          >
            Create account
          </button>
        </div>
        {mode === "signin" ? (
          <form className="ops-form" onSubmit={signIn}>
            <label>
              Username or email
              <input
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                required
                autoComplete="username"
                placeholder="e.g. irfan_desk01 or you@campus.edu"
              />
              <small className="field-hint">
                Use the username or email you registered with — not your full
                name.
              </small>
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
            <button className="button" disabled={pending} type="submit">
              {pending ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <form className="ops-form" onSubmit={signUp}>
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
                placeholder="e.g. irfan_desk01"
              />
              <small className="field-hint">
                Letters, numbers, dot, dash and underscore only — no spaces. You
                will sign in with this.
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
              GateLog password (12+ characters; not your Google password)
              <input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
                minLength={12}
                autoComplete="new-password"
              />
            </label>
            <button className="button" disabled={pending} type="submit">
              {pending ? "Creating account…" : "Create account"}
            </button>
          </form>
        )}
        {googleAvailable ? (
          <button
            className="google-signup"
            type="button"
            onClick={signInWithGoogle}
            disabled={googlePending}
            aria-label="Continue with Google"
          >
            <span className="google-g" aria-hidden="true">
              G
            </span>
            {googlePending ? "Connecting to Google…" : "Continue with Google"}
            <ArrowUpRight size={17} />
          </button>
        ) : null}
        <div className="signup-points">
          <div>
            <ShieldCheck size={17} />
            <span>Campus access is set by your administrator</span>
          </div>
          <div>
            <CarFront size={17} />
            <span>GateLog never asks for your Google password</span>
          </div>
        </div>
        {error ? (
          <div className="signup-unavailable" role="alert">
            <strong>Sign-in didn’t finish</strong>
            <span>{error}</span>
          </div>
        ) : null}
      </section>
      <div className="signup-rail" aria-hidden="true">
        <span>GATELOG</span>
        <i />
        <span>ARRIVALS · DEPARTURES · RECORDS</span>
      </div>
    </main>
  );
}
