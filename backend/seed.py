"""Fill the database with sample data: users, companies, records and about six
weeks of activity, so the website looks like it has been in use.

Run from the backend folder:  python seed.py
WARNING: this deletes the existing database and evidence copies first.

All people and data here are made up (emails use example.com, phone numbers use 555).
"""

import os
import shutil
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

import audit_log
import permissions
from app import create_app
from audit_log import add_log
from encryption import encrypt
from models import Case, Consent, LogEntry, Record, User, db, now

DEMO_PASSWORD = "Demo-Password-2026!"

# ---------- A simple clock so the sample activity is spread over past weeks ----------

clock = {"time": None}


def day(days_ago, time_of_day):
    """Move the clock to `days_ago` days before today at "HH:MM"."""
    hour, minute = map(int, time_of_day.split(":"))
    date = now() - timedelta(days=days_ago)
    clock["time"] = datetime(date.year, date.month, date.day, hour, minute)


def later(minutes=0, seconds=0):
    clock["time"] += timedelta(minutes=minutes, seconds=seconds)


def current_time():
    return clock["time"] or now()


# ---------- Helpers (also used by the tests) ----------

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
                      categories=",".join(sorted(categories)), created_at=current_time(),
                      expires_at=current_time() + expires_in if expires_in else None)
    db.session.add(consent)
    db.session.commit()
    add_log("consent.give", "success", user_id=user.id, owner_id=user.id, target=f"consent {consent.id}",
            details=f"company={company.username}, purpose={purpose}, categories={consent.categories}")
    return consent


def withdraw(consent):
    consent.status = "withdrawn"
    consent.withdrawn_at = current_time()
    db.session.commit()
    add_log("consent.withdraw", "success", user_id=consent.user_id, owner_id=consent.user_id,
            target=f"consent {consent.id}",
            details=f"company={consent.company.username}, purpose={consent.purpose}")


def view(company, record, purpose):
    return permissions.view_record(company, record, purpose)


def login(user):
    add_log("login", "success", user_id=user.id, target=user.username)


def open_case(investigator, title, description, entries, notes=""):
    case = Case(title=title, description=description, notes=notes, investigator_id=investigator.id,
                created_at=current_time())
    case.logs = entries
    db.session.add(case)
    db.session.commit()
    add_log("case.create", "success", user_id=investigator.id, target=f"case {case.id}")
    return case


# ---------- The sample data, in time order ----------

def seed():
    # While seeding, the log and the permission check use our clock instead of the real time
    audit_log.now = permissions.now = current_time
    try:
        _seed_timeline()
    finally:
        audit_log.now = permissions.now = now
        clock["time"] = None


