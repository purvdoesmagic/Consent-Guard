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

// What each purpose means, in plain words
export const PURPOSE_TEXT = {
  service: "Service: to provide something the user asked for (e.g. a loan, a hospital visit)",
  research: "Research: studies, e.g. medical research",
  marketing: "Marketing: ads, offers and promotional calls or emails",
  analytics: "Analytics: statistics and trends",
};

// The server stores times in UTC. Show them in Indian Standard Time (UTC+5:30),
// e.g. "18 Oct 2026, 03:45 pm IST".
export function formatTime(iso) {
  if (!iso) return "-";
  const utc = new Date(iso.slice(0, 19) + "Z");
  const text = utc.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
  return text + " IST";
}
