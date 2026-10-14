export const API_URL = (import.meta.env?.VITE_API_URL || "/api").replace(
  /\/$/,
  "",
);
let csrfToken = "";
export function setCsrfToken(value) {
  csrfToken = value || "";
}
export function getCsrfToken() {
  return csrfToken;
}
export async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.method && options.method !== "GET"
        ? { "X-CSRF-Token": csrfToken }
        : {}),
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  return readResponse(response);
}

export async function readResponse(response) {
  const responseText = await response.text();
  let data;
  try {
    data = responseText ? JSON.parse(responseText) : {};
  } catch {
    if (response.ok)
      throw new Error(
        "The service returned an incomplete response. Check Recent activity before trying again.",
      );
    data = {};
  }
  if (!response.ok) {
    const detail = Array.isArray(data?.detail)
      ? data?.detail
          .map((item) => `${item.loc?.at(-1) || "Request"}: ${item.msg}`)
          .join("; ")
      : data?.detail;
    const message =
      response.status >= 500
        ? "The service is temporarily unavailable. Please try again shortly."
        : typeof detail === "string"
          ? detail
          : "We couldn’t complete this request. Please try again.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}
export function websocketURL() {
  const url = new URL(API_URL, window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = url.pathname.replace(/\/$/, "") + "/ws/events";
  return url.toString();
}
