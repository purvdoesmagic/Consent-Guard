"""Flask CLI commands. Run from backend/:

    flask --app wsgi db upgrade                 # create/upgrade the database schema
    flask --app wsgi create-investigator        # investigators cannot self-register
    flask --app wsgi seed-demo                  # synthetic demo users, records and activity
    flask --app wsgi seed-demo --reset --yes    # wipe the dev database and reseed
"""

from datetime import timedelta

import click
import pyotp
from flask import current_app
from sqlalchemy import text

from app.extensions import db, limiter
from app.models import User
from app.services.users import UserCreationError, create_user
from app.utils.time import to_iso, utcnow

DEMO_PASSWORD = "Demo-Password-2026!"


class _DemoClient:
    """Drives the real API (same code paths as the browser), keeping cookies
    and the CSRF token."""

    def __init__(self, app):
        self.http = app.test_client()
        self.csrf = None

    def call(self, method, url, body=None, expect=(200, 201)):
        headers = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        resp = getattr(self.http, method)(url, json=body if body is not None else ({} if method != "get" else None),
                                          headers=headers)
        data = resp.get_json(silent=True) or {}
        if data.get("csrf_token"):
            self.csrf = data["csrf_token"]
        if expect and resp.status_code not in expect:
            raise click.ClickException(f"{method.upper()} {url} -> {resp.status_code}: {data}")
        return data


def register_cli(app):
    @app.cli.command("create-investigator")
    @click.option("--username", prompt=True)
    @click.option("--display-name", prompt=True)
    @click.password_option()
    def create_investigator(username, display_name, password):
        """Create an investigator account (MFA enrollment required at first sign-in)."""
        try:
            user = create_user(username, password, display_name, "investigator")
        except UserCreationError as err:
            raise click.ClickException(str(err))
        click.echo(f"Created investigator '{user.username}'. Sign in and enable MFA under Account security.")

    @app.cli.command("verify-chain")
    def verify_chain_command():
        """Verify the audit hash chain (read-only; does not record a checkpoint)."""
        from app.services import audit

        result = audit.verify_chain()
        click.echo(f"Events: {result['event_count']}  head seq: {result['head_seq']}  head hash: {result['head_hash']}")
        for f in result["findings"]:
            click.echo(f"  {f['type']:<24} seq {f['seq']}: {f['message']}")
        click.echo("VALID" if result["valid"] else f"INVALID ({len(result['findings'])} finding(s))")
        if not result["valid"]:
            raise SystemExit(1)

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Drop ALL data in the configured database first.")
    @click.option("--yes", is_flag=True, help="Confirm --reset without prompting.")
    def seed_demo(reset, yes):
        """Populate the database with synthetic demonstration data."""
        uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
        if reset:
            if not uri.startswith("sqlite"):
                raise click.ClickException("--reset is only supported for the local SQLite database.")
            if not yes:
                click.confirm(f"This permanently deletes all data in {uri}. Continue?", abort=True)
            from flask_migrate import upgrade

            db.drop_all()
            db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.session.commit()
            upgrade()
            click.echo("Database reset.")
        if User.query.first() is not None:
            raise click.ClickException("Database already contains users. Use --reset --yes to start over.")
        _seed(current_app._get_current_object())


