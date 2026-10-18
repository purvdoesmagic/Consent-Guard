import os
import sys

from audit_log import verify_chain
from models import LogEntry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import case_study  # noqa: E402


def test_cover_up_fools_the_app_but_not_the_saved_copy(app, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(case_study, "EVIDENCE", str(tmp_path))
    monkeypatch.setattr(case_study, "COPY_DB", str(tmp_path / "copy-1.db"))
    monkeypatch.setattr(case_study, "COPY_INFO", str(tmp_path / "copy-1.json"))
    monkeypatch.setattr(case_study, "db_path", lambda _app: app.config["SQLALCHEMY_DATABASE_URI"][10:])

    case_study.setup(app)
    before = LogEntry.query.count()
    case_study.save_copy(app)
    case_study.cover_up(app)

    assert verify_chain()["valid"]                  # the app is fooled
    assert LogEntry.query.count() == before - 9     # 9 blocked attempts were deleted

    case_study.check(app)
    output = capsys.readouterr().out
    assert "Entries missing compared to the copy: 9" in output
    assert "FAIL" in output
