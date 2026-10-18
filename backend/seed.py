"""Fill the database with fake demo data.

Run from the backend folder:  python seed.py
WARNING: this deletes the existing database and evidence copies first.
"""

import os
import shutil
from datetime import timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from audit_log import add_log
from encryption import encrypt
from models import Case, Consent, LogEntry, Record, User, db, now
from permissions import view_record

DEMO_PASSWORD = "Demo-Password-2026!"


def make_user(username, name, role):
    user = User(username=username, name=name, role=role, password_hash=generate_password_hash(DEMO_PASSWORD))
    db.session.add(user)
    db.session.commit()
    add_log("register", "success", user_id=user.id, target=username)
    return user


def make_record(owner, title, category, content):
    record = Record(owner_id=owner.id, title=title, category=category, encrypted_content=encrypt(content))
    db.session.add(record)
    db.session.commit()
    add_log("record.add", "success", user_id=owner.id, owner_id=owner.id, target=f"record {record.id}")
    return record


def give_consent(user, company, purpose, categories, expires_in=None):
    consent = Consent(user_id=user.id, company_id=company.id, purpose=purpose,
                      categories=",".join(sorted(categories)),
                      expires_at=now() + expires_in if expires_in else None)
    db.session.add(consent)
    db.session.commit()
    add_log("consent.give", "success", user_id=user.id, owner_id=user.id, target=f"consent {consent.id}",
            details=f"company={company.username}, purpose={purpose}, categories={consent.categories}")
    return consent


def withdraw(consent):
    consent.status = "withdrawn"
    consent.withdrawn_at = now()
    db.session.commit()
    add_log("consent.withdraw", "success", user_id=consent.user_id, owner_id=consent.user_id,
            target=f"consent {consent.id}",
            details=f"company={consent.company.username}, purpose={consent.purpose}")


def open_case(investigator, title, description, entries, notes=""):
    case = Case(title=title, description=description, notes=notes, investigator_id=investigator.id)
    case.logs = entries
    db.session.add(case)
    db.session.commit()
    add_log("case.create", "success", user_id=investigator.id, target=f"case {case.id}")
    return case


def seed():
    alice = make_user("alice", "Alice Example", "user")
    bob = make_user("bob", "Bob Sample", "user")
    acme = make_user("acme", "Acme Health Research", "company")
    bright = make_user("brightads", "BrightAds Marketing", "company")
    ivy = make_user("ivy", "Ivy Investigator", "investigator")

    a_health = make_record(alice, "Blood test results", "health", "Glucose 5.2, Cholesterol 4.8 (FAKE DATA)")
    a_contact = make_record(alice, "Contact details", "contact", "Phone +00 000 0000, 1 Example Street (FAKE DATA)")
    a_money = make_record(alice, "Bank summary", "financial", "Balance 1,000-5,000 (FAKE DATA)")
    b_health = make_record(bob, "Vaccination record", "health", "Fictional-Vax, 2 doses (FAKE DATA)")
    b_location = make_record(bob, "Location history", "location", "Sampletown, Fictional Park (FAKE DATA)")
    b_contact = make_record(bob, "Contact details", "contact", "bob@example.invalid (FAKE DATA)")

    give_consent(alice, acme, "research", ["health"], timedelta(days=365))
    bright_consent = give_consent(alice, bright, "marketing", ["contact"])
    give_consent(bob, acme, "analytics", ["location"], timedelta(minutes=2))  # expires during the demo

    view_record(acme, a_health, "research")       # allowed
    view_record(bright, a_contact, "marketing")   # allowed
    view_record(bright, a_health, "marketing")    # blocked: health not allowed
    view_record(bright, a_money, "analytics")     # blocked: wrong purpose
    withdraw(bright_consent)
    for _ in range(3):
        view_record(bright, a_contact, "marketing")  # blocked: after withdrawal
    for record in (b_health, b_location, b_contact):
        view_record(bright, record, "marketing")     # blocked: Bob never gave permission
    view_record(acme, b_location, "analytics")       # allowed (before it expires)

    for _ in range(5):
        add_log("login", "failed", target="admin", reason="WRONG_PASSWORD")  # someone guessing an "admin" account

    bright_entries = LogEntry.query.filter(
        (LogEntry.user_id == bright.id) & (LogEntry.action == "record.view")
    ).all()
    open_case(ivy, "BrightAds kept trying after Alice withdrew permission",
              "Check what BrightAds Marketing did with Alice's data around the time she withdrew permission.",
              bright_entries,
              notes="BrightAds was blocked 3 times after the withdrawal and also tried Bob's records without "
                    "any permission.")

    seed_case_study(ivy)


def seed_case_study(ivy):
    """The forensic case study: Carol vs QuickLoans (see docs/case-study.md)."""
    carol = make_user("carol", "Carol Customer", "user")
    dave = make_user("dave", "Dave Other", "user")
    ql = make_user("quickloans", "QuickLoans Credit Ltd", "company")

    credit = make_record(carol, "Credit file", "financial", "Credit score 712 (FAKE DATA)")
    phone = make_record(carol, "Contact details", "contact", "Phone +00 111 2222 (FAKE DATA)")
    location = make_record(carol, "Location history", "location", "Testville (FAKE DATA)")
    dave_records = [
        make_record(dave, "Credit file", "financial", "Credit score 650 (FAKE DATA)"),
        make_record(dave, "Contact details", "contact", "dave@example.invalid (FAKE DATA)"),
        make_record(dave, "Health record", "health", "Allergy: none (FAKE DATA)"),
    ]

    consent = give_consent(carol, ql, "service", ["financial", "contact"])
    view_record(ql, credit, "service")      # allowed: needed for the loan
    view_record(ql, phone, "service")       # allowed: QuickLoans now has her phone number
    view_record(ql, phone, "marketing")     # blocked: wrong purpose
    view_record(ql, location, "service")    # blocked: location was never allowed
    withdraw(consent)
    for record in (phone, credit, phone, credit):
        view_record(ql, record, "service")  # blocked: after withdrawal
    for record in dave_records:
        view_record(ql, record, "marketing")  # blocked: Dave never gave permission

    entries = LogEntry.query.filter_by(user_id=ql.id, action="record.view").all()
    open_case(ivy, "Carol's complaint against QuickLoans",
              "Carol gave QuickLoans permission to use her financial and contact data for her loan. "
              "She withdrew it after getting marketing calls, but the calls continued.",
              entries)

if __name__ == "__main__":
    app = create_app()
    db_file = os.path.join(app.instance_path, "consentguard.db")
    shutil.rmtree(os.path.join(app.instance_path, "evidence"), ignore_errors=True)  # old evidence copies
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed()
    print("Demo data created in", db_file)
    print("Password for every account:", DEMO_PASSWORD)
    print("  Users:        alice, bob, carol, dave")
    print("  Companies:    acme, brightads, quickloans")
    print("  Investigator: ivy")
    print("Note: Bob's permission for Acme expires about 2 minutes from now.")
