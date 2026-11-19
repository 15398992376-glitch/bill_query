"""SQLite 索引层：为账单与交易提供跨账单检索能力。

pickle 仍是权威数据源，SQLite 只是可重建的检索索引，
索引失败不影响主流程。
"""

import os
import sqlite3
from datetime import datetime

from .settings import abs_path, ensure_dir, get_logger

logger = get_logger("bill.store")

DB_FILE = "data/bills.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bills (
    bill_id      TEXT PRIMARY KEY,
    source_file  TEXT,
    channel      TEXT,
    record_count INTEGER,
    start_date   TEXT,
    end_date     TEXT,
    indexed_at   TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id      TEXT NOT NULL,
    trade_time   TEXT,
    trade_date   TEXT,
    direction    TEXT,
    amount       REAL,
    category     TEXT,
    counterparty TEXT,
    goods        TEXT,
    trade_no     TEXT,
    is_transfer  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tx_bill ON transactions(bill_id);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(trade_date);
CREATE INDEX IF NOT EXISTS idx_tx_amount ON transactions(amount);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_no ON transactions(trade_no);
"""


def db_path() -> str:
    return abs_path(DB_FILE)


def _connect():
    path = db_path()
    ensure_dir(os.path.dirname(path))
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def index_dataset(dataset) -> int:
    """把一个数据集写入索引，返回写入行数。"""
    df = dataset.df
    try:
        init_db()
        with _connect() as conn:
            conn.execute(
                "DELETE FROM transactions WHERE bill_id = ?", (dataset.bill_id,)
            )
            conn.execute("DELETE FROM bills WHERE bill_id = ?", (dataset.bill_id,))
            rows = []
            for _, row in df.iterrows():
                rows.append(
                    (
                        dataset.bill_id,
                        str(row.get("trade_time") or ""),
                        str(row.get("trade_date") or ""),
                        str(row.get("direction") or ""),
                        _to_float(row.get("amount")),
                        str(row.get("category") or ""),
                        str(row.get("counterparty") or ""),
                        str(row.get("goods") or ""),
                        str(row.get("trade_no") or ""),
                        1 if bool(row.get("is_transfer")) else 0,
                    )
                )
            conn.executemany(
                "INSERT INTO transactions (bill_id, trade_time, trade_date, direction,"
                " amount, category, counterparty, goods, trade_no, is_transfer)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            dates = df["trade_date"].dropna() if "trade_date" in df else []
            conn.execute(
                "INSERT INTO bills (bill_id, source_file, channel, record_count,"
                " start_date, end_date, indexed_at) VALUES (?,?,?,?,?,?,?)",
                (
                    dataset.bill_id,
                    dataset.source_file,
                    dataset.channel,
                    int(len(df)),
                    str(min(dates)) if len(dates) else "",
                    str(max(dates)) if len(dates) else "",
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLite 索引失败 %s: %s", dataset.bill_id, exc)
        return 0


def remove_bill(bill_id: str) -> None:
    try:
        init_db()
        with _connect() as conn:
            conn.execute("DELETE FROM transactions WHERE bill_id = ?", (bill_id,))
            conn.execute("DELETE FROM bills WHERE bill_id = ?", (bill_id,))
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLite 删除索引失败 %s: %s", bill_id, exc)


def search(keyword: str, limit: int = 100, bill_id: str = "") -> dict:
    """跨账单关键词检索（对方/商品/分类/交易号/时间）。"""
    text = str(keyword or "").strip()
    if not text:
        return {"keyword": "", "total": 0, "rows": []}
    like = f"%{text}%"
    where = (
        " WHERE (counterparty LIKE ? OR goods LIKE ? OR category LIKE ?"
        " OR trade_no LIKE ? OR trade_time LIKE ?)"
    )
    params = [like, like, like, like, like]
    if bill_id:
        where += " AND bill_id = ?"
        params.append(bill_id)
    try:
        init_db()
        with _connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM transactions{where}", params
            ).fetchone()["c"]
            rows = conn.execute(
                f"SELECT * FROM transactions{where} ORDER BY trade_time DESC LIMIT ?",
                params + [int(limit)],
            ).fetchall()
        return {
            "keyword": text,
            "total": int(total),
            "rows": [dict(r) for r in rows],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLite 检索失败: %s", exc)
        return {"keyword": text, "total": 0, "rows": []}


def stats() -> dict:
    try:
        init_db()
        with _connect() as conn:
            bills = conn.execute(
                "SELECT b.*, (SELECT COUNT(*) FROM transactions t WHERE t.bill_id=b.bill_id)"
                " AS indexed_rows FROM bills b ORDER BY indexed_at DESC"
            ).fetchall()
            totals = conn.execute(
                "SELECT COUNT(*) AS rows, COALESCE(SUM(amount),0) AS amount,"
                " COALESCE(SUM(CASE WHEN direction='支出' THEN amount ELSE 0 END),0) AS expense"
                " FROM transactions"
            ).fetchone()
        return {
            "bills": [dict(b) for b in bills],
            "indexed_rows": int(totals["rows"]),
            "indexed_amount": round(float(totals["amount"]), 2),
            "indexed_expense": round(float(totals["expense"]), 2),
            "db_file": db_path(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLite 统计失败: %s", exc)
        return {
            "bills": [],
            "indexed_rows": 0,
            "indexed_amount": 0,
            "indexed_expense": 0,
        }


def rebuild(datasets: list) -> dict:
    """全量重建索引。"""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM transactions")
        conn.execute("DELETE FROM bills")
    count = 0
    for dataset in datasets:
        index_dataset(dataset)
        count += 1
    return {"bills": count, "rows": int(stats().get("indexed_rows", 0))}
