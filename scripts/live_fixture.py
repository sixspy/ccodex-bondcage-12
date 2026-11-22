"""本机文件库（data/app.db）事故夹具实跑。

用法：
  python3 -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 11322
  python3 -I scripts/live_fixture.py [--base http://127.0.0.1:11322]

覆盖：
  1) 增补后旧结论直出金必须被拒（事故 1）。
  2) 双人同抢增补后笼出金：后到只留争用痕，持锁人也不能用旧结论出金（事故 2）。
  3) 甲路径重核后出金放行，且对账平衡。
  4) 违约路径同理：增补后旧违约结论罚没被拒，重核后罚没放行。
退出码 0 表示全部通过。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11322"


def req(method: str, path: str, token: str | None = None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except ValueError:
            payload = {}
        return exc.code, payload


def login(user: str) -> str:
    status, body = req("POST", "/api/login", body={"username": user, "password": "123456"})
    assert status == 200, (status, body)
    return body["token"]


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    BASE = ap.parse_args().base

    admin = login("admin")
    clerk = login("clerk")
    tag = f"L{int(time.time())}"

    # ---------- 事故 1：增补后旧通过结论直出金 ----------
    party = "P-" + tag
    code = "CG-" + tag + "-A"
    expect(req("POST", "/api/bonds", admin, {
        "party_key": party, "party_name": "夹具事故一", "initial_deposit": 200000,
    })[0] == 200, "开户失败")
    st, cage = req("POST", "/api/cages/freeze", admin, {
        "party_key": party, "contract_no": "HT-" + code, "amount": 50000,
        "beneficiary": "夹具受益人", "cage_code": code,
    })
    expect(st == 200, f"入笼失败 {st} {cage}")
    expect(req("POST", "/api/attestations", admin, {
        "cage_id": cage["id"], "outcome": "通过", "evidence": "增补前旧结论",
    })[0] == 200, "旧核验写入失败")

    st, top = req("POST", "/api/topup", admin, {
        "cage_id": cage["id"], "amount": 20000, "mode": "同笼扩代", "path": "甲",
    })
    expect(st == 200, f"增补失败 {st} {top}")
    expect(top["amount_after"] == 70000 and top["recheck_required"], "增补未扩额或未置待重核")
    expect(top["voided_attestation_id"] is not None, "旧核验未作废")

    st, rel = req("POST", "/api/releases", admin, {"cage_id": cage["id"]})
    expect(st == 409, f"事故1未拦住：增补后旧结论仍出金 {st} {rel}")
    st, _ = req("POST", "/api/forfeits", admin, {"cage_id": cage["id"]})
    expect(st == 409, "事故1：待重核笼罚没口未关")
    print("PASS 事故1：增补后旧结论直出金被拒 409，罚没口亦关")

    # ---------- 事故 2：双人同出金争用 ----------
    party2 = "P-" + tag + "R"
    code2 = "CG-" + tag + "-R"
    expect(req("POST", "/api/bonds", admin, {
        "party_key": party2, "party_name": "夹具事故二", "initial_deposit": 200000,
    })[0] == 200, "开户2失败")
    st, cage2 = req("POST", "/api/cages/freeze", admin, {
        "party_key": party2, "contract_no": "HT-" + code2, "amount": 50000,
        "beneficiary": "夹具受益人二", "cage_code": code2,
    })
    expect(st == 200, f"入笼2失败 {st} {cage2}")
    expect(req("POST", "/api/attestations", admin, {
        "cage_id": cage2["id"], "outcome": "通过", "evidence": "旧结论二",
    })[0] == 200, "旧核验2写入失败")
    st, top2 = req("POST", "/api/topup", admin, {
        "cage_id": cage2["id"], "amount": 10000, "mode": "同笼扩代",
    })
    expect(st == 200, f"增补2失败 {st} {top2}")

    lock_key = f"cage:{cage2['id']}"
    expect(req("POST", "/api/locks/acquire", admin, {"lock_key": lock_key})[0] == 200,
           "抢锁失败")
    st, _ = req("POST", "/api/releases", clerk, {"cage_id": cage2["id"]})
    expect(st == 409, "后到者未被笼锁拒绝")
    st, _ = req("POST", "/api/releases", admin, {"cage_id": cage2["id"]})
    expect(st == 409, "持锁人用增补前旧结论出金未被拒")
    st, cont = req("GET", "/api/contention", admin)
    expect(any(c["lock_key"] == lock_key for c in cont["items"]), "后到者未留争用痕")
    st, board = req("GET", f"/api/recheck/{cage2['id']}", admin)
    expect(board["gate"] == "closed" and board["recheck_pending"], "看板未显示闸门关闭")
    print("PASS 事故2：双人争用只留痕，持锁人旧结论出金被拒")

    # ---------- 甲路径闭环：重核后放行 + 对账 ----------
    st, newatt = req("POST", "/api/attestations", admin, {
        "cage_id": cage["id"], "outcome": "通过", "evidence": "新额影子复检单晋升",
    })
    expect(st == 200, f"重核写新结论失败 {st} {newatt}")
    st, board = req("GET", f"/api/recheck/{cage['id']}", admin)
    expect(board["gate"] == "open" and not board["recheck_pending"], "重核后闸门未开")
    st, rel = req("POST", "/api/releases", admin, {"cage_id": cage["id"]})
    expect(st == 200 and rel["amount"] == 70000, f"重核后出金失败 {st} {rel}")
    st, recon = req("GET", f"/api/reconcile/{code}", admin)
    expect(recon["balanced"], f"对账失衡 {recon}")
    print("PASS 甲路径：重核后出金 70000，对账平衡")

    # ---------- 违约路径：增补后旧违约结论罚没被拒，重核后放行 ----------
    party3 = "P-" + tag + "F"
    code3 = "CG-" + tag + "-F"
    expect(req("POST", "/api/bonds", admin, {
        "party_key": party3, "party_name": "夹具违约", "initial_deposit": 200000,
    })[0] == 200, "开户3失败")
    st, cage3 = req("POST", "/api/cages/freeze", admin, {
        "party_key": party3, "contract_no": "HT-" + code3, "amount": 30000,
        "beneficiary": "夹具受益人三", "cage_code": code3,
    })
    expect(st == 200, f"入笼3失败 {st} {cage3}")
    expect(req("POST", "/api/attestations", admin, {
        "cage_id": cage3["id"], "outcome": "违约", "evidence": "旧违约结论",
    })[0] == 200, "旧违约核验写入失败")
    st, _ = req("POST", "/api/topup", admin, {
        "cage_id": cage3["id"], "amount": 5000, "mode": "同笼扩代",
    })
    expect(st == 200, "违约笼增补失败")
    st, _ = req("POST", "/api/forfeits", admin, {"cage_id": cage3["id"]})
    expect(st == 409, "增补后旧违约结论仍可罚没")
    st, _ = req("POST", "/api/attestations", admin, {
        "cage_id": cage3["id"], "outcome": "违约", "evidence": "新额复检违约",
    })
    expect(st == 200, "违约路径重核失败")
    st, fr = req("POST", "/api/forfeits", admin, {"cage_id": cage3["id"]})
    expect(st == 200 and fr["amount"] == 35000, f"重核后罚没失败 {st} {fr}")
    st, recon3 = req("GET", f"/api/reconcile/{code3}", admin)
    expect(recon3["balanced"], f"违约路径对账失衡 {recon3}")
    print("PASS 违约路径：增补后旧结论罚没被拒，重核后罚没 35000，对账平衡")

    # ---------- 五页同源 + 偏航留痕 ----------
    st, board = req("GET", "/api/recheck/board", admin)
    expect(st == 200 and board["manifest"]["locked"], "纪要未锁死")
    expect(board["manifest"]["locked_at"] == "2026-11-22", "纪要锁定日不符")
    expect(set(board["sources"]) == {"增补页", "核验页", "解笼页", "罚没页", "审计页"},
           "五页同源清单不符")
    st, _ = req("POST", "/api/topup", admin, {
        "cage_id": cage3["id"], "amount": 1, "mode": "新笼桥接",
    })
    expect(st == 409, "偏离纪要的增补未被拒")
    st, board = req("GET", "/api/recheck/board", admin)
    expect(any("topup_path_deviation" in (d["payload"] or "") for d in board["deviations"]),
           "偏航未落审计")
    print("PASS 纪要锁死 + 五页同源 + 偏航拒写留痕")
    print("ALL LIVE FIXTURES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
