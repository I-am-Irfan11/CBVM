export const API_URL = (import.meta.env.VITE_API_URL || "/api").replace(
  /\/$/,
  "",
);
export async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "omit",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join("; ")
      : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}
export function websocketURL() {
  const url = new URL(API_URL, window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = url.pathname.replace(/\/$/, "") + "/ws/events";
  return url.toString();
}
