import { useEffect, useState } from "react";
import { ArrowUpRight, CarFront, ShieldCheck } from "lucide-react";
import { api } from "../services/api";
import { supabase } from "../services/supabase";

export default function Login({ authError = "" }) {
  const [configured, setConfigured] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(authError);
  useEffect(() => {
    let active = true;
    api("/auth/config").then((value) => {
      if (active) setConfigured(value.google_sign_in && Boolean(supabase));
    }).catch(() => { if (active) setConfigured(false); });
    return () => { active = false; };
  }, []);

  async function signIn() {
    if (!supabase) return;
    setPending(true);
    setError("");
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (signInError) {
      setError(signInError.message);
      setPending(false);
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
        <p className="signup-copy">Create your GateLog account or sign in with Google. Your Google password stays with Google.</p>
        <div className="signup-rule" />
        <div className="signup-points">
          <div><ShieldCheck size={17} /><span>Google manages your sign-in</span></div>
          <div><CarFront size={17} /><span>Campus access is set by your administrator</span></div>
        </div>
        {configured ? (
          <button className="google-signup" type="button" onClick={signIn} disabled={pending} aria-label="Continue with Google">
            <span className="google-g" aria-hidden="true">G</span>
            {pending ? "Connecting to Google…" : "Continue with Google"}
            <ArrowUpRight size={17} />
          </button>
        ) : (
          <div className="signup-unavailable" role="status">
            <strong>Google sign-in needs setup</strong>
            <span>Connect Supabase and Google in the project settings to enable account creation.</span>
          </div>
        )}
        {error ? <div className="signup-unavailable" role="alert"><strong>Sign-in didn’t finish</strong><span>{error}</span></div> : null}
        <p className="signup-footnote">GateLog never asks for or stores your Google password.</p>
      </section>
      <div className="signup-rail" aria-hidden="true">
        <span>GATELOG</span><i /><span>ARRIVALS · DEPARTURES · RECORDS</span>
      </div>
    </main>
  );
}
