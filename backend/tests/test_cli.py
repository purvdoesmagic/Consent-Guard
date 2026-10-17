from app.models import AuditEvent, InvestigationCase, ProtectedRecord, User


def test_seed_demo_creates_consistent_synthetic_data(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    assert "Synthetic demo data created" in result.output
    assert {u.username for u in User.query.all()} == {"alice", "bob", "acme", "brightads", "ivy"}
    assert User.query.filter_by(username="ivy").one().mfa_enabled
    assert ProtectedRecord.query.count() == 6
    assert InvestigationCase.query.count() == 1
    assert AuditEvent.query.filter_by(reason_code="DENY_CONSENT_WITHDRAWN").count() == 3

    verify = runner.invoke(args=["verify-chain"])
    assert verify.exit_code == 0 and "VALID" in verify.output

    again = runner.invoke(args=["seed-demo"])
    assert again.exit_code != 0 and "already contains users" in again.output


def test_verify_chain_cli_reports_tampering(app):
    from sqlalchemy import text

    from app.extensions import db
    from app.services import audit

    audit.record("test.event", "info")
    audit.record("test.event", "info")
    db.session.execute(text("UPDATE audit_events SET outcome='denied' WHERE seq=1"))
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["verify-chain"])
    assert result.exit_code == 1
    assert "HASH_MISMATCH" in result.output and "INVALID" in result.output
