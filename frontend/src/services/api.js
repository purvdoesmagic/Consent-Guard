// Thin fetch wrapper for the ConsentGuard API.
// - Sends cookies (same origin) and the per-session CSRF token on writes.
// - Normalizes errors into ApiError with the server's code/message/request id.
// Authorization is enforced by the backend; nothing here is a security control.

let csrfToken = null;
let unauthorizedHandler = null;

export function setCsrfToken(token) {
  csrfToken = token || null;
}

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  constructor(status, code, message, details, requestId) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export async function api(path, { method = "GET", body, raw = false, signal } = {}) {
  const headers = { Accept: raw ? "application/pdf" : "application/json" };
  const init = { method, headers, credentials: "same-origin", signal };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body ?? {});
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }

  let response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the ConsentGuard server. Is the backend running?");
  }

  if (raw && response.ok) return response;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const e = data?.error ?? {};
    const error = new ApiError(
      response.status,
      e.code ?? "HTTP_ERROR",
      e.message ?? `Request failed with status ${response.status}.`,
      e.details,
      e.request_id ?? response.headers.get("X-Request-ID"),
    );
    if (response.status === 401 && unauthorizedHandler && error.code === "AUTHENTICATION_REQUIRED") {
      unauthorizedHandler(error);
    }
    throw error;
  }
  if (data && typeof data === "object" && data.csrf_token) setCsrfToken(data.csrf_token);
  return data;
}

export function queryString(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export async function downloadFile(path, fallbackName) {
  const response = await api(path, { raw: true });
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match ? match[1] : fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
