"""增补入笼：甲路径。

增补提交、扩额、作废旧核验、笼改「待重核」态、写审计在同一事务内完成；
任一环节失败则增补与作废同滚。乙路径（影子复检）与其它模式一律记
``recheck_deviation`` 并拒绝写入。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from locks import release, require_lock
from models import TopupIn
from recheck_policy import (
    DEVIATION_ACTION,
    MODE_TOPUP,
    PATH_JIA,
    assert_manifest_locked,
)

router = APIRouter(tags=["topup"])

TOPUP_ALLOWED_STATUS = (
    "已冻结",
    "核验通过",
    "核验违约",
    "部分解笼",
    "部分罚没",
)


@router.get("/api/topup/jobs")
def list_jobs(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT j.*, c.cage_code AS cage_code_now, c.status AS cage_status
               FROM topup_jobs j
               JOIN cages c ON c.id=j.cage_id
               ORDER BY j.id DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


def _deviation(conn, actor: str, target: str, payload: dict) -> None:
    write_audit(conn, actor, DEVIATION_ACTION, target, payload)
    conn.commit()


@router.post("/api/topup")
@router.post("/api/topup-stub")
def do_topup(body: TopupIn, authorization: AuthHeader = None):
    """增补抬额（甲路径）：扩额 + 作废旧核验 + 待重核，同事务。"""
    user = require_writer(authorization)
    lock_key = f"cage:{body.cage_id}"
    declared_path = getattr(body, "path", PATH_JIA)
    with connect() as conn:
        require_lock(conn, lock_key, user)
        committed = False
        try:
            cage = conn.execute(
                "SELECT * FROM cages WHERE id=?", (body.cage_id,)
            ).fetchone()
            target = cage["cage_code"] if cage else f"cage:{body.cage_id}"
            if not cage:
                raise HTTPException(404, "笼不存在")

            # 口径偏离：非甲路径 / 非同一笼扩代 / 纪要未锁死，一律拒写并留痕
            if declared_path != PATH_JIA or body.mode != MODE_TOPUP:
                _deviation(
                    conn,
                    user,
                    target,
                    {
                        "reason": "topup_path_deviation",
                        "declared_path": declared_path,
                        "mode": body.mode,
                        "allowed_path": PATH_JIA,
                        "allowed_mode": MODE_TOPUP,
                    },
                )
                raise HTTPException(
                    409, "重核偏航：仅允许甲路径「同笼扩代」，不得混用乙路径"
                )
            try:
                lock_meta = assert_manifest_locked()
            except HTTPException as exc:
                _deviation(
                    conn,
                    user,
                    target,
                    {"reason": "manifest_not_locked", "detail": exc.detail},
                )
                raise

            if cage["status"] not in TOPUP_ALLOWED_STATUS:
                raise HTTPException(409, "当前笼状态禁止增补")
            amount = float(body.amount)
            if amount <= 0:
                raise HTTPException(400, "增补金额须大于 0")
            gen = int(cage["generation"])
            before_amount = float(cage["amount"])
            before_avail = float(cage["available"])

            # 账户侧冻结必须同步抬额（增补资金从可用余额划入笼冻结）
            acct = conn.execute(
                "SELECT * FROM bond_accounts WHERE party_key=?",
                (cage["party_key"],),
            ).fetchone()
            if not acct:
                raise HTTPException(409, "当事人保证金户不存在，禁止增补")
            free = float(acct["balance"]) - float(acct["frozen"])
            if amount > free + 1e-9:
                raise HTTPException(409, "当事人可用保证金不足，禁止增补")

            now = now_iso()

            # 1) 作废当前笼代仍有效的旧核验结论（保留原行，写作废痕）
            prior = conn.execute(
                """SELECT id, outcome FROM attestations
                   WHERE cage_id=? AND attest_gen=? AND voided_at IS NULL
                   ORDER BY id DESC""",
                (body.cage_id, gen),
            ).fetchall()
            voided_id = None
            for row in prior:
                conn.execute(
                    """UPDATE attestations
                       SET voided_at=?, voided_by=?, void_reason=?
                       WHERE id=? AND voided_at IS NULL""",
                    (now, user, "增补抬额触发重核", row["id"]),
                )
                voided_id = row["id"]

            # 2) 扩额：笼额与可用额同增，账户冻结同增
            new_amount = round(before_amount + amount, 6)
            new_avail = round(before_avail + amount, 6)
            conn.execute(
                """UPDATE cages SET amount=?, available=?, status='待重核'
                   WHERE id=?""",
                (new_amount, new_avail, body.cage_id),
            )
            conn.execute(
                "UPDATE bond_accounts SET frozen = frozen + ? WHERE party_key=?",
                (amount, cage["party_key"]),
            )

            # 3) 登记增补 job（与扩额/作废同事务）
            cur = conn.execute(
                """INSERT INTO topup_jobs(
                       cage_id,amount,mode,status,detail,created_at,party_key,
                       cage_code,amount_before,amount_after,status_before,
                       status_after,generation,voided_attestation_id,
                       recheck_required,applied_at,actor)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    body.cage_id,
                    amount,
                    body.mode,
                    "已扩额待重核",
                    "甲路径：扩额并作废旧核验，重核前出金口关闭",
                    now,
                    cage["party_key"],
                    cage["cage_code"],
                    before_amount,
                    new_amount,
                    cage["status"],
                    "待重核",
                    gen,
                    voided_id,
                    1,
                    now,
                    user,
                ),
            )
            job_id = cur.lastrowid

            # 4) 审计：增补与作废同一条业务痕
            write_audit(
                conn,
                user,
                "topup_recheck_open",
                cage["cage_code"],
                {
                    "job_id": job_id,
                    "path": PATH_JIA,
                    "mode": body.mode,
                    "amount": amount,
                    "amount_before": before_amount,
                    "amount_after": new_amount,
                    "generation": gen,
                    "voided_attestation_id": voided_id,
                    "status_before": cage["status"],
                    "status_after": "待重核",
                    "manifest": lock_meta,
                    "note": "扩额与作废同事务；重核前禁止解笼与罚没",
                },
            )

            # 事务后自检：任一未落地则视为母仓损坏
            after = conn.execute(
                "SELECT amount, available, status FROM cages WHERE id=?",
                (body.cage_id,),
            ).fetchone()
            still_live = conn.execute(
                """SELECT COUNT(*) c FROM attestations
                   WHERE cage_id=? AND attest_gen=? AND voided_at IS NULL""",
                (body.cage_id, gen),
            ).fetchone()["c"]
            if (
                abs(float(after["amount"]) - new_amount) > 1e-6
                or abs(float(after["available"]) - new_avail) > 1e-6
                or after["status"] != "待重核"
                or still_live
            ):
                raise HTTPException(500, "增补事务自检失败，母仓损坏")

            conn.commit()
            committed = True
            return {
                "job_id": job_id,
                "status": "已扩额待重核",
                "path": PATH_JIA,
                "mode": body.mode,
                "amount_before": before_amount,
                "amount_after": new_amount,
                "voided_attestation_id": voided_id,
                "recheck_required": True,
                "gate": "closed",
                "cage_unchanged": False,
                "manifest_locked_at": lock_meta.get("locked_at"),
            }
        finally:
            if committed:
                conn.commit()
            else:
                # 甲路径：失败则增补与作废同滚；偏航痕已单独提交，不受回滚影响
                conn.rollback()
            release(conn, lock_key, user)
            conn.commit()
