import { vi } from "vitest";

// Route-based fetch mock: routes = { "POST /api/auth/login": (body) => [status, json] }
export function mockFetch(routes) {
  const calls = [];
  const fn = vi.fn(async (url, init = {}) => {
    const method = init.method || "GET";
    const path = url.split("?")[0];
    calls.push({ method, url, headers: init.headers || {}, body: init.body ? JSON.parse(init.body) : undefined });
    const handler = routes[`${method} ${path}`];
    if (!handler) return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "no mock" } }), { status: 404 });
    const [status, json] = handler(init.body ? JSON.parse(init.body) : undefined, url);
    return new Response(JSON.stringify(json), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}
