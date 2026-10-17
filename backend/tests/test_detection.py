"""Detection-rule unit tests, including threshold and window boundaries."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.investigations.detection import Thresholds, burst_clusters, run_rules
from app.utils.time import to_iso

T0 = datetime(2026, 1, 1, 12, 0, 0)
TH = Thresholds(window_minutes=10, denial_threshold=3, probing_threshold=3, failed_login_threshold=5)


@dataclass
class Ev:
    seq: int
    minutes: float
    event_type: str = "record.access"
    outcome: str = "denied"
    reason_code: str = "DENY_NO_CONSENT"
    actor_id: int = 7
    subject_id: int | None = 1
    resource_id: str = "rec-1"
    consent_id: int | None = None
    details: dict = field(default_factory=dict)

    @property
    def timestamp(self):
        return to_iso(T0 + timedelta(minutes=self.minutes))

    @property
    def event_id(self):
        return f"evt-{self.seq}"


def rules(events, code):
    return [i for i in run_rules(events, TH) if i["rule_code"] == code]


def test_repeated_denials_threshold_boundary():
    two = [Ev(1, 0), Ev(2, 1)]
    three = two + [Ev(3, 2)]
    assert rules(two, "REPEATED_DENIALS") == []
    hits = rules(three, "REPEATED_DENIALS")
    assert len(hits) == 1 and hits[0]["event_ids"] == ["evt-1", "evt-2", "evt-3"]


def test_repeated_denials_window_is_inclusive():
    exactly = [Ev(1, 0), Ev(2, 5), Ev(3, 10)]  # spans exactly 10 minutes
    just_over = [Ev(1, 0), Ev(2, 5), Ev(3, 10 + 1 / 60_000_000 * 1000)]  # 10 min + 1 ms
    assert len(rules(exactly, "REPEATED_DENIALS")) == 1
    assert rules(just_over, "REPEATED_DENIALS") == []


def test_repeated_denials_per_actor_and_ignores_allowed():
    events = [Ev(1, 0, actor_id=1), Ev(2, 1, actor_id=2), Ev(3, 2, actor_id=3),
              Ev(4, 3, outcome="allowed"), Ev(5, 4, outcome="allowed")]
    assert rules(events, "REPEATED_DENIALS") == []


def test_separate_bursts_produce_separate_indicators():
    events = [Ev(1, 0), Ev(2, 1), Ev(3, 2), Ev(4, 60), Ev(5, 61), Ev(6, 62)]
    hits = rules(events, "REPEATED_DENIALS")
    assert [h["event_seqs"] for h in hits] == [[1, 2, 3], [4, 5, 6]]


def test_overlapping_windows_merge_and_escalate_severity():
    events = [Ev(i, i * 2) for i in range(1, 8)]  # 7 denials, 2 minutes apart
    hits = rules(events, "REPEATED_DENIALS")
    assert len(hits) == 1 and hits[0]["event_count"] == 7 and hits[0]["severity"] == "high"


def test_access_after_withdrawal_rule():
    events = [Ev(1, 0, reason_code="DENY_CONSENT_WITHDRAWN", consent_id=4)]
    hit = rules(events, "ACCESS_AFTER_WITHDRAWAL")
    assert len(hit) == 1 and hit[0]["rule_id"] == "R2" and hit[0]["consent_id"] == 4
    assert hit[0]["severity"] == "high"
    assert "not proof" in hit[0]["disclaimer"]


def test_purpose_category_and_expiry_rules():
    events = [Ev(1, 0, reason_code="DENY_PURPOSE_NOT_COVERED"),
              Ev(2, 1, reason_code="DENY_CATEGORY_NOT_COVERED", consent_id=2),
              Ev(3, 2, reason_code="DENY_CONSENT_EXPIRED", consent_id=3)]
    codes = {i["rule_code"] for i in run_rules(events, TH)}
    assert {"PURPOSE_MISMATCH", "CATEGORY_MISMATCH", "ACCESS_AFTER_EXPIRY"} <= codes


def test_broad_probing_counts_distinct_resources():
    same = [Ev(i, i, resource_id="rec-1") for i in range(1, 6)]
    assert rules(same, "BROAD_PROBING") == []
    two = [Ev(1, 0, resource_id="a"), Ev(2, 1, resource_id="b")]
    assert rules(two, "BROAD_PROBING") == []
    three = two + [Ev(3, 2, resource_id="c")]
    hit = rules(three, "BROAD_PROBING")
    assert len(hit) == 1 and hit[0]["event_count"] == 3


def test_broad_probing_ignores_consent_mismatch_denials():
    events = [Ev(i, i, resource_id=f"r{i}", reason_code="DENY_PURPOSE_NOT_COVERED") for i in range(1, 5)]
    assert rules(events, "BROAD_PROBING") == []


def test_failed_auth_burst_boundary():
    four = [Ev(i, i, event_type="auth.login.failure", outcome="failure", reason_code="INVALID_CREDENTIALS",
               actor_id=None, subject_id=9) for i in range(1, 5)]
    assert rules(four, "FAILED_AUTH_BURST") == []
    five = four + [Ev(5, 5, event_type="auth.mfa.failure", outcome="failure", actor_id=9, subject_id=9)]
    hit = rules(five, "FAILED_AUTH_BURST")
    assert len(hit) == 1 and hit[0]["target"] == "account:9"


def test_failed_auth_for_unknown_usernames_grouped_by_fingerprint():
    events = [Ev(i, i, event_type="auth.login.failure", outcome="failure", reason_code="UNKNOWN_ACCOUNT",
                 actor_id=None, subject_id=None, details={"username_fp": "abc" if i < 6 else "def"})
              for i in range(1, 8)]
    hits = rules(events, "FAILED_AUTH_BURST")
    assert len(hits) == 1 and hits[0]["target"] == "username_fp:abc"


def test_configurable_thresholds():
    events = [Ev(1, 0), Ev(2, 1)]
    assert [i for i in run_rules(events, Thresholds(denial_threshold=2)) if i["rule_code"] == "REPEATED_DENIALS"]


def test_burst_clusters_empty():
    assert burst_clusters([], timedelta(minutes=1), lambda w: True) == []


def test_indicators_reference_real_supporting_events():
    events = [Ev(1, 0, reason_code="DENY_CONSENT_WITHDRAWN", consent_id=1)]
    ind = run_rules(events, TH)[0]
    assert ind["supporting_events"][0]["event_id"] == "evt-1"
    assert ind["first_seen"] == events[0].timestamp
