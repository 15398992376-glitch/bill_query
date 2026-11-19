import io
import os
from datetime import datetime

import pandas as pd

EXPORT_COLUMNS = {
    "trade_time": "交易时间",
    "trade_date": "日期",
    "trade_month": "月份",
    "direction": "收/支",
    "amount": "金额",
    "category": "分类",
    "counterparty": "交易对方",
    "goods": "商品说明",
    "trade_type": "交易类型",
    "pay_method": "支付方式",
    "status": "状态",
    "trade_no": "交易单号",
    "remark": "备注",
    "channel": "数据渠道",
    "is_transfer": "转账/退款标记",
}


def to_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=EXPORT_COLUMNS.values())
    cols = [c for c in EXPORT_COLUMNS if c in df.columns]
    out = df[cols].copy()
    return out.rename(columns={c: EXPORT_COLUMNS[c] for c in cols})


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    frame = to_dataframe(df)
    return frame.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def to_excel_bytes(df: pd.DataFrame, analytics: dict = None) -> bytes:
    frame = to_dataframe(df)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        sheet_name = "账单明细"
        frame.to_excel(writer, index=False, sheet_name=sheet_name)
        if analytics:
            overview = analytics.get("overview", {})
            summary_rows = [
                {"指标": "记录条数", "数值": overview.get("record_count")},
                {
                    "指标": "时间范围",
                    "数值": f"{overview.get('start_date', '')} ~ {overview.get('end_date', '')}",
                },
                {"指标": "收入合计", "数值": overview.get("income_total")},
                {"指标": "支出合计", "数值": overview.get("expense_total")},
                {"指标": "净收支", "数值": overview.get("net_total")},
                {"指标": "日均支出", "数值": overview.get("avg_daily_expense")},
                {"指标": "笔均支出", "数值": overview.get("avg_ticket")},
                {"指标": "最大单笔支出", "数值": overview.get("max_expense")},
            ]
            pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="汇总")
            for key, sheet in (
                ("monthly_trend", "月度趋势"),
                ("category_stats", "支出分类"),
                ("income_category_stats", "收入分类"),
                ("counterparty_top", "交易对方TOP"),
                ("weekday_stats", "星期分布"),
                ("hour_stats", "时段分布"),
                ("top_expenses", "大额支出"),
                ("insights", "消费洞察"),
            ):
                data = analytics.get(key) or []
                if data:
                    pd.DataFrame(data).to_excel(writer, index=False, sheet_name=sheet)

            heatmap = analytics.get("heatmap") or {}
            if heatmap.get("matrix"):
                rows = []
                for idx, name in enumerate(heatmap.get("weekdays", [])):
                    row = {"星期": name}
                    for hour, value in enumerate(heatmap["matrix"][idx]):
                        row[f"{hour}时"] = value
                    rows.append(row)
                pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="7x24热力")

            comp = analytics.get("comparison") or {}
            if comp.get("categories"):
                pd.DataFrame(comp["categories"]).to_excel(
                    writer, index=False, sheet_name="环比对比"
                )
    return buffer.getvalue()


def export_file(
    df: pd.DataFrame, export_dir: str, fmt: str = "xlsx", analytics: dict = None
) -> str:
    os.makedirs(export_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "csv":
        path = os.path.join(export_dir, f"账单明细_{stamp}.csv")
        with open(path, "wb") as f:
            f.write(to_csv_bytes(df))
        return path
    path = os.path.join(export_dir, f"账单报告_{stamp}.xlsx")
    with open(path, "wb") as f:
        f.write(to_excel_bytes(df, analytics))
    return path
