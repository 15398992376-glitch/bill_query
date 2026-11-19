import os
from calendar import monthrange
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from . import classifier
from .repository import repository


def _period_frame(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["period", "income", "expense", "net", "count"])
    frame = df.copy()
    ts = pd.to_datetime(frame["trade_time"], errors="coerce")
    frame = frame[ts.notna()]
    if frame.empty:
        return pd.DataFrame(columns=["period", "income", "expense", "net", "count"])
    ts = pd.to_datetime(frame["trade_time"], errors="coerce")
    if freq == "day":
        frame["period"] = ts.dt.strftime("%Y-%m-%d")
    elif freq == "week":
        frame["period"] = ts.dt.strftime("%G-W%V")
    elif freq == "year":
        frame["period"] = ts.dt.strftime("%Y")
    else:
        frame["period"] = ts.dt.strftime("%Y-%m")

    income = (
        frame[frame["direction"] == "收入"]
        .groupby("period")["amount"]
        .sum()
        .rename("income")
    )
    expense = (
        frame[frame["direction"] == "支出"]
        .groupby("period")["amount"]
        .sum()
        .rename("expense")
    )
    count = frame.groupby("period")["amount"].size().rename("count")
    merged = pd.concat([income, expense, count], axis=1).fillna(0)
    merged["income"] = merged["income"].round(2)
    merged["expense"] = merged["expense"].round(2)
    merged["net"] = (merged["income"] - merged["expense"]).round(2)
    merged = merged.reset_index().rename(columns={"index": "period"})
    merged["count"] = merged["count"].astype(int)
    return merged.sort_values("period").reset_index(drop=True)


def overview(bill_id: str, start_date: str = "", end_date: str = "", **filters) -> dict:
    from .repository import query_filter

    df = query_filter(bill_id, start_date=start_date, end_date=end_date, **filters)
    income = df[df["direction"] == "收入"]
    expense = df[df["direction"] == "支出"]
    days = max(df["trade_date"].nunique(), 1) if not df.empty else 1
    total_expense = float(expense["amount"].sum())
    total_income = float(income["amount"].sum())
    transfer = (
        df[df["is_transfer"].astype(bool)] if "is_transfer" in df else df.iloc[0:0]
    )
    return {
        "record_count": int(len(df)),
        "days": int(days),
        "income_total": round(total_income, 2),
        "expense_total": round(total_expense, 2),
        "net_total": round(total_income - total_expense, 2),
        "income_count": int(len(income)),
        "expense_count": int(len(expense)),
        "avg_daily_expense": round(total_expense / days, 2),
        "avg_ticket": round(total_expense / len(expense), 2) if len(expense) else 0.0,
        "max_expense": round(float(expense["amount"].max()), 2)
        if len(expense)
        else 0.0,
        "min_expense": round(float(expense["amount"].min()), 2)
        if len(expense)
        else 0.0,
        "median_expense": round(float(expense["amount"].median()), 2)
        if len(expense)
        else 0.0,
        "savings_rate": round((total_income - total_expense) / total_income * 100, 2)
        if total_income > 0
        else 0.0,
        "transfer_count": int(len(transfer)),
        "transfer_amount": round(float(transfer["amount"].sum()), 2)
        if not transfer.empty
        else 0.0,
        "start_date": df["trade_date"].min() if not df.empty else "",
        "end_date": df["trade_date"].max() if not df.empty else "",
        "forecast_month_expense": _forecast_month(df),
    }


def _forecast_month(df: pd.DataFrame) -> float:
    """按最近一个有数据月份的日均支出，预估该月完整月支出。"""
    if df is None or df.empty or "trade_month" not in df:
        return 0.0
    expense = df[df["direction"] == "支出"]
    if expense.empty:
        return 0.0
    last_month = sorted(expense["trade_month"].unique().tolist())[-1]
    part = expense[expense["trade_month"] == last_month]
    days = max(part["trade_date"].nunique(), 1)
    from calendar import monthrange

    year, month = (int(x) for x in str(last_month).split("-")[:2])
    days_in_month = monthrange(year, month)[1]
    return round(float(part["amount"].sum()) / days * days_in_month, 2)


def trend(
    bill_id: str,
    freq: str = "month",
    start_date: str = "",
    end_date: str = "",
    **filters,
) -> list:
    from .repository import query_filter

    df = query_filter(bill_id, start_date=start_date, end_date=end_date, **filters)
    return _period_frame(df, freq).to_dict(orient="records")


