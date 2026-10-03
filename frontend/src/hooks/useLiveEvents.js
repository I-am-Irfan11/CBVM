import { useEffect, useState } from "react";
import { websocketURL } from "../services/api";

export function useLiveEvents(refresh) {
  const [status, setStatus] = useState("connecting");
  useEffect(() => {
    let stopped = false,
      socket,
      reconnect,
      refreshTimer,
      attempts = 0;
    function connect() {
      socket = new WebSocket(websocketURL());
      socket.onopen = () => {
        attempts = 0;
        setStatus("connected");
        refresh();
      };
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (!["connected", "heartbeat"].includes(data.type)) {
            clearTimeout(refreshTimer);
            refreshTimer = setTimeout(refresh, 150);
          }
        } catch {
          /* A malformed event must not break the dashboard. */
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        setStatus("reconnecting");
        reconnect = setTimeout(
          connect,
          Math.min(1000 * 2 ** attempts++, 15000),
        );
      };
      socket.onerror = () => socket.close();
    }
    connect();
    const poll = setInterval(refresh, 30000);
    return () => {
      stopped = true;
      clearInterval(poll);
      clearTimeout(reconnect);
      clearTimeout(refreshTimer);
      socket.close();
    };
  }, [refresh]);
  return status;
}
