"""Transparent, rule-based detection of potentially suspicious activity.

Every rule is a plain function over audit events. Each indicator lists the
exact event IDs and timestamps that triggered it and a human-readable
explanation. Indicators are *leads for an investigator*, not proof of
malicious intent: legitimate causes (a stale bookmark, a misconfigured
integration, a forgotten password) can trigger every rule.

Rules
-----
R1 REPEATED_DENIALS      >= N denied record-access attempts by one actor
                         within W minutes (inclusive).
R2 ACCESS_AFTER_WITHDRAWAL  access attempt denied because the applicable
                         consent had been withdrawn.
R3 ACCESS_AFTER_EXPIRY   access attempt denied because consent had expired.
R4 PURPOSE_MISMATCH      access requested for a purpose not consented to.
R5 CATEGORY_MISMATCH     access requested to a data category not covered.
R6 BROAD_PROBING         one actor denied on >= M *distinct* resources within
                         W minutes with no consent/ownership (possible
                         enumeration).
R7 FAILED_AUTH_BURST     >= K failed login/MFA attempts against one account
                         (or one unknown username) within W minutes.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from app.utils.time import parse_iso

DISCLAIMER = ("System-generated indicator based on a documented rule. It is not proof of malicious "
              "activity and must be assessed by an investigator.")

PROBING_REASONS = {"DENY_NO_CONSENT", "DENY_ROLE_NOT_PERMITTED", "DENY_RESOURCE_NOT_FOUND",
                   "NOT_RESOURCE_OWNER", "RESOURCE_NOT_FOUND"}
SINGLE_EVENT_RULES = {
    "DENY_CONSENT_WITHDRAWN": ("R2", "ACCESS_AFTER_WITHDRAWAL", "Access attempted after consent withdrawal", "high",
                               "The requester attempted to access data after the subject withdrew the consent "
                               "that previously covered it."),
    "DENY_CONSENT_EXPIRED": ("R3", "ACCESS_AFTER_EXPIRY", "Access attempted after consent expiry", "medium",
                             "The requester attempted to access data after the applicable consent expired."),
    "DENY_PURPOSE_NOT_COVERED": ("R4", "PURPOSE_MISMATCH", "Access requested outside consented purpose", "medium",
                                 "The requester asked to use data for a purpose the subject has not consented to."),
    "DENY_CATEGORY_NOT_COVERED": ("R5", "CATEGORY_MISMATCH", "Access requested to non-consented data category",
                                  "medium", "The requester asked for a data category not covered by any active "
                                  "consent for that purpose."),
}


@dataclass(frozen=True)
class Thresholds:
    window_minutes: int = 10
    denial_threshold: int = 3
    probing_threshold: int = 3
    failed_login_threshold: int = 5

    @classmethod
    def from_config(cls, cfg, **overrides):
        values = dict(
            window_minutes=cfg["DETECTION_WINDOW_MINUTES"],
            denial_threshold=cfg["DETECTION_DENIAL_THRESHOLD"],
            probing_threshold=cfg["DETECTION_PROBING_THRESHOLD"],
            failed_login_threshold=cfg["DETECTION_FAILED_LOGIN_THRESHOLD"],
        )
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    def as_dict(self):
        return dict(self.__dict__)


def _indicator(rule_id, code, title, severity, explanation, events, actor_id=None, extra=None):
    events = sorted(events, key=lambda e: (e.timestamp, e.seq))
    data = {
        "rule_id": rule_id,
        "rule_code": code,
        "title": title,
        "severity": severity,
        "classification": "system_generated_indicator",
        "explanation": explanation,
        "disclaimer": DISCLAIMER,
        "actor_id": actor_id,
        "event_count": len(events),
        "event_ids": [e.event_id for e in events],
        "event_seqs": [e.seq for e in events],
        "first_seen": events[0].timestamp,
        "last_seen": events[-1].timestamp,
        "supporting_events": [{"event_id": e.event_id, "seq": e.seq, "timestamp": e.timestamp,
                               "event_type": e.event_type, "reason_code": e.reason_code,
                               "resource_id": e.resource_id} for e in events],
    }
    if extra:
        data.update(extra)
    return data


def burst_clusters(events, window, qualifies):
    """Maximal clusters of time-ordered events in which some sliding window
    of length <= ``window`` satisfies ``qualifies(window_events)``.
    Overlapping qualifying windows are merged into one cluster."""
    events = sorted(events, key=lambda e: (e.timestamp, e.seq))
    times = [parse_iso(e.timestamp) for e in events]
    clusters, current, start = [], None, 0
    for end in range(len(events)):
        while times[end] - times[start] > window:
            start += 1
        if qualifies(events[start:end + 1]):
            idx = set(range(start, end + 1))
            if current is not None and start <= max(current):
                current |= idx
            else:
                if current is not None:
                    clusters.append(current)
                current = idx
    if current is not None:
        clusters.append(current)
    return [[events[i] for i in sorted(c)] for c in clusters]


def run_rules(events, thresholds):
    window = timedelta(minutes=thresholds.window_minutes)
    indicators = []

    denied_access = [e for e in events if e.event_type == "record.access" and e.outcome == "denied"]
    by_actor = defaultdict(list)
    for e in denied_access:
        by_actor[e.actor_id].append(e)

    # R1 repeated denials
    for actor_id, items in by_actor.items():
        for cluster in burst_clusters(items, window, lambda w: len(w) >= thresholds.denial_threshold):
            severity = "high" if len(cluster) >= 2 * thresholds.denial_threshold else "medium"
            indicators.append(_indicator(
                "R1", "REPEATED_DENIALS", "Repeated denied access attempts", severity,
                f"Actor {actor_id} had {len(cluster)} denied access attempts with at least "
                f"{thresholds.denial_threshold} inside a {thresholds.window_minutes}-minute window.",
                cluster, actor_id))

    # R2-R5 single-event rules, grouped per (rule, actor, consent)
    groups = defaultdict(list)
    for e in denied_access:
        if e.reason_code in SINGLE_EVENT_RULES:
            groups[(e.reason_code, e.actor_id, e.consent_id)].append(e)
    for (reason, actor_id, consent_id), items in groups.items():
        rule_id, code, title, severity, explanation = SINGLE_EVENT_RULES[reason]
        suffix = f" Consent #{consent_id}." if consent_id else ""
        indicators.append(_indicator(
            rule_id, code, title, severity,
            f"{explanation} Actor {actor_id}, {len(items)} attempt(s).{suffix}",
            items, actor_id, {"consent_id": consent_id}))

    # R6 broad probing across distinct resources
    probing = defaultdict(list)
    for e in events:
        if e.outcome == "denied" and e.reason_code in PROBING_REASONS and e.event_type in {"record.access", "authz.denied"}:
            probing[e.actor_id].append(e)
    for actor_id, items in probing.items():
        def distinct_enough(w):
            return len({x.resource_id for x in w}) >= thresholds.probing_threshold
        for cluster in burst_clusters(items, window, distinct_enough):
            distinct = len({x.resource_id for x in cluster})
            indicators.append(_indicator(
                "R6", "BROAD_PROBING", "Denied access across many unrelated resources", "high",
                f"Actor {actor_id} was denied access to {distinct} distinct resources without ownership or "
                f"consent within a {thresholds.window_minutes}-minute window (threshold "
                f"{thresholds.probing_threshold}). This pattern can indicate enumeration.",
                cluster, actor_id))

    # R7 failed authentication bursts per target account / username fingerprint
    auth_fail = defaultdict(list)
    for e in events:
        if e.event_type in {"auth.login.failure", "auth.mfa.failure"}:
            key = f"account:{e.subject_id}" if e.subject_id else f"username_fp:{e.details.get('username_fp', '?')}"
            auth_fail[key].append(e)
    for key, items in auth_fail.items():
        for cluster in burst_clusters(items, window, lambda w: len(w) >= thresholds.failed_login_threshold):
            indicators.append(_indicator(
                "R7", "FAILED_AUTH_BURST", "Burst of failed authentication attempts", "medium",
                f"{len(cluster)} failed login/MFA attempts against {key} within a "
                f"{thresholds.window_minutes}-minute window (threshold {thresholds.failed_login_threshold}).",
                cluster, None, {"target": key}))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    indicators.sort(key=lambda i: (severity_rank[i["severity"]], i["first_seen"], i["rule_id"]))
    return indicators
