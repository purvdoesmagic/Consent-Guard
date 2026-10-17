"""SHA-256 hash-chained audit log.

Each event's hash is SHA-256 over a canonical JSON serialization of all its
fields *including the previous event's hash*. The first event links to a
fixed genesis value of 64 zeros.

Writing: callers ``stage()`` one or more events while making their business
changes, then call ``commit()``. ``commit()`` takes a process-wide lock, reads
the current chain head, assigns sequence numbers and hashes, and commits the
business changes and the audit events in ONE database transaction. Either
both persist or neither does. The unique constraints on ``seq`` and
``prev_hash`` make a concurrent writer that bypasses the lock (e.g. a second
process) fail instead of silently forking the chain.

What verification proves: that the stored events are internally consistent
with the hashes recorded at write time. A modified field, a deleted event, a
renumbered/reordered event or an event inserted mid-chain breaks the chain.
What it does NOT prove: that nobody with write access to the database and
knowledge of this algorithm rewrote the entire chain (or the tail) and
recomputed every hash. Checkpoints copied outside the system (e.g. the head
hash printed in a PDF report) are needed to detect that.
"""

import hashlib
import json
import threading
import uuid

from flask import g, has_request_context

from app.extensions import db
from app.models import AuditCheckpoint, AuditEvent
from app.utils.time import to_iso, utcnow

GENESIS_HASH = "0" * 64
CHAIN_VERSION = 1
_chain_lock = threading.Lock()

# Keys never allowed in event details, as a guard against accidental logging
# of secrets or protected payloads.
_FORBIDDEN_DETAIL_KEYS = {"password", "secret", "token", "code", "payload", "plaintext", "key", "csrf"}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_fields(fields):
    """Return the canonical string and its SHA-256 for an event's fields."""
    material = {
        "v": CHAIN_VERSION,
        "seq": fields["seq"],
        "event_id": fields["event_id"],
        "timestamp": fields["timestamp"],
        "event_type": fields["event_type"],
        "actor_id": fields["actor_id"],
        "subject_id": fields["subject_id"],
        "resource_type": fields["resource_type"],
        "resource_id": fields["resource_id"],
        "action": fields["action"],
        "outcome": fields["outcome"],
        "reason_code": fields["reason_code"],
        "consent_id": fields["consent_id"],
        "request_id": fields["request_id"],
        "details_json": fields["details_json"],
        "prev_hash": fields["prev_hash"],
    }
    text = canonical_json(material)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_event_hash(event):
    return hash_fields({c: getattr(event, c) for c in (
        "seq", "event_id", "timestamp", "event_type", "actor_id", "subject_id", "resource_type",
        "resource_id", "action", "outcome", "reason_code", "consent_id", "request_id",
        "details_json", "prev_hash",
    )})[1]


def _check_details(details):
    for key in details:
        if key.lower() in _FORBIDDEN_DETAIL_KEYS:
            raise ValueError(f"Refusing to log sensitive detail key '{key}'.")


def _pending():
    return db.session.info.setdefault("cg_pending_audit", [])


def stage(event_type, outcome, *, actor_id=None, subject_id=None, resource_type=None, resource_id=None,
          action=None, reason_code=None, consent_id=None, details=None):
    """Queue an audit event to be written with the next ``commit()``."""
    details = details or {}
    _check_details(details)
    _pending().append({
        "event_type": event_type,
        "outcome": outcome,
        "actor_id": actor_id,
        "subject_id": subject_id,
        "resource_type": resource_type,
        "resource_id": None if resource_id is None else str(resource_id),
        "action": action,
        "reason_code": reason_code,
        "consent_id": consent_id,
        "request_id": g.get("request_id") if has_request_context() else None,
        "details_json": canonical_json(details),
    })


def discard():
    db.session.info.pop("cg_pending_audit", None)