def _seed(app):
    limiter.enabled = False  # seeding performs many logins from one process
    try:
        users = {
            "alice": ("Alice Example", "subject"),
            "bob": ("Bob Sample", "subject"),
            "acme": ("Acme Health Research", "processor"),
            "brightads": ("BrightAds Marketing", "processor"),
        }
        clients = {}
        for username, (display, role) in users.items():
            c = _DemoClient(app)
            c.call("post", "/api/auth/register",
                   {"username": username, "display_name": display, "role": role, "password": DEMO_PASSWORD})
            c.call("post", "/api/auth/login", {"username": username, "password": DEMO_PASSWORD})
            clients[username] = c
        create_user("ivy", DEMO_PASSWORD, "Ivy Investigator", "investigator")
        ivy = _DemoClient(app)
        ivy.call("post", "/api/auth/login", {"username": "ivy", "password": DEMO_PASSWORD})
        secret = ivy.call("post", "/api/auth/mfa/setup")["secret"]
        ivy.call("post", "/api/auth/mfa/enable", {"code": pyotp.TOTP(secret).now()})

        ids = {u.username: u.id for u in User.query.all()}
        alice, bob, acme, bright = clients["alice"], clients["bob"], clients["acme"], clients["brightads"]

        def record(client, label, category, fields):
            return client.call("post", "/api/records",
                               {"label": label, "category": category, "fields": fields})["record"]["id"]

        a_health = record(alice, "Synthetic blood panel (2026)", "health",
                          {"Glucose": "5.2 mmol/L", "Cholesterol": "4.8 mmol/L", "Notice": "SYNTHETIC DEMO DATA"})
        a_contact = record(alice, "Synthetic contact card", "contact",
                           {"Address": "1 Example Street, Testville", "Phone": "+00 000 0000",
                            "Notice": "SYNTHETIC DEMO DATA"})
        a_fin = record(alice, "Synthetic bank summary", "financial",
                       {"Balance band": "1,000-5,000", "Account": "XX-0000 (fictional)", "Notice": "SYNTHETIC DEMO DATA"})
        b_health = record(bob, "Synthetic vaccination record", "health",
                          {"Vaccine": "Fictional-Vax", "Dose": "2 of 2", "Notice": "SYNTHETIC DEMO DATA"})
        b_loc = record(bob, "Synthetic location history", "location",
                       {"City": "Sampletown", "Last seen": "Fictional Park", "Notice": "SYNTHETIC DEMO DATA"})
        b_contact = record(bob, "Synthetic contact card", "contact",
                           {"Email": "bob@example.invalid", "Notice": "SYNTHETIC DEMO DATA"})

        def consent(client, recipient, purpose, categories, expires_in=None):
            body = {"recipient_id": ids[recipient], "purpose": purpose, "categories": categories}
            if expires_in:
                body["expires_at"] = to_iso(utcnow() + expires_in)
            return client.call("post", "/api/consents", body)["consent"]["id"]

        def access(client, record_id, purpose):
            client.call("post", f"/api/records/{record_id}/access", {"action": "read", "purpose": purpose},
                        expect=None)

        consent(alice, "acme", "medical_research", ["health", "demographic"], timedelta(days=365))
        bright_consent = consent(alice, "brightads", "marketing", ["contact"])
        consent(bob, "acme", "analytics", ["location"], timedelta(minutes=2))  # expires during the demo

        access(acme, a_health, "medical_research")          # allowed
        access(bright, a_contact, "marketing")              # allowed
        access(bright, a_health, "marketing")               # category not covered
        access(bright, a_fin, "analytics")                  # purpose not covered
        alice.call("post", f"/api/consents/{bright_consent}/withdraw")
        for _ in range(3):
            access(bright, a_contact, "marketing")          # after withdrawal (R1 + R2)
        for rec in (b_health, b_loc, b_contact):
            access(bright, rec, "marketing")                # no consent, distinct resources (R6)
        access(acme, b_loc, "analytics")                    # allowed (before expiry)

        attacker = _DemoClient(app)
        for _ in range(5):
            attacker.call("post", "/api/auth/login", {"username": "alice", "password": "Not-The-Password-1"},
                          expect=(401,))                    # R7 failed-login burst

        case = ivy.call("post", "/api/cases", {
            "title": "Suspected access after consent withdrawal (BrightAds)",
            "description": "Synthetic demo case: review BrightAds Marketing's access attempts to Alice's data "
                           "around the withdrawal of marketing consent.",
        })["case"]
        evts = ivy.call("get", f"/api/audit/events?actor_id={ids['brightads']}&event_type=record.access&page_size=200")
        consent_evts = ivy.call("get", f"/api/audit/events?consent_id={bright_consent}&event_type=consent.&page_size=50")
        ivy.call("post", f"/api/cases/{case['id']}/events", {
            "event_ids": [e["event_id"] for e in evts["events"] + consent_evts["events"]],
            "rationale": "BrightAds access attempts and the related consent lifecycle"})
        ivy.call("post", f"/api/cases/{case['id']}/notes", {
            "note_type": "finding",
            "content": "Three read attempts on Alice's contact record were denied after the marketing consent was "
                       "withdrawn. Further denied attempts touched Bob's records, for which no consent exists."})
        ivy.call("post", "/api/audit/verify")
    finally:
        limiter.enabled = current_app.config.get("RATELIMIT_ENABLED", True)

    click.echo("\nSynthetic demo data created.")
    click.echo(f"  Demo password for every account: {DEMO_PASSWORD}")
    click.echo("  Subjects:     alice, bob")
    click.echo("  Processors:   acme, brightads")
    click.echo("  Investigator: ivy (MFA enabled)")
    click.echo(f"  ivy's TOTP secret (add to an authenticator app, or run scripts/totp.py): {secret}")
    click.echo("  Bob's analytics consent for acme expires about 2 minutes from now.")