def category_stats(
    bill_id: str,
    start_date: str = "",
    end_date: str = "",
    direction: str = "支出",
    top: Optional[int] = None,
    **filters,
) -> list:
    from .repository import query_filter

    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    if direction == "支出":
        grouped = classifier.category_overview(df)
    else:
        if df.empty:
            return []
        grouped = (
            df.groupby("category")
            .agg(amount=("amount", "sum"), count=("amount", "size"))
            .reset_index()
            .sort_values("amount", ascending=False)
        )
        total = grouped["amount"].sum() or 1
        grouped["ratio"] = (grouped["amount"] / total * 100).round(2)
    records = grouped.to_dict(orient="records")
    return records[:top] if top else records


def counterparty_stats(
    bill_id: str,
    direction: str = "支出",
    top: int = 20,
    start_date: str = "",
    end_date: str = "",
    **filters,
) -> list:
    from .repository import query_filter

    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    return classifier.counterparty_ranking(df, top=top, direction=direction).to_dict(
        orient="records"
    )


def weekday_stats(
    bill_id: str, start_date: str = "", end_date: str = "", **filters
) -> list:
    from .repository import query_filter

    direction = filters.pop("direction", "") or "支出"
    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    if df.empty:
        return []
    names = {
        1: "周一",
        2: "周二",
        3: "周三",
        4: "周四",
        5: "周五",
        6: "周六",
        7: "周日",
    }
    grouped = (
        df.groupby("trade_weekday")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
    )
    grouped["weekday"] = grouped["trade_weekday"].map(names)
    grouped["amount"] = grouped["amount"].round(2)
    return grouped[["trade_weekday", "weekday", "amount", "count"]].to_dict(
        orient="records"
    )


def hour_stats(
    bill_id: str, start_date: str = "", end_date: str = "", **filters
) -> list:
    from .repository import query_filter

    direction = filters.pop("direction", "") or "支出"
    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    if df.empty:
        return []
    grouped = (
        df.groupby("trade_hour")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reindex(range(24), fill_value=0)
        .reset_index()
    )
    grouped["amount"] = grouped["amount"].round(2)
    return grouped.rename(columns={"trade_hour": "hour"}).to_dict(orient="records")


def monthly_comparison(bill_id: str) -> list:
    return trend(bill_id, freq="month")


def top_transactions(
    bill_id: str,
    top: int = 20,
    direction: str = "支出",
    start_date: str = "",
    end_date: str = "",
    **filters,
) -> list:
    from .repository import query_filter

    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    if df.empty:
        return []
    subset = df.nlargest(top, "amount")
    cols = ["trade_time", "counterparty", "goods", "category", "amount", "pay_method"]
    return subset[cols].to_dict(orient="records")