def _seed_timeline():
    # --- 6 weeks ago: people and companies sign up ---
    day(45, "09:10")
    ivy = make_user("ivy", "Ivy Raman", "investigator")
    acme = make_user("acme", "Acme Health Research", "company")
    bright = make_user("brightads", "BrightAds Marketing", "company")
    ql = make_user("quickloans", "QuickLoans Credit Ltd", "company")
    citycare = make_user("citycare", "CityCare Hospital", "company")

    day(44, "18:30")
    alice = make_user("alice", "Alice Fernandes", "user")
    a_health = make_record(alice, "Blood test report (Sep 2026)", "health",
                           "Haemoglobin 13.2 g/dL, fasting glucose 92 mg/dL, total cholesterol 182 mg/dL. "
                           "Lab: Springfield Diagnostics")
    a_contact = make_record(alice, "Contact details", "contact",
                            "Phone +1 555-0142, alice.fernandes@example.com, 14 Maple Avenue, Springfield")
    a_money = make_record(alice, "Bank statement summary", "financial",
                          "Account ending 4821, average monthly balance 3,450, salary credited on the 1st")

    day(43, "11:05")
    bob = make_user("bob", "Bob Mathews", "user")
    b_health = make_record(bob, "Vaccination record", "health",
                           "Influenza vaccine, 2 doses (Mar and Apr 2026). Clinic: Riverside Health Centre")
    b_location = make_record(bob, "Location history", "location",
                             "Home area: Riverside. Frequent places: Central Library, Riverside Gym")
    b_contact = make_record(bob, "Contact details", "contact", "Phone +1 555-0187, bob.mathews@example.com")

    day(42, "20:40")
    priya = make_user("priya", "Priya Sharma", "user")
    p_health = make_record(priya, "Medical history", "health",
                           "Allergy: penicillin. Mild asthma. Last visit: CityCare OPD, Aug 2026")
    p_contact = make_record(priya, "Contact details", "contact", "Phone +1 555-0110, priya.sharma@example.com")

    day(41, "08:15")
    rahul = make_user("rahul", "Rahul Mehta", "user")
    r_health = make_record(rahul, "Fitness tracker summary", "health",
                           "Average 8,400 steps a day, resting heart rate 64 bpm, sleep 7h 10m")
    r_location = make_record(rahul, "Location history", "location", "Daily commute: Lakeview to Tech Park")

    day(40, "17:20")
    carol = make_user("carol", "Carol D'Souza", "user")
    c_credit = make_record(carol, "Credit report", "financial",
                           "Credit score 712, 1 active credit card, no missed payments")
    c_phone = make_record(carol, "Contact details", "contact", "Phone +1 555-0163, carol.dsouza@example.com")
    c_location = make_record(carol, "Location history", "location", "Home: Hillside. Work: Harbour Business Centre")

    day(39, "13:45")
    dave = make_user("dave", "Dave Pinto", "user")
    dave_records = [
        make_record(dave, "Credit report", "financial", "Credit score 650, car loan (active)"),
        make_record(dave, "Contact details", "contact", "Phone +1 555-0129, dave.pinto@example.com"),
        make_record(dave, "Health record", "health", "Blood group O+, no known allergies"),
    ]

    # --- Users give permissions ---
    day(38, "10:00")
    give_consent(alice, acme, "research", ["health"], timedelta(days=365))
    later(minutes=30)
    give_consent(bob, acme, "analytics", ["location"], timedelta(days=33))  # ends 5 days ago
    later(minutes=45)
    give_consent(bob, bright, "marketing", ["contact"], timedelta(days=180))
    day(37, "19:10")
    give_consent(priya, citycare, "service", ["health", "contact"])
    later(minutes=3)
    give_consent(priya, bright, "marketing", ["contact"], timedelta(days=90))
    day(36, "09:30")
    give_consent(rahul, acme, "research", ["health"], timedelta(days=365))
    later(minutes=2)
    give_consent(rahul, bright, "analytics", ["location"], timedelta(days=60))
    day(35, "16:00")
    carol_consent = give_consent(carol, ql, "service", ["financial", "contact"])  # her loan application

    # --- Normal, allowed use of data ---
    day(34, "11:00")
    view(ql, c_credit, "service")       # QuickLoans checks Carol's credit for the loan
    later(minutes=4)
    view(ql, c_phone, "service")        # and reads her phone number (so it now has it)
    day(32, "12:20")
    alice_bright = give_consent(alice, bright, "marketing", ["contact"])
    day(30, "10:15")
    view(acme, a_health, "research")
    later(minutes=20)
    view(acme, r_health, "research")
    day(28, "14:00")
    view(citycare, p_health, "service")
    later(minutes=1)
    view(citycare, p_contact, "service")
    day(25, "09:40")
    view(bright, a_contact, "marketing")
    later(minutes=2)
    view(bright, b_contact, "marketing")
    later(minutes=2)
    view(bright, p_contact, "marketing")
    later(minutes=5)
    view(bright, r_location, "analytics")
    day(20, "15:30")
    view(acme, b_location, "analytics")
    later(minutes=10)
    view(acme, a_health, "research")

    # --- QuickLoans starts over-reaching on Carol's data ---
    day(18, "10:05")
    view(ql, c_phone, "marketing")      # blocked: wrong purpose
    later(minutes=40)
    view(ql, c_location, "service")     # blocked: location was never allowed

    # --- BrightAds asks for more than it was allowed ---
    day(14, "16:10")
    view(bright, a_health, "marketing")   # blocked: Alice only allowed contact
    later(minutes=15)
    view(bright, a_money, "analytics")    # blocked: wrong purpose
    later(minutes=20)
    view(bright, b_health, "marketing")   # blocked: Bob only allowed contact
    later(minutes=1)
    view(bright, b_location, "marketing")  # blocked

    # --- Carol and Alice withdraw permission ---
    day(10, "21:15")
    withdraw(carol_consent)
    day(8, "08:50")
    withdraw(alice_bright)

    # --- Both companies keep trying after the withdrawal ---
    day(7, "11:00")
    for _ in range(3):
        view(bright, a_contact, "marketing")  # blocked 3 times within minutes
        later(minutes=2)
    day(7, "15:20")
    view(ql, c_phone, "service")              # blocked: permission withdrawn

    # --- Someone guesses passwords for an "admin" account ---
    day(6, "02:13")
    for _ in range(5):
        add_log("login", "failed", target="admin", reason="WRONG_PASSWORD")
        later(seconds=20)

    day(6, "10:45")
    view(ql, c_credit, "service")
    day(5, "17:30")
    view(ql, c_phone, "service")
    day(4, "09:05")
    view(ql, c_credit, "service")

    # --- Acme tries Bob's data after his permission ended ---
    day(3, "13:00")
    view(acme, b_location, "analytics")       # blocked: permission expired

    # --- QuickLoans tries Dave, who never gave it permission ---
    day(3, "18:40")
    for record in dave_records:
        view(ql, record, "marketing")
        later(minutes=1)

    # --- The investigator opens cases ---
    day(2, "10:00")
    login(ivy)
    bright_entries = LogEntry.query.filter_by(user_id=bright.id, action="record.view", result="denied").all()
    open_case(ivy, "BrightAds kept trying after Alice withdrew permission",
              "Alice reported marketing emails from BrightAds after she withdrew her permission.",
              bright_entries,
              notes="BrightAds asked for health and financial data it was never allowed to see, and tried "
                    "Alice's contact details 3 times after she withdrew permission. All attempts were blocked.")
    day(1, "11:30")
    login(ivy)
    ql_entries = LogEntry.query.filter_by(user_id=ql.id, action="record.view").all()
    open_case(ivy, "Carol's complaint against QuickLoans",
              "Carol gave QuickLoans permission to use her financial and contact data for her loan. "
              "She withdrew it after getting marketing calls, but the calls continued.",
              ql_entries)


if __name__ == "__main__":
    app = create_app()
    db_file = os.path.join(app.instance_path, "consentguard.db")
    shutil.rmtree(os.path.join(app.instance_path, "evidence"), ignore_errors=True)  # old evidence copies
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed()
        entries = LogEntry.query.count()
    print("Sample data created in", db_file, f"({entries} log entries over 6 weeks)")
    print("Password for every account:", DEMO_PASSWORD)
    print("  Users:        alice, bob, priya, rahul, carol, dave")
    print("  Companies:    acme, brightads, citycare, quickloans")
    print("  Investigator: ivy")
