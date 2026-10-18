import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import App from "../App.jsx";
import { reasonText } from "../api.js";

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

test("a blocked request shows the reason in plain English", async () => {
  fakeServer({
    "GET /api/me": [200, { user: { ...alice, role: "company", name: "Acme" } }],
    "GET /api/records": [200, {
      records: [{ id: 5, title: "Blood test", category: "health", owner: "Alice" }],
      purposes: ["research"], categories: ["health"],
    }],
    "POST /api/records/5/view": [403, { error: "Access blocked.", reason: "CONSENT_WITHDRAWN" }],
  });
  renderApp("/records");
  await userEvent.selectOptions(await screen.findByLabelText(/purpose/), "research");
  await userEvent.click(await screen.findByRole("button", { name: "Request" }));
  expect(await screen.findByText("Blocked: Permission was withdrawn")).toBeInTheDocument();
});

test("reason codes have readable text", () => {
  expect(reasonText("WRONG_PURPOSE")).toBe("Wrong purpose");
  expect(reasonText("SOMETHING_NEW")).toBe("SOMETHING_NEW");
});
