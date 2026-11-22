import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient) -> dict:
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def test_topup_expands_amount_and_forces_recheck():
    """增补不再是空桩：扩额落库，旧结论作废，重核前出金口关闭。"""
    c = TestClient(app)
    h = _auth(c)
    cage = [x for x in c.get("/api/cages", headers=h).json()["items"] if x["available"] > 0][0]
    before_amount = cage["amount"]
    before_avail = cage["available"]
    r = c.post(
        "/api/topup",
        headers=h,
        json={"cage_id": cage["id"], "amount": 5000, "mode": "同笼扩代"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recheck_required"] is True
    assert body["gate"] == "closed"
    after = c.get(f"/api/cages/{cage['id']}", headers=h).json()["cage"]
    assert after["amount"] == before_amount + 5000
    assert after["available"] == before_avail + 5000
    assert after["status"] == "待重核"
    jobs = c.get("/api/topup/jobs", headers=h).json()["items"]
    assert any(j["status"] == "已扩额待重核" for j in jobs)


def test_split_stub_no_new_cage():
    c = TestClient(app)
    h = _auth(c)
    with connect() as conn:
        before = conn.execute("SELECT COUNT(*) c FROM cages").fetchone()["c"]
    cage = [x for x in c.get("/api/cages", headers=h).json()["items"] if x["available"] > 0][0]
    half = round(cage["available"] / 2, 2)
    other = round(cage["available"] - half, 2)
    r = c.post(
        "/api/split-stub",
        headers=h,
        json={
            "cage_id": cage["id"],
            "left_amount": half,
            "right_amount": other,
            "mode": "影子子笼",
        },
    )
    assert r.status_code == 200
    assert r.json()["cages_unchanged"] is True
    with connect() as conn:
        after = conn.execute("SELECT COUNT(*) c FROM cages").fetchone()["c"]
    assert after == before
