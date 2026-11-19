"""交易标注：标签、备注、忽略标记。

存储于 data/annotations.json，按账单 ID + 交易键组织。
交易键优先使用交易号，缺失时回退为时间+金额+方向+对方。
"""

import json
import os
from datetime import datetime

from .settings import abs_path, ensure_dir, get_logger

logger = get_logger("bill.annotations")

ANNOTATION_FILE = "data/annotations.json"


def _path() -> str:
    return abs_path(ANNOTATION_FILE)


def _load() -> dict:
    path = _path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    path = _path()
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def key_for(row) -> str:
    """由交易行生成稳定的标注键。"""
    get = row.get if hasattr(row, "get") else (lambda k, d=None: row[k])
    no = str(get("trade_no") or "").strip()
    if no and no.lower() not in ("nan", "none"):
        return "no:" + no
    parts = [
        str(get(k) or "") for k in ("trade_time", "amount", "direction", "counterparty")
    ]
    return "mix:" + "|".join(parts)


def bills_map(bill_id: str) -> dict:
    return _load().get(bill_id, {}) or {}


def set_annotation(
    bill_id: str, key: str, tag: str = "", note: str = "", ignored: bool = False
) -> dict:
    key = str(key or "").strip()
    if not key:
        raise ValueError("缺少交易键")
    data = _load()
    bucket = data.setdefault(bill_id, {})
    item = {
        "tag": str(tag or "").strip(),
        "note": str(note or "").strip(),
        "ignored": bool(ignored),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if not item["tag"] and not item["note"] and not item["ignored"]:
        bucket.pop(key, None)
        item = {}
    else:
        bucket[key] = item
    if not bucket:
        data.pop(bill_id, None)
    _save(data)
    return item


def delete_annotation(bill_id: str, key: str) -> bool:
    data = _load()
    bucket = data.get(bill_id) or {}
    if key not in bucket:
        return False
    bucket.pop(key, None)
    if not bucket:
        data.pop(bill_id, None)
    _save(data)
    return True


def ignored_keys(bill_id: str) -> set:
    return {k for k, v in bills_map(bill_id).items() if v.get("ignored")}


def tagged_keys(bill_id: str) -> dict:
    return {k: v.get("tag", "") for k, v in bills_map(bill_id).items() if v.get("tag")}


def apply_ignored(bill_id: str, df):
    """过滤掉被标记为忽略的交易。"""
    if df is None or df.empty:
        return df
    ignored = ignored_keys(bill_id)
    if not ignored:
        return df
    keys = df.apply(lambda row: key_for(row), axis=1)
    return df[~keys.isin(ignored)].reset_index(drop=True)


def summary(bill_id: str) -> dict:
    bucket = bills_map(bill_id)
    ignored = sum(1 for v in bucket.values() if v.get("ignored"))
    tagged = sum(1 for v in bucket.values() if v.get("tag"))
    return {
        "total": len(bucket),
        "ignored": ignored,
        "tagged": tagged,
        "items": bucket,
    }
