"""End-to-end smoke test against a RUNNING ConsentGuard instance (seeded demo data).

Uses only the Python standard library and real HTTP, through either the Vite
proxy (default, http://127.0.0.1:5173) or Flask directly (http://127.0.0.1:5000).

    backend\\.venv\\Scripts\\python.exe scripts\\smoke_test.py
    backend\\.venv\\Scripts\\python.exe scripts\\smoke_test.py --base http://127.0.0.1:5000 --totp-secret <ivy secret>

It creates a few new events (logins, access attempts) but never modifies or deletes existing data.
It deliberately triggers the login rate limit once and then waits 61 seconds. Run it at most a few
times per hour (the default limit is 30 logins per hour per IP address).
"""

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

PASSWORD = "Demo-Password-2026!"
results = []


class Client:
    def __init__(self, base):
        self.base = base
        self.csrf = None
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, csrf=True):
        data = json.dumps(body or {}).encode() if method != "GET" else None
        req = urllib.request.Request(self.base + "/api" + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
            if csrf and self.csrf:
                req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req, timeout=15) as resp:
                status, raw, headers = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as err:
            status, raw, headers = err.code, err.read(), err.headers
        payload = json.loads(raw) if headers.get("Content-Type", "").startswith("application/json") else raw
        if isinstance(payload, dict) and payload.get("csrf_token"):
            self.csrf = payload["csrf_token"]
        return status, payload, headers


def check(name, condition, detail=""):
    results.append(condition)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{'' if condition else f'  -> {detail}'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    parser.add_argument("--totp-secret", help="ivy's TOTP secret printed by seed-demo (enables investigator checks)")
    args = parser.parse_args()

    anon = Client(args.base)
    status, body, headers = anon.call("GET", "/health")
    check("health endpoint", status == 200 and body.get("database") == "ok", body)
    check("security headers", "frame-ancestors 'none'" in headers.get("Content-Security-Policy", ""), dict(headers))
    check("anonymous access rejected", anon.call("GET", "/consents")[0] == 401)
    status, body, _ = anon.call("POST", "/auth/login", {"username": "alice", "password": "wrong-password-x"})
    if status == 429:
        print("       login is rate limited from an earlier run; waiting 61 s...")
        time.sleep(61)
        status, body, _ = anon.call("POST", "/auth/login", {"username": "alice", "password": "wrong-password-x"})
    check("bad password -> generic 401", status == 401 and body["error"]["code"] == "INVALID_CREDENTIALS", body)

    alice = Client(args.base)
    status, body, _ = alice.call("POST", "/auth/login", {"username": "alice", "password": PASSWORD})
    check("subject login", status == 200 and body.get("authenticated"), body)
    check("write without CSRF token rejected", alice.call("POST", "/auth/sessions/revoke-others", csrf=False)[0] == 403)
    status, body, _ = alice.call("GET", "/consents")
    check("subject lists own consents", status == 200 and body["consents"]
          and all(c["subject"]["username"] == "alice" for c in body["consents"]), body)
    status, body, _ = alice.call("GET", "/records")
    records = {r["category"]: r["id"] for r in body.get("records", [])}
    check("subject lists own records (metadata only)", status == 200 and "ciphertext" not in json.dumps(body), body)
    status, body, _ = alice.call("POST", f"/records/{records['health']}/access", {"action": "read"})
    check("owner decrypts own record", status == 200 and body["decision"] == "ALLOW_OWNER", body)
    status, body, _ = alice.call("GET", "/dashboard")
    check("dashboard from live data", status == 200 and "integrity" in body, body)

    acme = Client(args.base)
    acme.call("POST", "/auth/login", {"username": "acme", "password": PASSWORD})
    status, body, _ = acme.call("POST", f"/records/{records['health']}/access",
                                {"action": "read", "purpose": "medical_research"})
    check("processor allowed under active consent", status == 200 and body["decision"] == "ALLOW_CONSENT", body)
    status, body, _ = acme.call("POST", f"/records/{records['financial']}/access",
                                {"action": "read", "purpose": "medical_research"})
    check("processor denied for non-consented category", status == 403, body)
    check("processor cannot open cases", acme.call("GET", "/cases")[0] == 403)

    bright = Client(args.base)
    bright.call("POST", "/auth/login", {"username": "brightads", "password": PASSWORD})
    status, body, _ = bright.call("POST", f"/records/{records['contact']}/access", {"action": "read", "purpose": "marketing"})
    check("access after withdrawal denied", status == 403 and body["error"]["details"]["reason"] == "DENY_CONSENT_WITHDRAWN", body)

    bob = Client(args.base)
    bob.call("POST", "/auth/login", {"username": "bob", "password": PASSWORD})
    status, body, _ = bob.call("POST", f"/records/{records['health']}/access", {"action": "read"})
    check("cross-user record access denied", status == 403 and body["error"]["details"]["reason"] == "ACCESS_DENIED", body)

    # Five logins have now been made from this IP within a minute; the sixth must be throttled.
    ivy = Client(args.base)
    status, body, _ = ivy.call("POST", "/auth/login", {"username": "ivy", "password": PASSWORD})
    check("login rate limit enforced (6th attempt in a minute)", status == 429, body)
    print("       waiting 61 s for the rate-limit window to reset...")
    time.sleep(61)
    status, body, _ = ivy.call("POST", "/auth/login", {"username": "ivy", "password": PASSWORD})
    check("investigator login requires MFA", status == 200 and body.get("mfa_required") is True, body)
    if args.totp_secret:
        import pyotp

        status, body, _ = ivy.call("POST", "/auth/mfa/verify", {"code": pyotp.TOTP(args.totp_secret).now()})
        check("investigator TOTP verification", status == 200 and body.get("authenticated"), body)
        status, body, _ = ivy.call("POST", "/audit/verify")
        check("audit chain verifies", status == 200 and body.get("valid") is True, body)
        status, body, _ = ivy.call("GET", "/cases")
        cases = body.get("cases", [])
        check("investigator sees seeded case", status == 200 and len(cases) >= 1, body)
        if cases:
            status, body, headers = ivy.call("GET", f"/cases/{cases[0]['id']}/report.pdf")
            check("PDF report downloads", status == 200 and isinstance(body, bytes) and body.startswith(b"%PDF-"),
                  headers.get("Content-Type"))
    else:
        print("[SKIP] investigator checks (pass --totp-secret to enable)")

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