def calendar_daily(
    bill_id: str, year: int, month: int, direction: str = "支出", **filters
) -> dict:
    """返回某月每日消费日历数据（含热力图所需的格子矩阵与统计）。

    返回结构：
      - cells: 6x7 的二维数组，每格为 {date, day, weekday, in_month,
               expense, income, count, level}
      - month_summary: {total_expense, total_income, total_count,
                        max_expense, max_date, avg_expense, active_days}
      - max_amount: 用于前端色阶映射的参考最大值
    """
    from .repository import query_filter

    df = query_filter(bill_id, direction=direction, **filters)
    if df.empty:
        return {"cells": [], "month_summary": {}, "max_amount": 0}

    month_start = date(year, month, 1)
    days_in_month = monthrange(year, month)[1]
    month_end = date(year, month, days_in_month)

    # 日历格从该月第一天所在的周一开始（周一为一周的第一天）
    grid_start = month_start - timedelta(days=month_start.weekday())
    # 网格结束于该月最后一天所在周的周日
    grid_end = month_end + timedelta(days=6 - month_end.weekday())

    # 按日期聚合
    ts = pd.to_datetime(df["trade_time"], errors="coerce")
    df = df[ts.notna()].copy()
    df["d"] = ts.dt.date
    daily = (
        df.groupby("d")
        .agg(
            expense=(
                "amount",
                lambda x: float(x[df.loc[x.index, "direction"] == "支出"].sum()),
            ),
            income=(
                "amount",
                lambda x: float(x[df.loc[x.index, "direction"] == "收入"].sum()),
            ),
            count=("amount", "size"),
        )
        .reset_index()
    )
    daily_map = {row["d"]: row for _, row in daily.iterrows()}

    # 仅统计当月范围内的数据
    month_rows = daily[(daily["d"] >= month_start) & (daily["d"] <= month_end)]
    if not month_rows.empty:
        max_expense_row = month_rows.loc[month_rows["expense"].idxmax()]
        max_amount = float(month_rows["expense"].max())
        month_summary = {
            "total_expense": round(float(month_rows["expense"].sum()), 2),
            "total_income": round(float(month_rows["income"].sum()), 2),
            "total_count": int(month_rows["count"].sum()),
            "max_expense": round(float(max_expense_row["expense"]), 2),
            "max_date": str(max_expense_row["d"]),
            "avg_expense": round(float(month_rows["expense"].mean()), 2),
            "active_days": int(len(month_rows)),
            "days_in_month": days_in_month,
        }
    else:
        max_amount = 0.0
        month_summary = {
            "total_expense": 0.0,
            "total_income": 0.0,
            "total_count": 0,
            "max_expense": 0.0,
            "max_date": "",
            "avg_expense": 0.0,
            "active_days": 0,
            "days_in_month": days_in_month,
        }

    # 用 max_amount 的平方根做色阶映射，让小额消费也有区分度
    sqrt_max = (max_amount**0.5) if max_amount > 0 else 1.0

    cells = []
    cur = grid_start
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
    while cur <= grid_end:
        d_data = daily_map.get(cur)
        expense = round(float(d_data["expense"]), 2) if d_data is not None else 0.0
        income = round(float(d_data["income"]), 2) if d_data is not None else 0.0
        count = int(d_data["count"]) if d_data is not None else 0
        # 热力等级 0-4
        if expense <= 0:
            level = 0
        else:
            ratio = (expense**0.5) / sqrt_max
            level = min(4, max(1, int(ratio * 4) + 1))
        cells.append(
            {
                "date": cur.isoformat(),
                "day": cur.day,
                "weekday": weekday_names[cur.weekday()],
                "in_month": cur.month == month,
                "expense": expense,
                "income": income,
                "count": count,
                "level": level,
            }
        )
        cur += timedelta(days=1)

    return {
        "cells": cells,
        "month_summary": month_summary,
        "max_amount": round(max_amount, 2),
    }


def available_months(bill_id: str) -> list:
    """返回账单覆盖的所有月份列表，用于日历切换。"""
    dataset = repository.get(bill_id)
    if dataset.df.empty:
        return []
    ts = pd.to_datetime(dataset.df["trade_time"], errors="coerce").dropna()
    if ts.empty:
        return []
    months = sorted(ts.dt.to_period("M").unique().tolist())
    return [{"year": p.year, "month": p.month, "label": str(p)} for p in months]


def heatmap_week_hour(
    bill_id: str,
    start_date: str = "",
    end_date: str = "",
    direction: str = "支出",
    **filters,
) -> dict:
    """返回 7(星期) x 24(小时) 的消费热力矩阵。"""
    from .repository import query_filter

    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    matrix = [[0.0 for _ in range(24)] for _ in range(7)]
    counts = [[0 for _ in range(24)] for _ in range(7)]
    if not df.empty:
        for _, row in df.iterrows():
            try:
                wd = int(row["trade_weekday"]) - 1
                hr = int(row["trade_hour"])
            except (ValueError, TypeError):
                continue
            if 0 <= wd < 7 and 0 <= hr < 24:
                matrix[wd][hr] += float(row["amount"])
                counts[wd][hr] += 1
    max_amount = max((max(r) for r in matrix), default=0.0)
    labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return {
        "matrix": [[round(v, 2) for v in r] for r in matrix],
        "counts": counts,
        "weekdays": labels,
        "hours": list(range(24)),
        "max_amount": round(max_amount, 2),
        "total": round(sum(sum(r) for r in matrix), 2),
    }


