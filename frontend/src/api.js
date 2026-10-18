// Small helper for calling the Flask API.
// Throws an Error with the server's message when something goes wrong.
export async function api(path, method = "GET", body) {
  const options = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body || {});
  }

  let response;
  try {
    response = await fetch("/api" + path, options);
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "Something went wrong.");
    error.data = data;
    throw error;
  }
  return data;
}

// Plain-English text for the reason codes the server sends
const REASONS = {
  ALLOWED: "Allowed by permission",
  OWNER: "Own data",
  NO_CONSENT: "No permission given",
  WRONG_PURPOSE: "Wrong purpose",
  CATEGORY_NOT_ALLOWED: "Data type not allowed",
  CONSENT_WITHDRAWN: "Permission was withdrawn",
  CONSENT_EXPIRED: "Permission has expired",
  NOT_A_COMPANY: "Only companies can request data",
  WRONG_PASSWORD: "Wrong password",
  WRONG_CODE: "Wrong 6-digit code",
  WRONG_ROLE: "Not allowed for this role",
};

export function reasonText(code) {
  return REASONS[code] || code || "";
}

export function formatTime(iso) {
  return iso ? iso.slice(0, 16).replace("T", " ") + " UTC" : "-";
}
