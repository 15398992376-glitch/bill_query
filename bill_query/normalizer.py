import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pandas as pd

from .settings import billing_conf, get_logger

logger = get_logger("bill.normalizer")

COLUMN_ALIASES = {
    "trade_time": [
        "交易时间",
        "交易日期",
        "记账日期",
        "入账日期",
        "发生时间",
        "发生日期",
        "交易创建时间",
        "付款时间",
        "创建时间",
        "时间",
        "日期",
        "trade_time",
        "trade_date",
        "transaction_time",
        "date",
    ],
    "trade_type": [
        "交易类型",
        "业务类型",
        "摘要",
        "交易摘要",
        "trade_type",
        "type",
        "摘要说明",
    ],
    "counterparty": [
        "交易对方",
        "对方户名",
        "对方账号",
        "对手方",
        "商户名称",
        "商户",
        "收款方",
        "付款方",
        "counterparty",
        "merchant",
        "对方账户名称",
    ],
    "goods": [
        "商品",
        "商品说明",
        "商品名称",
        "摘要详情",
        "goods",
        "description",
        "用途",
    ],
    "direction": [
        "收/支",
        "收支",
        "收付标志",
        "借贷标志",
        "收入/支出",
        "方向",
        "direction",
    ],
    "amount": [
        "金额(元)",
        "金额（元）",
        "金额",
        "交易金额",
        "发生额",
        "amount",
        "money",
    ],
    "pay_method": [
        "支付方式",
        "付款方式",
        "交易方式",
        "渠道",
        "pay_method",
        "payment_method",
    ],
    "status": [
        "当前状态",
        "交易状态",
        "状态",
        "status",
    ],
    "trade_no": [
        "交易单号",
        "交易号",
        "支付宝交易号",
        "交易流水号",
        "流水号",
        "订单号",
        "凭证号",
        "trade_no",
        "transaction_no",
        "serial_no",
    ],
    "merchant_no": ["商户单号", "商家订单号", "merchant_no", "外部订单号"],
    "remark": ["备注", "附言", "remark", "memo"],
    "category": ["分类", "消费分类", "category"],
    "account": ["账户", "卡号", "账号", "本方账号", "account"],
}

REQUIRED_FOR_PARSE = ("trade_time", "amount")

WEIXIN_HINT = ("微信支付账单明细", "微信支付", "零钱", "收/支")

ALIPAY_HINT = ("支付宝交易记录", "支付宝", "商家订单号", "支付宝交易号")

BANK_HINT = ("银行", "账户", "户名", "借方", "贷方", "摘要", "发生额", "余额")


@dataclass
class ParseResult:
    df: pd.DataFrame
    channel: str = ""
    source_file: str = ""
    header_row: int = -1
    skipped_rows: int = 0
    warnings: list = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return 0 if self.df is None else len(self.df)


def _read_csv_rows(file_path: str) -> list:
    last_error = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "utf-16"):
        try:
            with open(file_path, "r", encoding=enc, newline="") as f:
                rows = [[cell.strip() for cell in row] for row in csv.reader(f)]
            return rows
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
    raise ValueError(f"无法识别 CSV 编码，请另存为 UTF-8 或 GBK: {last_error}")


def _read_raw_table(file_path: str, max_scan_rows: int = 40) -> pd.DataFrame:
    lower = file_path.lower()
    if lower.endswith(".csv"):
        rows = _read_csv_rows(file_path)
        width = max((len(r) for r in rows), default=0)
        padded = [r + [""] * (width - len(r)) for r in rows]
        return pd.DataFrame(padded, dtype=str)
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        frame = pd.read_excel(file_path, header=None, dtype=str)
        return frame.fillna("")
    raise ValueError("仅支持 .csv / .xlsx / .xls 文件")


def _score_header(cells) -> int:
    normalized = {str(c).strip() for c in cells if str(c).strip() and str(c) != "nan"}
    if not normalized:
        return 0
    score = 0
    for aliases in COLUMN_ALIASES.values():
        for alias in aliases:
            if any(alias == cell or alias in cell for cell in normalized):
                score += 1
                break
    return score


def _detect_header_row(raw: pd.DataFrame, max_scan_rows: int = 40) -> int:
    limit = min(len(raw), max_scan_rows)
    best_row, best_score = -1, 0
    for idx in range(limit):
        score = _score_header(raw.iloc[idx].tolist())
        if score > best_score:
            best_row, best_score = idx, score
    if best_score < 3:
        return -1
    return best_row


def _map_columns(columns) -> dict:
    mapping = {}
    used = set()
    for idx, col in enumerate(columns):
        name = str(col).strip()
        if not name or name == "nan":
            continue
        for field_name, aliases in COLUMN_ALIASES.items():
            if field_name in used:
                continue
            for alias in aliases:
                if name == alias or alias in name or name in alias and len(name) >= 2:
                    mapping[idx] = field_name
                    used.add(field_name)
                    break
    return mapping


