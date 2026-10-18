import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import App from "../App.jsx";
import { formatTime, reasonText } from "../api.js";

// Fake server: maps "METHOD /api/path" to [status, json]
function fakeServer(routes) {
  vi.stubGlobal("fetch", vi.fn(async (url, options = {}) => {
    const [status, json] = routes[`${options.method || "GET"} ${url}`] || [404, { error: "Not found." }];
    return new Response(JSON.stringify(json), { status });
  }));
}

function renderApp(path = "/") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const alice = { id: 1, username: "alice", name: "Alice Example", role: "user", two_step_enabled: false };

test("shows the login page when nobody is logged in", async () => {
  fakeServer({ "GET /api/me": [200, { user: null }] });
  renderApp();
  expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
});

test("logging in shows the menu for that role", async () => {
  fakeServer({
    "GET /api/me": [200, { user: null }],
    "POST /api/login": [200, { user: alice }],
  });
  renderApp();
  await userEvent.type(await screen.findByLabelText("Username"), "alice");
  await userEvent.type(screen.getByLabelText("Password"), "Demo-Password-2026!");
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect(await screen.findByText("Welcome, Alice Example")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "My permissions" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Alerts" })).not.toBeInTheDocument();
});

test("asks for the 6-digit code when two-step login is on", async () => {
  fakeServer({
    "GET /api/me": [200, { user: null }],
    "POST /api/login": [401, { error: "Enter the 6-digit code from your authenticator app.", need_code: true }],
  });
  renderApp();
  await userEvent.type(await screen.findByLabelText("Username"), "ivy");
  await userEvent.type(screen.getByLabelText("Password"), "Demo-Password-2026!");
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect(await screen.findByLabelText(/6-digit code/)).toBeInTheDocument();
});

test("a company sees shared data, and a blocked request shows the reason", async () => {
  fakeServer({
    "GET /api/me": [200, { user: { ...alice, role: "company", name: "Acme" } }],
    "GET /api/records": [200, {
      records: [
        { id: 5, title: "Blood test", category: "health", owner: "Alice", allowed_purposes: [] },
        { id: 6, title: "Contact details", category: "contact", owner: "Bob", allowed_purposes: ["marketing"] },
      ],
      purposes: ["research"], categories: ["health"],
    }],
    "POST /api/records/5/view": [403, { error: "Access blocked.", reason: "CONSENT_WITHDRAWN" }],
    "POST /api/records/6/view": [200, { record: {}, content: "Phone +1 555-0187" }],
  });
  renderApp("/records");
  expect(await screen.findByText("Shared with you (1)")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "View for marketing" }));
  expect(await screen.findByText("Phone +1 555-0187")).toBeInTheDocument();
  await userEvent.selectOptions(await screen.findByLabelText(/purpose/), "research");
  await userEvent.click(await screen.findByRole("button", { name: "Request" }));
  expect(await screen.findByText("Blocked: Permission was withdrawn")).toBeInTheDocument();
});

test("times are shown in Indian Standard Time", () => {
  expect(formatTime("2026-10-18T04:30:00.123456")).toMatch(/18 Oct 2026, 10:00 am IST/i);
  expect(formatTime(null)).toBe("-");
});

test("reason codes have readable text", () => {
  expect(reasonText("WRONG_PURPOSE")).toBe("Wrong purpose");
  expect(reasonText("SOMETHING_NEW")).toBe("SOMETHING_NEW");
});

test("the forensics page shows which log entries were deleted", async () => {
  const copy = { id: 1, saved_at: "2026-10-18T10:00:00", saved_by: "ivy", note: "", entries: 70, last_hash: "ab", file_sha256: "cd" };
  fakeServer({
    "GET /api/me": [200, { user: { ...alice, role: "investigator", name: "Ivy" } }],
    "GET /api/evidence": [200, { copies: [copy] }],
    "GET /api/cases": [200, { cases: [] }],
    "POST /api/evidence/1/compare": [200, {
      copy, tampered: true, copy_unchanged: true, last_hash_found: false, live_entries: 61,
      missing: [{ time: "2026-10-18T09:00:00", who: "quickloans", action: "record.view", target: "record 9",
        result: "denied", reason: "CONSENT_WITHDRAWN", details: "purpose=service" }],
    }],
  });
  renderApp("/forensics");
  await userEvent.click(await screen.findByRole("button", { name: "Compare with copy 1" }));
  expect(await screen.findByText("The log was tampered with.")).toBeInTheDocument();
  expect(screen.getByText("Permission was withdrawn")).toBeInTheDocument();
});
