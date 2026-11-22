"""增补重核事故夹具。

本文件先以「增补后旧核验结论仍可解笼」的假绿事故为红测：
- 第一条：增补登记成功后，旧结论仍能直出金。
- 第二条：增补后的笼被两人同时出金时，持锁人仍能用旧结论直出金。
两条红测必须先见红，才允许改增补 / 核验 / 解笼 / 罚没服务。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient, user: str = "admin") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _open_and_freeze(
    c: TestClient,
    h: dict,
    *,
    key: str = "P-INC",
    code: str = "CG-INC-001",
    amount: float = 40000,
    deposit: float = 100000,
) -> dict:
    r = c.post(
        "/api/bonds",
        headers=h,
        json={
            "party_key": key,
            "party_name": "事故夹具",
            "initial_deposit": deposit,
        },
    )
    assert r.status_code == 200, r.text
    r = c.post(
        "/api/cages/freeze",
        headers=h,
        json={
            "party_key": key,
            "contract_no": f"HT-{code}",
            "amount": amount,
            "beneficiary": "事故受益人",
            "cage_code": code,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _attest_pass(c: TestClient, h: dict, cage_id: int) -> dict:
    r = c.post(
        "/api/attestations",
        headers=h,
        json={
            "cage_id": cage_id,
            "outcome": "通过",
            "evidence": "事故前旧结论",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_incident_old_conclusion_must_not_release_after_topup():
    """假绿事故：增补已经登记，旧结论仍可直接解笼。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _open_and_freeze(c, h)
    _attest_pass(c, h, cage["id"])

    # 当前可用的增补入口（空桩）。修复前它返回 200，假绿由此发生。
    top = c.post(
        "/api/topup-stub",
        headers=h,
        json={
            "cage_id": cage["id"],
            "amount": 10000,
            "mode": "同笼扩代",
        },
    )
    assert top.status_code == 200, top.text

    rel = c.post("/api/releases", headers=h, json={"cage_id": cage["id"]})
    assert rel.status_code == 409, (
        "事故复现：增补后旧结论仍可直出金 "
        f"status={rel.status_code} body={rel.text}"
    )
    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
    assert n == 0, "增补后旧结论直出金已落库，出金口未关"


def test_incident_two_actor_release_after_topup_must_not_pay_old_conclusion():
    """假绿事故：两人同抢增补后的笼，持锁人用旧结论直出金。"""
    c = TestClient(app)
    h_admin = _auth(c, "admin")
    h_clerk = _auth(c, "clerk")
    cage = _open_and_freeze(c, h_admin, key="P-RACE", code="CG-RACE-001")
    _attest_pass(c, h_admin, cage["id"])

    top = c.post(
        "/api/topup-stub",
        headers=h_admin,
        json={
            "cage_id": cage["id"],
            "amount": 10000,
            "mode": "同笼扩代",
        },
    )
    assert top.status_code == 200, top.text

    lock_key = f"cage:{cage['id']}"
    assert (
        c.post(
            "/api/locks/acquire",
            headers=h_admin,
            json={"lock_key": lock_key},
        ).status_code
        == 200
    )

    # 后到的柜员只能留争用痕，不能写业务。
    r_clerk = c.post(
        "/api/releases", headers=h_clerk, json={"cage_id": cage["id"]}
    )
    assert r_clerk.status_code == 409, r_clerk.text

    # 持锁人也不能用增补前的旧结论直出金。
    r_admin = c.post(
        "/api/releases", headers=h_admin, json={"cage_id": cage["id"]}
    )
    assert r_admin.status_code == 409, (
        "事故复现：持锁人用增补前旧结论直出金 "
        f"status={r_admin.status_code} body={r_admin.text}"
    )

    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
        contended = conn.execute(
            "SELECT COUNT(*) c FROM contention_log WHERE lock_key=?",
            (lock_key,),
        ).fetchone()["c"]
    assert n == 0, "争用后仍落了拨付"
    assert contended >= 1, "后到者未留下争用痕"