def _detect_channel(raw: pd.DataFrame, header_row: int) -> str:
    scan_end = min(len(raw), header_row + 30 if header_row >= 0 else 30)
    text = " ".join(
        str(v) for v in raw.iloc[0:scan_end].values.ravel() if str(v) != "nan"
    )
    header_text = (
        " ".join(str(c) for c in raw.iloc[header_row].tolist() if str(c) != "nan")
        if header_row >= 0
        else ""
    )
    joined = text + " " + header_text
    if any(h in joined for h in ALIPAY_HINT):
        return "支付宝"
    if any(h in joined for h in WEIXIN_HINT):
        return "微信支付"
    if any(h in joined for h in BANK_HINT):
        return "银行"
    return "通用"


def _to_amount(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "--"}:
        return None
    text = text.replace("¥", "").replace("￥", "").replace(",", "").replace(" ", "")
    text = text.replace("元", "")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    if text.startswith("-"):
        negative = True
        text = text[1:]
    try:
        val = float(text)
    except ValueError:
        return None
    return -val if negative else val


def _to_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    if isinstance(value, (datetime, date)):
        return datetime(value.year, value.month, value.day)
    text = re.sub(r"[年月]", "-", text).replace("日", "").replace("/", "-")
    text = text.replace(".", "-").strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d",
        "%Y%m%d%H%M%S",
        "%d-%m-%Y %H:%M:%S",
        "%H:%M:%S %Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime().replace(tzinfo=None)
    except Exception:
        return None


def normalize_direction(
    raw_direction, amount: float, trade_type: str, goods: str
) -> str:
    text = str(raw_direction or "").strip()
    if "/" in text:
        text = text.split("/")[0].strip()
    if "支" in text or "借" in text or "付" in text:
        return "支出"
    if "收" in text or "贷" in text:
        return "收入"
    if "不计" in text or "中性" in text:
        return "不计收支"
    if amount is not None:
        if amount < 0:
            return "支出"
        combined = f"{trade_type} {goods}"
        for kw in billing_conf("income_keywords", []):
            if kw and kw in combined:
                return "收入"
    return "支出"


def _row_to_record(raw_row, mapping, channel):
    record = {}
    for idx, field_name in mapping.items():
        if idx < len(raw_row):
            record[field_name] = raw_row[idx]
    amount = _to_amount(record.get("amount"))
    trade_time = _to_datetime(record.get("trade_time"))
    if amount is None or trade_time is None:
        return None
    direction = normalize_direction(
        record.get("direction"), amount, record.get("trade_type"), record.get("goods")
    )
    return {
        "trade_time": trade_time.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": trade_time.strftime("%Y-%m-%d"),
        "trade_month": trade_time.strftime("%Y-%m"),
        "trade_hour": trade_time.hour,
        "trade_weekday": trade_time.isoweekday(),
        "trade_type": str(record.get("trade_type") or "").strip(),
        "counterparty": str(record.get("counterparty") or "").strip(),
        "goods": str(record.get("goods") or "").strip(),
        "direction": direction,
        "amount": round(abs(amount), 2),
        "signed_amount": round(abs(amount) if direction == "收入" else -abs(amount), 2),
        "channel": channel,
        "pay_method": str(record.get("pay_method") or "").strip(),
        "status": str(record.get("status") or "").strip(),
        "trade_no": str(record.get("trade_no") or "").strip(),
        "merchant_no": str(record.get("merchant_no") or "").strip(),
        "remark": str(record.get("remark") or "").strip(),
        "account": str(record.get("account") or "").strip(),
        "raw_category": str(record.get("category") or "").strip(),
    }


def parse_bill(file_path: str, source_name: str = None) -> ParseResult:
    raw = _read_raw_table(file_path)
    if raw is None or raw.empty:
        raise ValueError("文件内容为空，无法解析")

    header_row = _detect_header_row(raw)
    channel = _detect_channel(raw, header_row)
    result = ParseResult(
        df=pd.DataFrame(),
        channel=channel,
        source_file=source_name or file_path,
        header_row=header_row,
    )

    if header_row < 0:
        result.warnings.append("未能识别表头，尝试按位置解析")
        header_row = 0

    header = raw.iloc[header_row].tolist()
    mapping = _map_columns(header)
    missing = [f for f in REQUIRED_FOR_PARSE if f not in mapping.values()]
    if missing:
        raise ValueError(
            f"无法识别必要列（缺少: {', '.join(missing)}），已识别列: {list(mapping.values())}"
        )

    records = []
    for idx in range(header_row + 1, len(raw)):
        row = raw.iloc[idx].tolist()
        if all(str(v) in ("nan", "", "None") for v in row):
            continue
        try:
            rec = _row_to_record(row, mapping, channel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("第 %s 行解析失败: %s", idx + 1, exc)
            result.skipped_rows += 1
            continue
        if rec is None:
            if str(row[0] if row else "").strip() and "---" not in str(row[0]):
                result.skipped_rows += 1
            continue
        records.append(rec)

    if not records:
        raise ValueError("未解析出任何有效账单记录，请检查文件格式")

    df = pd.DataFrame(records)
    df = df.drop_duplicates(
        subset=["trade_time", "amount", "direction", "counterparty", "trade_no"]
    )
    df = df.sort_values("trade_time").reset_index(drop=True)
    result.df = df
    logger.info(
        "解析完成: %s 条记录, 渠道=%s, 跳过=%s", len(df), channel, result.skipped_rows
    )
    return result