def comparison(
    bill_id: str,
    start_date: str = "",
    end_date: str = "",
    direction: str = "支出",
    **filters,
) -> dict:
    """最近两个自然月的环比对比（金额、笔数、分类变化）。"""
    from .repository import query_filter

    df = query_filter(
        bill_id,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        **filters,
    )
    if df.empty:
        return {"current": {}, "previous": {}, "delta": {}, "categories": []}
    months = sorted(df["trade_month"].unique().tolist())
    current = months[-1]
    year, month = (int(x) for x in str(current).split("-")[:2])
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    previous = f"{prev_year:04d}-{prev_month:02d}"

    def agg(month_key):
        part = df[df["trade_month"] == month_key]
        return {
            "month": month_key,
            "amount": round(float(part["amount"].sum()), 2),
            "count": int(len(part)),
        }

    cur = agg(current)
    prev = agg(previous)
    yoy_month = f"{year - 1:04d}-{month:02d}"
    yoy = agg(yoy_month)

    def pct(a, b):
        return round((a - b) / b * 100, 2) if b else 0.0

    cat_cur = df[df["trade_month"] == current].groupby("category")["amount"].sum()
    cat_prev = df[df["trade_month"] == previous].groupby("category")["amount"].sum()
    categories = []
    for name in sorted(set(cat_cur.index) | set(cat_prev.index)):
        a = round(float(cat_cur.get(name, 0)), 2)
        b = round(float(cat_prev.get(name, 0)), 2)
        categories.append(
            {
                "category": name,
                "current": a,
                "previous": b,
                "delta": round(a - b, 2),
                "delta_pct": pct(a, b),
            }
        )
    categories.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "current": cur,
        "previous": prev,
        "yoy": {
            **yoy,
            "amount_pct": pct(cur["amount"], yoy["amount"]),
            "count_delta": cur["count"] - yoy["count"],
        },
        "delta": {
            "amount": round(cur["amount"] - prev["amount"], 2),
            "amount_pct": pct(cur["amount"], prev["amount"]),
            "count": cur["count"] - prev["count"],
        },
        "categories": categories,
    }


def insights(
    bill_id: str,
    start_date: str = "",
    end_date: str = "",
    **filters,
) -> list:
    """规则型消费洞察：大额、高频、深夜、订阅、环比异常、储蓄率。"""
    from .repository import query_filter

    df = query_filter(bill_id, start_date=start_date, end_date=end_date, **filters)
    expense = df[df["direction"] == "支出"]
    if expense.empty:
        return []
    result = []

    mean_amount = float(expense["amount"].mean())
    std_amount = float(expense["amount"].std() or 0)
    threshold = mean_amount + max(std_amount * 2, mean_amount)
    big = expense[expense["amount"] >= threshold].nlargest(3, "amount")
    for _, row in big.iterrows():
        result.append(
            {
                "type": "大额消费",
                "level": "warn",
                "title": f"大额支出 ¥{row['amount']:.2f}",
                "detail": f"{row['trade_time']} · {row['counterparty'] or '未知商户'} · {row['category']}",
                "value": round(float(row["amount"]), 2),
            }
        )

    top = (
        expense.groupby("counterparty")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .sort_values("count", ascending=False)
    )
    if not top.empty:
        name = top.index[0]
        row = top.iloc[0]
        if int(row["count"]) >= 5:
            result.append(
                {
                    "type": "高频消费",
                    "level": "info",
                    "title": f"最常光顾：{name or '未知商户'}",
                    "detail": f"{int(row['count'])} 笔，累计 ¥{row['amount']:.2f}，笔均 ¥{row['amount'] / row['count']:.2f}",
                    "value": int(row["count"]),
                }
            )

    night = expense[expense["trade_hour"].isin([22, 23, 0, 1, 2, 3, 4, 5])]
    if not night.empty:
        result.append(
            {
                "type": "深夜消费",
                "level": "info",
                "title": "深夜消费提醒",
                "detail": f"22:00-05:59 共 {len(night)} 笔，累计 ¥{night['amount'].sum():.2f}",
                "value": round(float(night["amount"].sum()), 2),
            }
        )

    fixed = (
        expense.assign(amt=expense["amount"].round(2))
        .groupby(["counterparty", "amt"])
        .agg(months=("trade_month", "nunique"), count=("amount", "size"))
        .reset_index()
    )
    subs = fixed[(fixed["months"] >= 3) & (fixed["count"] >= 3)].head(3)
    for _, row in subs.iterrows():
        result.append(
            {
                "type": "订阅/周期消费",
                "level": "info",
                "title": f"疑似订阅：{row['counterparty']}",
                "detail": f"连续 {int(row['months'])} 个月出现，固定金额 ¥{row['amt']:.2f}",
                "value": round(float(row["amt"]), 2),
            }
        )

    comp = comparison(bill_id, start_date=start_date, end_date=end_date, **filters)
    delta_pct = comp.get("delta", {}).get("amount_pct", 0)
    if abs(delta_pct) >= 20 and comp.get("previous", {}).get("amount"):
        result.append(
            {
                "type": "环比异动",
                "level": "warn" if delta_pct > 0 else "good",
                "title": f"最近一月支出环比{'上升' if delta_pct > 0 else '下降'} {abs(delta_pct):.1f}%",
                "detail": f"{comp['previous']['month']} ¥{comp['previous']['amount']:.2f} → "
                f"{comp['current']['month']} ¥{comp['current']['amount']:.2f}",
                "value": delta_pct,
            }
        )

    income_total = float(df[df["direction"] == "收入"]["amount"].sum())
    if income_total > 0:
        rate = (income_total - float(expense["amount"].sum())) / income_total * 100
        result.append(
            {
                "type": "储蓄率",
                "level": "good" if rate >= 20 else "info",
                "title": f"储蓄率 {rate:.1f}%",
                "detail": "建议保持在 20% 以上；当前为收入扣除支出后的结余比例。",
                "value": round(rate, 2),
            }
        )
    return result


