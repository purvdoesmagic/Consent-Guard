import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, queryString, setCsrfToken } from "../services/api.js";
import { mockFetch } from "./mockFetch.js";

describe("api client", () => {
  beforeEach(() => setCsrfToken(null));

  it("sends the CSRF token on state-changing requests only", async () => {
    const calls = mockFetch({
      "GET /api/auth/session": () => [200, { authenticated: true, csrf_token: "tok-1" }],
      "POST /api/consents": () => [201, { consent: { id: 1 } }],
    });
    await api("/auth/session");
    await api("/consents", { method: "POST", body: { purpose: "x" } });
    expect(calls[0].headers["X-CSRF-Token"]).toBeUndefined();
    expect(calls[1].headers["X-CSRF-Token"]).toBe("tok-1");
    expect(calls[1].headers["Content-Type"]).toBe("application/json");
    expect(calls[1].body).toEqual({ purpose: "x" });
  });

  it("throws ApiError carrying the server error code and request id", async () => {
    mockFetch({
      "POST /api/records/abc/access": () => [403, {
        error: { code: "DENY_CONSENT_WITHDRAWN", message: "Access denied.", request_id: "req-9", details: { reason: "DENY_CONSENT_WITHDRAWN" } },
      }],
    });
    const err = await api("/records/abc/access", { method: "POST", body: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe("DENY_CONSENT_WITHDRAWN");
    expect(err.requestId).toBe("req-9");
    expect(err.details.reason).toBe("DENY_CONSENT_WITHDRAWN");
  });

  it("reports network failures clearly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await api("/health").catch((e) => e);
    expect(err.code).toBe("NETWORK_ERROR");
  });

  it("builds query strings without empty values", () => {
    expect(queryString({ a: 1, b: "", c: null, d: "x y" })).toBe("?a=1&d=x+y");
    expect(queryString({})).toBe("");
  });
});
