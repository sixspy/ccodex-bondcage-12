"""增补重核：待重核笼的重裁入口与五页同源看板。

五页（增补 / 核验 / 解笼 / 罚没 / 审计）的账实统一从 ``/api/recheck/board``
取数；任一页只改提醒字而闸门未落库，均视为偏离纪要。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import connect
from recheck_policy import DEVIATION_ACTION, lock_state

router = APIRouter(tags=["recheck"])


def pending_recheck(conn, cage_id: int) -> dict | None:
    """返回该笼未完成的增补 job（若处于待重核）。"""
    return conn.execute(
        """SELECT * FROM topup_jobs
           WHERE cage_id=? AND recheck_required=1
           ORDER BY id DESC LIMIT 1""",
        (cage_id,),
    ).fetchone()


def _cage_brief(conn, cage) -> dict:
    job = pending_recheck(conn, cage["id"])
    live_att = conn.execute(
        """SELECT * FROM attestations
           WHERE cage_id=? AND attest_gen=? AND voided_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (cage["id"], int(cage["generation"])),
    ).fetchone()
    voided = conn.execute(
        """SELECT * FROM attestations
           WHERE cage_id=? AND attest_gen=? AND voided_at IS NOT NULL
           ORDER BY id DESC""",
        (cage["id"], int(cage["generation"])),
    ).fetchall()
    gate_open = cage["status"] in ("核验通过", "核验违约") and live_att is not None
    return {
        "cage_id": cage["id"],
        "cage_code": cage["cage_code"],
        "party_key": cage["party_key"],
        "contract_no": cage["contract_no"],
        "generation": int(cage["generation"]),
        "status": cage["status"],
        "amount": float(cage["amount"]),
        "available": float(cage["available"]),
        "recheck_pending": bool(job),
        "topup_job_id": job["id"] if job else None,
        "topup_amount": float(job["amount"]) if job else None,
        "amount_before": float(job["amount_before"]) if job else None,
        "voided_attestation_ids": [int(v["id"]) for v in voided],
        "live_attestation": dict(live_att) if live_att else None,
        "gate": "open" if gate_open else "closed",
        "gate_reason": (
            "存在有效新结论"
            if gate_open
            else ("待重核：扩额后须重新核验" if job else "无可出金结论")
        ),
    }


@router.get("/api/recheck/board")
def recheck_board(authorization: AuthHeader = None):
    """五页同源看板：增补页、核验页、解笼页、罚没页、审计页共用。"""
    require_user(authorization)
    with connect() as conn:
        cages = conn.execute("SELECT * FROM cages ORDER BY id").fetchall()
        items = [_cage_brief(conn, c) for c in cages]
        pending = [i for i in items if i["recheck_pending"]]
        jobs = conn.execute(
            """SELECT j.*, c.cage_code AS cage_code_now, c.status AS cage_status
               FROM topup_jobs j JOIN cages c ON c.id=j.cage_id
               ORDER BY j.id DESC"""
        ).fetchall()
        deviations = conn.execute(
            """SELECT id, actor, target, payload, created_at FROM audit_trail
               WHERE action=? ORDER BY id DESC LIMIT 50""",
            (DEVIATION_ACTION,),
        ).fetchall()
        manifest = lock_state()
        return {
            "manifest": manifest,
            "pending_count": len(pending),
            "pending": pending,
            "cages": items,
            "topup_jobs": [dict(j) for j in jobs],
            "deviations": [dict(d) for d in deviations],
            "gate_policy": {
                "path": "甲",
                "rule": "扩额后必须重核才能出金",
                "modes": ["同笼扩代"],
            },
            "sources": [
                "增补页",
                "核验页",
                "解笼页",
                "罚没页",
                "审计页",
            ],
        }


@router.get("/api/recheck/{cage_id}")
def recheck_one(cage_id: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        cage = conn.execute("SELECT * FROM cages WHERE id=?", (cage_id,)).fetchone()
        if not cage:
            raise HTTPException(404, "笼不存在")
        return _cage_brief(conn, cage)
