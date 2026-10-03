import { useEffect, useState } from "react";
import { ArrowUpRight, CarFront, ShieldCheck } from "lucide-react";
import { api } from "../services/api";

export default function Login() {
  const [configured, setConfigured] = useState(null);
  useEffect(() => {
    let active = true;
    api("/auth/config").then((value) => {
      if (active) setConfigured(value.google_sign_in);
    }).catch(() => {
      if (active) setConfigured(false);
    });
    return () => { active = false; };
  }, []);

  return (
    <main className="signup-page">
      <section className="signup-card" aria-labelledby="signup-title">
        <div className="signup-mark" aria-hidden="true">
          <CarFront size={24} strokeWidth={1.8} />
        </div>
        <span className="eyebrow">CAMPUS GATE OPERATIONS</span>
        <h1 id="signup-title">Your gate, in view.</h1>
        <p className="signup-copy">Create your GateLog account with your Google account. Your sign-in is managed by Cloudflare Access.</p>
        <div className="signup-rule" />
        <div className="signup-points">
          <div><ShieldCheck size={17} /><span>Google manages your sign-in</span></div>
          <div><CarFront size={17} /><span>Campus access is set by your administrator</span></div>
        </div>
        {configured ? (
          <a className="google-signup" href="/cdn-cgi/access/login" aria-label="Continue with Google">
            <span className="google-g" aria-hidden="true">G</span>
            Continue with Google
            <ArrowUpRight size={17} />
          </a>
        ) : (
          <div className="signup-unavailable" role="status">
            <strong>Google sign-in needs setup</strong>
            <span>Connect this site to Cloudflare Access and add your Google identity provider to enable account creation.</span>
          </div>
        )}
        <p className="signup-footnote">GateLog does not ask for or store your Google password.</p>
      </section>
      <div className="signup-rail" aria-hidden="true">
        <span>GATELOG</span><i /><span>ARRIVALS · DEPARTURES · RECORDS</span>
      </div>
    </main>
  );
}
