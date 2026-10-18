from conftest import login
from detection import find_alerts
from models import LogEntry, User
from seed import make_user, seed


def test_demo_data_triggers_all_four_rules(app):
    seed()
    names = {u.id: u.name for u in User.query.all()}
    alerts = find_alerts(LogEntry.query.order_by(LogEntry.id).all(), names)
    assert {a["rule"] for a in alerts} == {"R1", "R2", "R3", "R4"}
    after_withdrawal = {a["explanation"].split()[0]: len(a["log_ids"]) for a in alerts if a["rule"] == "R2"}
    assert after_withdrawal == {"BrightAds": 3, "QuickLoans": 4}


def test_only_investigators_see_alerts_and_cases(client, users):
    login(client, "alice")
    assert client.get("/api/alerts").status_code == 403
    assert client.get("/api/cases").status_code == 403


def test_case_and_pdf_report(client, users):
    login(client, "ivy")
    case_id = client.post("/api/cases", json={"title": "Test case"}).get_json()["case"]["id"]
    assert client.post(f"/api/cases/{case_id}/logs", json={"log_ids": [1, 2]}).get_json()["case"]["log_count"] == 2
    client.put(f"/api/cases/{case_id}/notes", json={"notes": "Looks fine."})

    res = client.get(f"/api/cases/{case_id}/report")
    assert res.status_code == 200
    assert res.data.startswith(b"%PDF")


def test_investigator_cannot_open_another_investigators_case(client, users):
    login(client, "ivy")
    case_id = client.post("/api/cases", json={"title": "Private case"}).get_json()["case"]["id"]
    client.post("/api/logout")
    make_user("ian", "Ian", "investigator")
    login(client, "ian")
    assert client.get(f"/api/cases/{case_id}").status_code == 404