def test_topup_recheck_then_release_after_new_conclusion():
    """甲路径闭环：扩额 → 待重核（出金关）→ 新结论 → 出金放行。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _open_and_freeze(c, h, key="P-OK", code="CG-OK-001", amount=30000)
    _attest_pass(c, h, cage["id"])
    top = c.post(
        "/api/topup",
        headers=h,
        json={"cage_id": cage["id"], "amount": 20000, "mode": "同笼扩代"},
    )
    assert top.status_code == 200, top.text
    board = c.get(f"/api/recheck/{cage['id']}", headers=h).json()
    assert board["recheck_pending"] is True
    assert board["gate"] == "closed"
    assert board["voided_attestation_ids"], "旧结论未留作废痕"
    # 重核前罚没同样关闭
    assert (
        c.post("/api/forfeits", headers=h, json={"cage_id": cage["id"]}).status_code
        == 409
    )
    new_att = c.post(
        "/api/attestations",
        headers=h,
        json={"cage_id": cage["id"], "outcome": "通过", "evidence": "新额复检"},
    )
    assert new_att.status_code == 200, new_att.text
    board = c.get(f"/api/recheck/{cage['id']}", headers=h).json()
    assert board["recheck_pending"] is False
    assert board["gate"] == "open"
    rel = c.post("/api/releases", headers=h, json={"cage_id": cage["id"]})
    assert rel.status_code == 200, rel.text
    assert rel.json()["amount"] == 50000
    recon = c.get(f"/api/reconcile/{cage['cage_code']}", headers=h).json()
    assert recon["balanced"] is True


def test_topup_b_path_and_other_modes_are_refused_and_logged():
    """乙路径/新笼桥接一律记重核偏航并拒写，笼额不动。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _open_and_freeze(c, h, key="P-DEV", code="CG-DEV-001")
    for payload in (
        {"cage_id": cage["id"], "amount": 1000, "mode": "同笼扩代", "path": "乙"},
        {"cage_id": cage["id"], "amount": 1000, "mode": "新笼桥接"},
    ):
        r = c.post("/api/topup", headers=h, json=payload)
        assert r.status_code == 409, r.text
    after = c.get(f"/api/cages/{cage['id']}", headers=h).json()["cage"]
    assert after["amount"] == 40000 and after["status"] == "已冻结"
    devs = c.get("/api/recheck/board", headers=h).json()["deviations"]
    assert len(devs) >= 2


