import { useEffect, useState } from "react";
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  getRedirectResult,
  onAuthStateChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithRedirect,
  updateProfile,
} from "firebase/auth";
import { CarFront } from "lucide-react";
import { api, setCsrfToken } from "../services/api";
import { firebaseAuth, firebaseConfigured } from "../services/firebase";

export default function Login({ onAuthenticated }) {
  const [createAccount, setCreateAccount] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [currentUser, setCurrentUser] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!firebaseAuth) return;
    const unsubscribe = onAuthStateChanged(firebaseAuth, setCurrentUser);
    getRedirectResult(firebaseAuth)
      .then((credential) => {
        if (credential) return finishSignIn(credential.user);
      })
      .catch((cause) => {
        setError(cause?.message || "Google sign-in could not be completed.");
      });
    return unsubscribe;
  }, []);

  async function finishSignIn(firebaseUser) {
    const result = await api("/auth/firebase", {
      method: "POST",
      body: { id_token: await firebaseUser.getIdToken() },
    });
    setCsrfToken(result.csrf_token);
    onAuthenticated?.(result.user);
  }

  async function run(action) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
    } catch (cause) {
      setError(
        cause?.code === "auth/unauthorized-domain"
          ? "Add this website domain under Firebase Authentication → Settings → Authorized domains."
          : cause?.message ||
              "Sign-in could not be completed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  function emailAction(event) {
    event.preventDefault();
    run(async () => {
      if (createAccount) {
        const credential = await createUserWithEmailAndPassword(
          firebaseAuth,
          email.trim(),
          password,
        );
        if (name.trim())
          await updateProfile(credential.user, { displayName: name.trim() });
        await sendEmailVerification(credential.user);
        setMessage(
          "Account created. Verify your email, then return here and sign in.",
        );
        return;
      }
      const credential = await signInWithEmailAndPassword(
        firebaseAuth,
        email.trim(),
        password,
      );
      await finishSignIn(credential.user);
    });
  }

  function googleSignIn() {
    run(async () => {
      const provider = new GoogleAuthProvider();
      try {
        const credential = await signInWithPopup(firebaseAuth, provider);
        await finishSignIn(credential.user);
      } catch (cause) {
        if (cause?.code !== "auth/popup-blocked") throw cause;
        await signInWithRedirect(firebaseAuth, provider);
      }
    });
  }

  return (
    <main className="login-screen">
      <section
        className="login-card firebase-login"
        aria-labelledby="login-title"
      >
        <div className="login-mark" aria-hidden="true">
          <CarFront size={24} strokeWidth={1.8} />
        </div>
        <span className="eyebrow">CAMPUS GATE OPERATIONS</span>
        <h1 id="login-title">Your gate, in view.</h1>
        {!firebaseConfigured ? (
          <div className="login-alert" role="status">
            Firebase setup is not connected yet. Add the Firebase web app
            settings to Vercel and redeploy.
          </div>
        ) : (
          <>
            <form className="login-form firebase-form" onSubmit={emailAction}>
              {createAccount ? (
                <label>
                  Full name
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    autoComplete="name"
                    required
                  />
                </label>
              ) : null}
              <label>
                Email address
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  required
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete={
                    createAccount ? "new-password" : "current-password"
                  }
                  minLength={6}
                  required
                />
              </label>
              <button className="button login-submit" disabled={busy}>
                {busy
                  ? "Please wait…"
                  : createAccount
                    ? "Create account"
                    : "Sign in with email"}
              </button>
              <button
                className="text-button"
                type="button"
                onClick={() => {
                  setCreateAccount(!createAccount);
                  setError("");
                  setMessage("");
                }}
              >
                {createAccount
                  ? "Already have an account? Sign in"
                  : "New to GateLog? Create an account"}
              </button>
            </form>
            <div className="auth-divider">
              <span>or</span>
            </div>
            <button
              className="button google-login"
              type="button"
              onClick={googleSignIn}
              disabled={busy}
            >
              <span className="google-mark">G</span> Continue with Google{" "}
              <span aria-hidden="true">↗</span>
            </button>
            {currentUser?.emailVerified ? (
              <button
                className="button secondary login-continue"
                type="button"
                disabled={busy}
                onClick={() => run(() => finishSignIn(currentUser))}
              >
                Continue as {currentUser.displayName || currentUser.email}
              </button>
            ) : null}
          </>
        )}
        {message ? (
          <div className="login-success" role="status">
            {message}
          </div>
        ) : null}
        {error ? (
          <div className="login-alert" role="alert">
            <strong>Sign-in didn’t finish</strong>
            <span>{error}</span>
          </div>
        ) : null}
      </section>
    </main>
  );
}