def commit():
    """Chain all staged events and commit them with the current transaction."""
    staged = db.session.info.pop("cg_pending_audit", [])
    created = []
    with _chain_lock:
        try:
            head = db.session.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
            seq = head.seq if head else 0
            prev_hash = head.hash if head else GENESIS_HASH
            for fields in staged:
                seq += 1
                fields = dict(fields, seq=seq, event_id=str(uuid.uuid4()),
                              timestamp=to_iso(utcnow()), prev_hash=prev_hash)
                _, digest = hash_fields(fields)
                event = AuditEvent(**fields, hash=digest)
                db.session.add(event)
                created.append(event)
                prev_hash = digest
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return created


def record(event_type, outcome, **kwargs):
    """Stage a single event and commit immediately. Returns the event."""
    stage(event_type, outcome, **kwargs)
    events = commit()
    return events[-1]


def verify_chain():
    """Walk the whole chain and report integrity findings."""
    events = db.session.query(AuditEvent).order_by(AuditEvent.seq.asc()).all()
    findings = []
    expected_prev = GENESIS_HASH
    expected_seq = 1
    last_ts = None
    for ev in events:
        if ev.seq != expected_seq:
            findings.append({
                "type": "SEQUENCE_GAP", "seq": ev.seq, "event_id": ev.event_id,
                "message": f"Sequence numbers {expected_seq}..{ev.seq - 1} are missing (events deleted?).",
            })
        if ev.prev_hash != expected_prev:
            findings.append({
                "type": "PREVIOUS_HASH_MISMATCH", "seq": ev.seq, "event_id": ev.event_id,
                "message": "Link to the preceding event is broken: an event was deleted, inserted or reordered.",
            })
        if compute_event_hash(ev) != ev.hash:
            findings.append({
                "type": "HASH_MISMATCH", "seq": ev.seq, "event_id": ev.event_id,
                "message": "Recomputed hash differs from the stored hash: event content was modified.",
            })
        if last_ts is not None and ev.timestamp < last_ts:
            findings.append({
                "type": "TIMESTAMP_ORDER", "seq": ev.seq, "event_id": ev.event_id,
                "message": "Timestamp is earlier than the preceding event (possible reordering or clock change).",
            })
        expected_prev = ev.hash
        expected_seq = ev.seq + 1
        last_ts = ev.timestamp

    head = events[-1] if events else None
    checkpoint = db.session.query(AuditCheckpoint).filter_by(valid=True).order_by(AuditCheckpoint.id.desc()).first()
    if checkpoint is not None:
        match = next((e for e in events if e.seq == checkpoint.head_seq), None)
        if match is None or match.hash != checkpoint.head_hash:
            findings.append({
                "type": "CHECKPOINT_MISMATCH", "seq": checkpoint.head_seq, "event_id": match.event_id if match else None,
                "message": (
                    f"Previously verified head (seq {checkpoint.head_seq}, recorded {checkpoint.created_at}) "
                    "is missing or changed: the chain was truncated or rewritten."
                ),
            })

    return {
        "valid": not findings,
        "event_count": len(events),
        "head_seq": head.seq if head else 0,
        "head_hash": head.hash if head else GENESIS_HASH,
        "findings": findings,
        "checked_at": to_iso(utcnow()),
        "last_checkpoint": None if checkpoint is None else {
            "head_seq": checkpoint.head_seq, "head_hash": checkpoint.head_hash, "created_at": checkpoint.created_at,
        },
    }


def verify_and_checkpoint(actor_id):
    """Explicit verification run: records a checkpoint and an audit event."""
    result = verify_chain()
    db.session.add(AuditCheckpoint(
        created_at=result["checked_at"], head_seq=result["head_seq"], head_hash=result["head_hash"],
        verified_by=actor_id, valid=result["valid"], event_count=result["event_count"],
    ))
    record(
        "audit.verified", "success" if result["valid"] else "failure", actor_id=actor_id,
        resource_type="audit_chain", action="verify",
        reason_code=None if result["valid"] else "INTEGRITY_FINDINGS",
        details={"event_count": result["event_count"], "head_seq": result["head_seq"],
                 "finding_count": len(result["findings"])},
    )
    return result