def test_manifest_lock_blocks_writes_and_board_is_same_source(monkeypatch, tmp_path):
    """纪要未锁死时必须拒写；五页同源看板返回同一口径。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _open_and_freeze(c, h, key="P-LOCK", code="CG-LOCK-001")
    import recheck_policy

    monkeypatch.setattr(
        recheck_policy, "lock_state", lambda: {"locked": False, "reason": "测试篡改"}
    )
    r = c.post(
        "/api/topup",
        headers=h,
        json={"cage_id": cage["id"], "amount": 1000, "mode": "同笼扩代"},
    )
    assert r.status_code == 409
    board = c.get("/api/recheck/board", headers=h).json()
    for key in ("pending", "cages", "topup_jobs", "deviations", "manifest"):
        assert key in board
    assert board["gate_policy"]["rule"] == "扩额后必须重核才能出金"
    assert "增补页" in board["sources"]


def test_failed_topup_rolls_back_expand_and_void(monkeypatch):
    """甲路径事务性：增补中途失败时扩额与作废同滚，旧结论仍有效。"""
    c = TestClient(app, raise_server_exceptions=False)
    h = _auth(c)
    cage = _open_and_freeze(c, h, key="P-ROLL", code="CG-ROLL-001", amount=20000)
    old = _attest_pass(c, h, cage["id"])
    before = c.get(f"/api/cages/{cage['id']}", headers=h).json()["cage"]

    import topup_svc

    real_write_audit = topup_svc.write_audit

    def boom(conn, actor, action, target, payload):
        # 审计写入阶段炸掉，模拟事务中途失败
        raise RuntimeError("审计写入故障（夹具注入）")

    monkeypatch.setattr(topup_svc, "write_audit", boom)
    r = c.post(
        "/api/topup",
        headers=h,
        json={"cage_id": cage["id"], "amount": 5000, "mode": "同笼扩代"},
    )
    monkeypatch.setattr(topup_svc, "write_audit", real_write_audit)
    assert r.status_code == 500, r.text

    after = c.get(f"/api/cages/{cage['id']}", headers=h).json()["cage"]
    assert after["amount"] == before["amount"], "失败后笼额未回滚"
    assert after["available"] == before["available"], "失败后可用额未回滚"
    assert after["status"] == before["status"] == "核验通过", "失败后笼状态未回滚"
    detail = c.get(f"/api/cages/{cage['id']}", headers=h).json()
    assert not [a for a in detail["attestations"] if a["voided_at"]], "失败后旧结论被作废"
    assert detail["attestations"][0]["id"] == old["id"]
    # 旧结论仍可用：解笼应成功
    assert c.post("/api/releases", headers=h, json={"cage_id": cage["id"]}).status_code == 200


def test_two_actor_release_race_after_recheck_leaves_contention():
    """重核通过后两人同抢出金：后到只留争用痕，不落第二笔拨付。"""
    c = TestClient(app)
    h_admin = _auth(c, "admin")
    h_clerk = _auth(c, "clerk")
    cage = _open_and_freeze(c, h_admin, key="P-R2", code="CG-R2-001", amount=30000)
    _attest_pass(c, h_admin, cage["id"])
    assert (
        c.post(
            "/api/topup",
            headers=h_admin,
            json={"cage_id": cage["id"], "amount": 10000, "mode": "同笼扩代"},
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/attestations",
            headers=h_admin,
            json={"cage_id": cage["id"], "outcome": "通过", "evidence": "重核"},
        ).status_code
        == 200
    )
    lock_key = f"cage:{cage['id']}"
    assert (
        c.post(
            "/api/locks/acquire", headers=h_admin, json={"lock_key": lock_key}
        ).status_code
        == 200
    )
    r_clerk = c.post("/api/releases", headers=h_clerk, json={"cage_id": cage["id"]})
    assert r_clerk.status_code == 409, r_clerk.text
    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
        contended = conn.execute(
            "SELECT COUNT(*) c FROM contention_log WHERE lock_key=?", (lock_key,)
        ).fetchone()["c"]
    assert n == 0, "后到者仍落了拨付"
    assert contended >= 1, "后到者未留争用痕"


def test_board_is_single_source_for_five_pages():
    """五页同源：看板的笼/核验/偏航与各页接口读同一库。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _open_and_freeze(c, h, key="P-SRC", code="CG-SRC-001", amount=25000)
    _attest_pass(c, h, cage["id"])
    c.post(
        "/api/topup",
        headers=h,
        json={"cage_id": cage["id"], "amount": 5000, "mode": "同笼扩代"},
    )
    board = c.get("/api/recheck/board", headers=h).json()
    by_id = {i["cage_id"]: i for i in board["cages"]}
    row = by_id[cage["id"]]
    assert row["status"] == "待重核" and row["gate"] == "closed"
    cages = {i["id"]: i for i in c.get("/api/cages", headers=h).json()["items"]}
    assert cages[cage["id"]]["amount"] == row["amount"] == 30000
    atts = c.get("/api/attestations", headers=h).json()["items"]
    voided = [a["id"] for a in atts if a["cage_id"] == cage["id"] and a["voided_at"]]
    assert sorted(voided) == sorted(row["voided_attestation_ids"])
    # 五页同源清单与闸门策略
    assert set(board["sources"]) == {"增补页", "核验页", "解笼页", "罚没页", "审计页"}
    assert board["gate_policy"]["rule"] == "扩额后必须重核才能出金"
