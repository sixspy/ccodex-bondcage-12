"""增补重核纪要的当日锁死校验。

纪要正文在 ``docs/增补重核纪要.md``，摘要与锁定日在
``docs/增补重核纪要.sha256``。任何增补 / 重核写入前都必须通过本校验；
正文被改动（摘要不一致）或缺失时，一律拒绝写入并记重核偏航。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "增补重核纪要.md"
LOCK = ROOT / "docs" / "增补重核纪要.sha256"

PATH_JIA = "甲"
MODE_TOPUP = "同笼扩代"
DEVIATION_ACTION = "recheck_deviation"


def doc_digest() -> str:
    return hashlib.sha256(DOC.read_bytes()).hexdigest()


def lock_state() -> dict:
    if not DOC.exists() or not LOCK.exists():
        return {"locked": False, "reason": "纪要或锁文件缺失"}
    try:
        meta = json.loads(LOCK.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"locked": False, "reason": "锁文件不可读"}
    expect = str(meta.get("sha256", ""))
    actual = doc_digest()
    if not expect or expect != actual:
        return {
            "locked": False,
            "reason": "纪要摘要不一致，已偏离锁死版本",
            "expected": expect,
            "actual": actual,
        }
    return {
        "locked": True,
        "locked_at": meta.get("locked_at"),
        "doc": meta.get("doc"),
        "sha256": actual,
    }


def assert_manifest_locked() -> dict:
    state = lock_state()
    if not state["locked"]:
        raise HTTPException(409, f"增补重核纪要未锁死：{state['reason']}，拒绝写入")
    return state
