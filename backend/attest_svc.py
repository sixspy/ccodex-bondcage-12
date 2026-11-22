"""履约核验：通过后允许解笼；违约后允许罚没；增补后须重核。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from locks import release, require_lock
from models import AttestIn
from recheck_svc import pending_recheck

router = APIRouter(tags=["attest"])

ALLOWED = {"通过", "违约"}


@router.get("/api/attestations")
def list_attestations(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT a.*, c.cage_code, c.contract_no, c.status AS cage_status
               FROM attestations a
               JOIN cages c ON c.id=a.cage_id
               ORDER BY a.id DESC LIMIT 200"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/attestations")
def create_attestation(body: AttestIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    if body.outcome not in ALLOWED:
        raise HTTPException(400, "outcome 须为通过或违约")
    lock_key = f"cage:{body.cage_id}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            cage = conn.execute(
                "SELECT * FROM cages WHERE id=?", (body.cage_id,)
            ).fetchone()
            if not cage:
                raise HTTPException(404, "笼不存在")
            job = pending_recheck(conn, body.cage_id)
            # 待重核是核验口唯一放行的状态；其余沿用已冻结
            if cage["status"] == "待重核":
                if not job:
                    raise HTTPException(409, "待重核笼缺少增补 job，禁止核验")
            elif cage["status"] != "已冻结":
                raise HTTPException(409, "仅已冻结或待重核笼可核验")
            if float(cage["available"]) <= 0:
                raise HTTPException(409, "笼可用额为 0，禁止核验")
            gen = int(cage["generation"])
            # 同一笼代只允许一条有效（未作废）核验结论
            prior = conn.execute(
                """SELECT id, outcome FROM attestations
                   WHERE cage_id=? AND attest_gen=? AND voided_at IS NULL""",
                (body.cage_id, gen),
            ).fetchone()
            if prior:
                raise HTTPException(409, "本笼代已有有效核验结论，禁止改口")
            now = now_iso()
            cur = conn.execute(
                """INSERT INTO attestations(
                       cage_id,outcome,evidence,attest_gen,officer,created_at,
                       topup_job_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    body.cage_id,
                    body.outcome,
                    body.evidence or "",
                    gen,
                    user,
                    now,
                    job["id"] if job else None,
                ),
            )
            new_status = "核验通过" if body.outcome == "通过" else "核验违约"
            conn.execute(
                "UPDATE cages SET status=? WHERE id=?",
                (new_status, body.cage_id),
            )
            # 重核完成：增补 job 收口，出金口由状态闸门放行
            if job:
                conn.execute(
                    """UPDATE topup_jobs SET recheck_required=0
                       WHERE id=?""",
                    (job["id"],),
                )
            write_audit(
                conn,
                user,
                "attest",
                cage["cage_code"],
                {
                    "attestation_id": cur.lastrowid,
                    "outcome": body.outcome,
                    "attest_gen": gen,
                    "evidence": body.evidence or "",
                    "after_topup_job_id": job["id"] if job else None,
                    "recheck_closed": bool(job),
                },
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM attestations WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        finally:
            release(conn, lock_key, user)
            conn.commit()
