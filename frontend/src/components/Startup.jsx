import { useEffect, useState } from "react";
import { ScanLine, RefreshCw } from "lucide-react";

export default function Startup() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 8000);
    return () => clearTimeout(timer);
  }, []);
  return <main className="startup-screen" aria-busy="true">
    <div className="startup-brand"><ScanLine size={30} /><strong>GateLog</strong></div>
    <div className="startup-track" aria-hidden="true"><span /></div>
    <p role="status">{slow ? "The server is taking longer than usual." : "Opening your gate console"}</p>
    {slow ? <button className="button secondary" onClick={() => window.location.reload()}><RefreshCw size={16} /> Try again</button> : <small>Campus vehicle operations</small>}
  </main>;
}
