import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../App.jsx";
import { AuthProvider } from "../hooks/useAuth.jsx";
import { mockFetch } from "./mockFetch.js";

const ANON = { authenticated: false, mfa_pending: false, user: null, csrf_token: null };
const ALICE = { id: 1, username: "alice", display_name: "Alice Example", role: "subject", mfa_enabled: false };

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  );
}

const DASHBOARD = {
  role: "subject", consents: { active: 2, withdrawn: 1, expired: 0 }, access: { total: 3, allowed: 2, denied: 1, failed: 0 },
  open_cases: null, integrity: { valid: true, event_count: 10, finding_count: 0, checked_at: "2026-10-17T00:00:00Z" },
  recent_events: [],
};

describe("App integration (mocked API)", () => {
  it("redirects anonymous users to the sign-in page", async () => {
    mockFetch({ "GET /api/auth/session": () => [200, ANON] });
    renderApp("/consents");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("signs in and shows dashboard statistics from the API", async () => {
    const calls = mockFetch({
      "GET /api/auth/session": () => [200, ANON],
      "POST /api/auth/login": () => [200, { mfa_required: false, authenticated: true, user: ALICE, csrf_token: "c1" }],
      "GET /api/dashboard": () => [200, DASHBOARD],
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "Demo-Password-2026!");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: /welcome, alice example/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Valid")).toBeInTheDocument());
    expect(screen.getByText("Denied attempts").nextSibling).toHaveTextContent("1");
    expect(calls.find((c) => c.url === "/api/auth/login").body).toEqual({ username: "alice", password: "Demo-Password-2026!" });
  });

  it("routes to MFA verification when the backend requires a second factor", async () => {
    mockFetch({
      "GET /api/auth/session": () => [200, ANON],
      "POST /api/auth/login": () => [200, { mfa_required: true, csrf_token: "c2" }],
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Username"), "ivy");
    await userEvent.type(screen.getByLabelText("Password"), "Demo-Password-2026!");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Two-step verification" })).toBeInTheDocument();
  });

  it("shows the server's generic error on failed sign-in", async () => {
    mockFetch({
      "GET /api/auth/session": () => [200, ANON],
      "POST /api/auth/login": () => [401, { error: { code: "INVALID_CREDENTIALS", message: "Invalid username or password.", request_id: "r" } }],
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
  });

  it("hides investigator-only pages from other roles", async () => {
    mockFetch({ "GET /api/auth/session": () => [200, { authenticated: true, user: ALICE, csrf_token: "c" }] });
    renderApp("/cases");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("sends investigators without MFA to account security", async () => {
    mockFetch({
      "GET /api/auth/session": () => [200, { authenticated: true, csrf_token: "c",
        user: { ...ALICE, username: "ivy", role: "investigator", mfa_enabled: false, created_at: "2026-10-17T00:00:00Z" } }],
      "GET /api/auth/sessions": () => [200, { sessions: [] }],
    });
    renderApp("/cases");
    expect(await screen.findByRole("heading", { name: "Account security" })).toBeInTheDocument();
    expect(screen.getByText(/MFA required/)).toBeInTheDocument();
  });
});
