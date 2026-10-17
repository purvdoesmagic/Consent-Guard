"""UTC time helpers.

All timestamps are stored as naive UTC datetimes in SQLite and serialized as
ISO-8601 strings with microsecond precision and a trailing ``Z``. Tests patch
``utcnow`` to simulate the passage of time (e.g. consent expiry).
"""

from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(value):
    """Parse an ISO-8601 timestamp into a naive UTC datetime. Raises ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
