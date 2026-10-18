"""Turns log entries into plain English for the website and the PDF report.

Example:  action "record.view", result "denied", target "record 3", reason "CONSENT_WITHDRAWN"
becomes:  "Tried to view data" on "Blood test report (Alice Fernandes)": "Permission was withdrawn"
"""

from models import Case, Consent, Record, User

# (action, result) or just action  ->  what happened
ACTIONS = {
    ("login", "success"): "Logged in",
    ("login", "failed"): "Login failed",
    ("record.view", "allowed"): "Viewed data",
    ("record.view", "denied"): "Tried to view data",
    "register": "Created an account",
    "logout": "Logged out",
    "two_step.enable": "Turned on two-step login",
    "record.add": "Added data",
    "consent.give": "Gave permission",
    "consent.withdraw": "Withdrew permission",
    "log.verify": "Checked the log",
    "access": "Tried to open a page not allowed for their role",
    "case.create": "Opened a case",
    "case.link_logs": "Added evidence to a case",
    "case.notes": "Updated case notes",
    "case.report": "Downloaded a case report",
    "evidence.save": "Saved an evidence copy",
    "evidence.compare": "Compared the log with an evidence copy",
    "evidence.restore": "Restored an evidence copy",
}

REASONS = {
    "ALLOWED": "Allowed by permission",
    "OWNER": "Own data",
    "NO_CONSENT": "No permission given",
    "WRONG_PURPOSE": "Wrong purpose",
    "CATEGORY_NOT_ALLOWED": "Data type not allowed",
    "CONSENT_WITHDRAWN": "Permission was withdrawn",
    "CONSENT_EXPIRED": "Permission has expired",
    "NOT_A_COMPANY": "Only companies can request data",
    "WRONG_PASSWORD": "Wrong password",
    "WRONG_CODE": "Wrong 6-digit code",
    "WRONG_ROLE": "Not allowed for this role",
}

RESULTS = {"allowed": "Allowed", "denied": "Blocked", "success": "Done", "failed": "Failed"}

ACCOUNT_ACTIONS = {"register", "login", "logout", "two_step.enable"}


def reason_text(code):
    return REASONS.get(code, code or "")


class Describer:
    """Loads users, records, permissions and cases once, then describes many log entries."""

    def __init__(self):
        self.users = {u.id: u for u in User.query.all()}
        self.records = {r.id: r for r in Record.query.all()}
        self.consents = {c.id: c for c in Consent.query.all()}
        self.cases = {c.id: c for c in Case.query.all()}

    def name(self, user_id):
        user = self.users.get(user_id)
        return user.name if user else "-"

    def what(self, entry):
        return ACTIONS.get((entry.action, entry.result)) or ACTIONS.get(entry.action) or entry.action

    def on(self, entry):
        target = entry.target or ""
        if entry.action in ACCOUNT_ACTIONS:
            return f"Account: {target}"
        if entry.action == "access":
            return "Restricted page"
        kind, _, number = target.partition(" ")
        if not number.isdigit():
            return target
        number = int(number)
        if kind == "record" and number in self.records:
            record = self.records[number]
            return f"{record.title} ({self.name(record.owner_id)})"
        if kind == "consent" and number in self.consents:
            consent = self.consents[number]
            return f"Permission for {consent.company.name} ({consent.purpose})"
        if kind == "case" and number in self.cases:
            return f"Case #{number}: {self.cases[number].title}"
        return target.capitalize()

    def describe(self, entry):
        return {
            "who": self.name(entry.user_id),
            "what": self.what(entry),
            "on": self.on(entry),
            "result_text": RESULTS.get(entry.result, entry.result),
            "reason_text": reason_text(entry.reason),
        }

    def row(self, entry):
        """A log entry as a dictionary for the website, with the plain-English fields added."""
        return dict(entry.to_dict(), **self.describe(entry))
