"""The forensic case study: an insider hides QuickLoans' blocked attempts."""

import pytest

from audit_log import verify_chain
from conftest import login
from models import LogEntry
from seed import seed


@pytest.fixture
def investigator(app, client, tmp_path):
    app.instance_path = str(tmp_path / "instance")  # keep evidence copies inside the test folder
    seed()
    login(client, "ivy")
    return client


def test_cover_up_fools_the_app_but_not_the_evidence_copy(investigator):
    client = investigator
    copy = client.post("/api/evidence", json={"note": "Before the report"}).get_json()["copy"]
    assert client.post(f"/api/evidence/{copy['id']}/compare").get_json()["tampered"] is False

    removed = client.post("/api/demo/cover-up", json={"company": "quickloans"}).get_json()["removed"]
    assert removed == 9
    assert verify_chain()["valid"]  # the app's own check is fooled

    result = client.post(f"/api/evidence/{copy['id']}/compare").get_json()
    assert result["tampered"] is True
    assert result["copy_unchanged"] is True
    assert result["last_hash_found"] is False
    assert len(result["missing"]) == 9
    assert all(m["who"] == "QuickLoans Credit Ltd" and m["what"] == "Tried to view data" for m in result["missing"])


def test_restore_undoes_the_cover_up(investigator):
    client = investigator
    copy = client.post("/api/evidence").get_json()["copy"]
    client.post("/api/demo/cover-up")
    client.post(f"/api/evidence/{copy['id']}/restore")

    assert verify_chain()["valid"]
    assert LogEntry.query.filter_by(result="denied").count() > 9
    login(client, "ivy")  # restoring the database starts a fresh session
    assert client.post(f"/api/evidence/{copy['id']}/compare").get_json()["missing"] == []


def test_only_investigators_can_use_forensics(client, users):
    login(client, "alice")
    assert client.post("/api/evidence").status_code == 403
    assert client.post("/api/demo/cover-up").status_code == 403


def test_home_page_numbers(client, users):
    login(client, "alice")
    cards = dict(client.get("/api/summary").get_json()["cards"])
    assert cards["My data records"] == 0