def year_report(
    bill_id: str, year=None, start_date: str = "", end_date: str = "", **filters
) -> dict:
    """年度报告：全年汇总、逐月收支、分类/商户/支付方式排行。"""
    from .repository import query_filter

    df = query_filter(bill_id, start_date=start_date, end_date=end_date, **filters)
    if df.empty:
        return {
            "year": str(year or ""),
            "available_years": [],
            "income_total": 0.0,
            "expense_total": 0.0,
            "net_total": 0.0,
            "savings_rate": 0.0,
            "months": [],
            "top_categories": [],
            "top_merchants": [],
            "pay_methods": [],
        }

    years = sorted({str(v)[:4] for v in df["trade_date"].dropna() if str(v)})
    target = str(year or (years[-1] if years else ""))
    part = df[df["trade_date"].astype(str).str.startswith(target)]
    expense = part[part["direction"] == "支出"]
    income = part[part["direction"] == "收入"]
    total_expense = float(expense["amount"].sum())
    total_income = float(income["amount"].sum())

    month_rows = []
    for month in range(1, 13):
        key = f"{target}-{month:02d}"
        part_month = part[part["trade_month"] == key]
        month_rows.append(
            {
                "month": f"{month:02d}",
                "month_key": key,
                "income": round(
                    float(
                        part_month[part_month["direction"] == "收入"]["amount"].sum()
                    ),
                    2,
                ),
                "expense": round(
                    float(
                        part_month[part_month["direction"] == "支出"]["amount"].sum()
                    ),
                    2,
                ),
                "count": int(len(part_month)),
            }
        )

    cat = (
        expense.groupby("category")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    top_categories = []
    for _, row in cat.head(8).iterrows():
        top_categories.append(
            {
                "category": row["category"],
                "amount": round(float(row["amount"]), 2),
                "count": int(row["count"]),
                "ratio": round(float(row["amount"]) / total_expense * 100, 2)
                if total_expense
                else 0.0,
            }
        )

    merchants = (
        expense.groupby("counterparty")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    top_merchants = merchants.head(8).to_dict(orient="records")
    for item in top_merchants:
        item["amount"] = round(float(item["amount"]), 2)
        item["count"] = int(item["count"])

    pay = (
        part.groupby("pay_method")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    pay_methods = [
        {
            "pay_method": row["pay_method"],
            "amount": round(float(row["amount"]), 2),
            "count": int(row["count"]),
        }
        for _, row in pay.iterrows()
    ]

    max_row = expense.nlargest(1, "amount")
    return {
        "year": target,
        "available_years": years,
        "income_total": round(total_income, 2),
        "expense_total": round(total_expense, 2),
        "net_total": round(total_income - total_expense, 2),
        "savings_rate": round((total_income - total_expense) / total_income * 100, 2)
        if total_income
        else 0.0,
        "income_count": int(len(income)),
        "expense_count": int(len(expense)),
        "active_days": int(expense["trade_date"].nunique()) if not expense.empty else 0,
        "avg_month_expense": round(
            total_expense
            / max(expense["trade_month"].nunique() if not expense.empty else 0, 1),
            2,
        ),
        "max_expense": round(float(max_row["amount"].iloc[0]), 2)
        if not max_row.empty
        else 0.0,
        "max_expense_date": str(max_row["trade_date"].iloc[0])
        if not max_row.empty
        else "",
        "max_expense_name": str(max_row["counterparty"].iloc[0])
        if not max_row.empty
        else "",
        "months": month_rows,
        "top_categories": top_categories,
        "top_merchants": top_merchants,
        "pay_methods": pay_methods,
    }


def merchant_profile(
    bill_id: str, name: str, start_date: str = "", end_date: str = "", **filters
) -> dict:
    """单个交易对方的消费画像。"""
    from .repository import query_filter

    text = str(name or "").strip()
    if not text:
        raise ValueError("请输入商户名称")
    df = query_filter(bill_id, start_date=start_date, end_date=end_date, **filters)
    if df.empty:
        raise ValueError("当前条件下无数据")
    matched = df[
        df["counterparty"].astype(str).str.contains(text, na=False, case=False)
    ]
    if matched.empty:
        raise ValueError(f"未找到交易对方：{text}")
    names = matched["counterparty"].value_counts()
    actual = str(names.index[0])
    part = matched[matched["counterparty"] == actual]
    expense = part[part["direction"] == "支出"]
    total = float(part["amount"].sum())
    count = int(len(part))
    first = str(part["trade_time"].min())
    last = str(part["trade_time"].max())

    by_month = (
        part.groupby("trade_month")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("trade_month")
    )
    by_hour = (
        part.groupby("trade_hour")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
    )
    by_category = (
        part.groupby("category")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    top_goods = (
        part.groupby("goods")
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
        .sort_values("amount", ascending=False)
        .head(8)
    )

    interval = 0.0
    times = (
        pd.to_datetime(part["trade_time"], errors="coerce")
        .dropna()
        .sort_values()
        .tolist()
    )
    if len(times) >= 2:
        gaps = [
            (times[i] - times[i - 1]).total_seconds() / 86400
            for i in range(1, len(times))
        ]
        interval = round(sum(gaps) / len(gaps), 2)

    return {
        "name": actual,
        "query": text,
        "count": count,
        "total": round(total, 2),
        "avg": round(total / count, 2) if count else 0.0,
        "max": round(float(part["amount"].max()), 2),
        "expense_total": round(float(expense["amount"].sum()), 2),
        "first": first,
        "last": last,
        "active_months": int(part["trade_month"].nunique()),
        "avg_interval_days": interval,
        "by_month": [
            {
                "month": row["trade_month"],
                "amount": round(float(row["amount"]), 2),
                "count": int(row["count"]),
            }
            for _, row in by_month.iterrows()
        ],
        "by_hour": [
            {
                "hour": int(row["trade_hour"]),
                "amount": round(float(row["amount"]), 2),
                "count": int(row["count"]),
            }
            for _, row in by_hour.iterrows()
        ],
        "by_category": [
            {
                "category": row["category"],
                "amount": round(float(row["amount"]), 2),
                "count": int(row["count"]),
            }
            for _, row in by_category.iterrows()
        ],
        "top_goods": [
            {
                "goods": row["goods"],
                "amount": round(float(row["amount"]), 2),
                "count": int(row["count"]),
            }
            for _, row in top_goods.iterrows()
        ],
    }


def category_trend(bill_id: str, top: int = 6, **filters) -> dict:
    """支出分类的逐月堆叠趋势。"""
    from .repository import query_filter

    filters.pop("direction", None)
    df = query_filter(bill_id, direction="支出", **filters)
    if df.empty:
        return {"months": [], "categories": [], "series": []}
    months = sorted(df["trade_month"].unique().tolist())
    totals = (
        df.groupby("category")["amount"].sum().sort_values(ascending=False).head(top)
    )
    categories = totals.index.tolist()
    series = []
    for name in categories:
        part = df[df["category"] == name]
        grouped = part.groupby("trade_month")["amount"].sum()
        series.append(
            {
                "category": name,
                "data": [round(float(grouped.get(m, 0)), 2) for m in months],
            }
        )
    return {"months": months, "categories": categories, "series": series}


def cumulative_expense(
    bill_id: str, start_date: str = "", end_date: str = "", **filters
) -> dict:
    """按日累计支出曲线，用于观察月度消费进度。"""
    from .repository import query_filter

    filters.pop("direction", None)
    df = query_filter(
        bill_id, direction="支出", start_date=start_date, end_date=end_date, **filters
    )
    if df.empty:
        return {"rows": [], "total": 0.0}
    daily = df.groupby("trade_date")["amount"].sum().sort_index()
    rows = []
    total = 0.0
    for day, amount in daily.items():
        total += float(amount)
        rows.append(
            {
                "date": str(day),
                "daily": round(float(amount), 2),
                "cumulative": round(total, 2),
            }
        )
    return {"rows": rows, "total": round(total, 2)}


BUDGET_FILE = "data/budgets.json"


def _load_budgets() -> dict:
    import json

    from .settings import abs_path

    path = abs_path(BUDGET_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_budget(bill_id: str, monthly: float = 0, categories: dict = None) -> dict:
    import json

    from .settings import abs_path, ensure_dir

    data = _load_budgets()
    data[bill_id] = {
        "monthly": round(float(monthly or 0), 2),
        "categories": {
            str(k): round(float(v), 2) for k, v in (categories or {}).items()
        },
    }
    path = abs_path(BUDGET_FILE)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data[bill_id]


def budget_status(
    bill_id: str, start_date: str = "", end_date: str = "", **filters
) -> dict:
    from .repository import query_filter

    budgets = _load_budgets().get(bill_id, {})
    monthly = float(budgets.get("monthly") or 0)
    df = query_filter(bill_id, start_date=start_date, end_date=end_date, **filters)
    expense = df[df["direction"] == "支出"]
    current_month = ""
    if not expense.empty:
        current_month = sorted(expense["trade_month"].unique().tolist())[-1]
        expense = expense[expense["trade_month"] == current_month]
    used = round(float(expense["amount"].sum()), 2)
    percent = round(used / monthly * 100, 2) if monthly > 0 else 0.0
    cat_used = expense.groupby("category")["amount"].sum().round(2).to_dict()
    cat_budget = budgets.get("categories", {})
    cat_status = [
        {
            "category": name,
            "budget": float(value),
            "used": round(float(cat_used.get(name, 0)), 2),
            "percent": round(float(cat_used.get(name, 0)) / float(value) * 100, 2)
            if float(value) > 0
            else 0.0,
        }
        for name, value in cat_budget.items()
    ]
    return {
        "month": current_month,
        "monthly": round(monthly, 2),
        "used": used,
        "remaining": round(monthly - used, 2) if monthly > 0 else 0.0,
        "percent": percent,
        "over": monthly > 0 and used > monthly,
        "categories": cat_status,
    }


def nl_query(bill_id: str, question: str, **filters) -> dict:
    """极简自然语言查询：识别时间/收支部位/分类/商户/金额条件。"""
    import re

    from .repository import query_filter

    text = str(question or "").strip()
    if not text:
        raise ValueError("请输入查询内容")

    dataset = repository.get(bill_id)
    all_df = dataset.df
    kwargs = dict(filters)
    kwargs.pop("direction", None)
    kwargs.pop("category", None)
    kwargs.pop("keyword", None)
    kwargs.pop("min_amount", None)
    kwargs.pop("max_amount", None)

    start = end = ""
    months = sorted(all_df["trade_month"].unique().tolist()) if not all_df.empty else []

    def _month_range(month_key):
        from calendar import monthrange

        year, month = (int(x) for x in str(month_key).split("-")[:2])
        last_day = monthrange(year, month)[1]
        return f"{month_key}-01", f"{month_key}-{last_day:02d}"

    if any(w in text for w in ("上月", "上个月")):
        if months:
            m = months[-2] if len(months) >= 2 else months[-1]
            start, end = _month_range(m)
    elif any(w in text for w in ("本月", "这个月", "当月")):
        if months:
            start, end = _month_range(months[-1])
    elif "今年" in text:
        year = str(months[-1])[:4] if months else ""
        if year:
            start, end = f"{year}-01-01", f"{year}-12-31"
    elif "去年" in text:
        if months:
            year = int(str(months[-1])[:4]) - 1
            start, end = f"{year}-01-01", f"{year}-12-31"

    direction = "收入" if "收入" in text else "支出"

    stop_words = {
        "支出",
        "收入",
        "本月",
        "上月",
        "上个月",
        "这个月",
        "当月",
        "今年",
        "去年",
        "一共",
        "多少",
        "花了",
        "查询",
        "统计",
        "大于",
        "小于",
        "超过",
        "低于",
        "不超过",
        "至少",
        "记录",
        "明细",
        "合计",
        "总额",
        "看看",
    }

    def _fragments(text_value, limit=6):
        seen = []
        for n in range(min(limit, len(text_value)), 1, -1):
            for i in range(0, len(text_value) - n + 1):
                sub = text_value[i : i + n]
                if sub in stop_words:
                    continue
                if all("\u4e00" <= ch <= "\u9fa5" for ch in sub):
                    seen.append(sub)
        return sorted(set(seen), key=len, reverse=True)

    fragments = _fragments(text)

    category = ""
    for name in billing_conf_categories() or {}:
        if not name:
            continue
        if name in text:
            category = name
            break
        if any(frag in name for frag in fragments):
            category = name
            break

    min_amount = max_amount = None
    m = re.search(r"(?:大于|超过|高于|至少)\s*(\d+(?:\.\d+)?)", text)
    if m:
        min_amount = float(m.group(1))
    m = re.search(r"(?:小于|低于|不超过)\s*(\d+(?:\.\d+)?)", text)
    if m:
        max_amount = float(m.group(1))

    keyword = ""
    best_len = 0
    for name in all_df["counterparty"].dropna().unique().tolist():
        name = str(name).strip()
        if len(name) < 2:
            continue
        if name in text and len(name) > best_len:
            keyword, best_len = name, len(name)
            continue
        for frag in fragments:
            if frag in name and len(frag) > best_len:
                keyword, best_len = frag, len(frag)
                break

    df = query_filter(
        bill_id,
        start_date=start,
        end_date=end,
        direction=direction,
        category=category,
        keyword=keyword,
        min_amount=min_amount,
        max_amount=max_amount,
        **kwargs,
    )
    cols = ["trade_time", "direction", "amount", "category", "counterparty", "goods"]
    return {
        "question": text,
        "answer": f"共 {len(df)} 笔，合计 ¥{float(df['amount'].sum()):.2f}",
        "parsed": {
            "start_date": start,
            "end_date": end,
            "direction": direction,
            "category": category,
            "keyword": keyword,
            "min_amount": min_amount,
            "max_amount": max_amount,
        },
        "total": round(float(df["amount"].sum()), 2),
        "count": int(len(df)),
        "rows": df.sort_values("trade_time", ascending=False)
        .head(20)[cols]
        .to_dict(orient="records"),
    }


def billing_conf_categories() -> dict:
    from .settings import billing_conf

    return billing_conf("categories", {}) or {}


def full_report(
    bill_id: str, start_date: str = "", end_date: str = "", **filters
) -> dict:
    dataset = repository.get(bill_id)
    return {
        "bill_id": bill_id,
        "channel": dataset.channel,
        "source_file": dataset.source_file,
        "overview": overview(bill_id, start_date, end_date, **filters),
        "monthly_trend": trend(bill_id, "month", start_date, end_date, **filters),
        "daily_trend": trend(bill_id, "day", start_date, end_date, **filters),
        "category_stats": category_stats(
            bill_id, start_date, end_date, "支出", **filters
        ),
        "income_category_stats": category_stats(
            bill_id, start_date, end_date, "收入", **filters
        ),
        "counterparty_top": counterparty_stats(
            bill_id, "支出", 20, start_date, end_date, **filters
        ),
        "weekday_stats": weekday_stats(bill_id, start_date, end_date, **filters),
        "hour_stats": hour_stats(bill_id, start_date, end_date, **filters),
        "top_expenses": top_transactions(
            bill_id, 20, "支出", start_date, end_date, **filters
        ),
        "heatmap": heatmap_week_hour(bill_id, start_date, end_date, **filters),
        "comparison": comparison(bill_id, start_date, end_date, **filters),
        "insights": insights(bill_id, start_date, end_date, **filters),
        "budget": budget_status(bill_id, start_date, end_date, **filters),
        "calendar": calendar_daily(bill_id, *list(_default_month(dataset)), **filters),
        "available_months": available_months(bill_id),
        "categories": classifier.available_categories(dataset.df),
    }


def _default_month(dataset) -> tuple:
    """推断默认日历月份：取账单最后一条记录所在的月。"""
    if dataset.df is None or dataset.df.empty:
        from datetime import datetime as _dt

        now = _dt.now()
        return (now.year, now.month)
    ts = pd.to_datetime(dataset.df["trade_time"], errors="coerce").dropna()
    if ts.empty:
        from datetime import datetime as _dt

        now = _dt.now()
        return (now.year, now.month)
    last = ts.max()
    return (last.year, last.month)
