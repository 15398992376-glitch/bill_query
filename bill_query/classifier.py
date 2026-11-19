from typing import Dict, List, Optional

import pandas as pd

from .settings import billing_conf, get_logger

logger = get_logger("bill.classifier")

FALLBACK_CATEGORY = "其他"
TRANSFER_KEYWORDS = ("转账", "红包", "群收款", "收款")
TRANSFER_FLAG_KEYWORDS = (
    "转账",
    "红包",
    "提现",
    "充值",
    "还款",
    "退款",
    "零钱通",
    "余额宝",
    "内部划转",
    "群收款",
)


def _build_keyword_index() -> List[tuple]:
    index = []
    categories = billing_conf("categories", {}) or {}
    for category, keywords in categories.items():
        if not isinstance(keywords, (list, tuple)):
            continue
        for kw in keywords:
            if kw:
                index.append((str(kw), category))
    index.sort(key=lambda item: len(item[0]), reverse=True)
    return index


_KEYWORD_INDEX = _build_keyword_index()


def rule_classify(
    counterparty: str, goods: str, trade_type: str, direction: str
) -> str:
    text = f"{counterparty} {goods} {trade_type}"
    for keyword, category in _KEYWORD_INDEX:
        if keyword in text:
            return category
    if direction == "收入":
        for kw in TRANSFER_KEYWORDS:
            if kw in text:
                return "转账红包"
    if direction == "支出" and not text.strip():
        return FALLBACK_CATEGORY
    return FALLBACK_CATEGORY


def classify_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    frame = df.copy()
    categories = []
    for _, row in frame.iterrows():
        raw_category = str(row.get("raw_category") or "").strip()
        if raw_category and raw_category.lower() not in ("nan", "none"):
            categories.append(raw_category)
            continue
        categories.append(
            rule_classify(
                str(row.get("counterparty") or ""),
                str(row.get("goods") or ""),
                str(row.get("trade_type") or ""),
                str(row.get("direction") or ""),
            )
        )
    frame["category"] = categories
    flags = []
    for _, row in frame.iterrows():
        text = f"{row.get('trade_type') or ''} {row.get('goods') or ''} {row.get('counterparty') or ''} {row.get('category') or ''}"
        flags.append(any(kw in text for kw in TRANSFER_FLAG_KEYWORDS))
    frame["is_transfer"] = flags
    return frame


def category_overview(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["category", "amount", "count", "ratio"])
    expense = df[df["direction"] == "支出"]
    if expense.empty:
        return pd.DataFrame(columns=["category", "amount", "count", "ratio"])
    grouped = (
        expense.groupby("category")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    total = grouped["amount"].sum() or 1
    grouped["ratio"] = (grouped["amount"] / total * 100).round(2)
    grouped["amount"] = grouped["amount"].round(2)
    return grouped


def counterparty_ranking(
    df: pd.DataFrame, top: int = 20, direction: str = "支出"
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["counterparty", "amount", "count"])
    subset = df[df["direction"] == direction]
    if subset.empty:
        return pd.DataFrame(columns=["counterparty", "amount", "count"])
    grouped = (
        subset.groupby("counterparty")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
    )
    grouped = grouped[grouped["counterparty"].str.strip() != ""]
    grouped = grouped.sort_values("amount", ascending=False).head(top)
    grouped["amount"] = grouped["amount"].round(2)
    return grouped.reset_index(drop=True)


def category_of(df: pd.DataFrame) -> Dict[str, float]:
    return {
        row["category"]: row["amount"] for _, row in category_overview(df).iterrows()
    }


def available_categories(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return list((billing_conf("categories", {}) or {}).keys())
    base = list((billing_conf("categories", {}) or {}).keys())
    extra = [c for c in df["category"].dropna().unique().tolist() if c not in base]
    return base + sorted(extra)
