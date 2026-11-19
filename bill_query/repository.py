import os
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from . import annotations, classifier, store
from .normalizer import parse_bill
from .settings import app_conf, abs_path, billing_conf, ensure_dir, get_logger

logger = get_logger("bill.repository")

TABLE_EXT = (".csv", ".xlsx", ".xls", ".xlsm")
ALLOWED_EXT = TABLE_EXT + (".zip",)


@dataclass
class BillDataset:
    bill_id: str
    source_file: str
    channel: str
    df: pd.DataFrame
    warnings: list = field(default_factory=list)

    def summary(self) -> dict:
        df = self.df
        income = df[df["direction"] == "收入"]
        expense = df[df["direction"] == "支出"]
        dates = pd.to_datetime(df["trade_time"], errors="coerce").dropna()
        return {
            "bill_id": self.bill_id,
            "source_file": self.source_file,
            "channel": self.channel,
            "record_count": int(len(df)),
            "income_total": round(float(income["amount"].sum()), 2),
            "expense_total": round(float(expense["amount"].sum()), 2),
            "net_total": round(
                float(income["amount"].sum() - expense["amount"].sum()), 2
            ),
            "income_count": int(len(income)),
            "expense_count": int(len(expense)),
            "start_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
            "end_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
            "warnings": self.warnings,
        }


def dedupe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """跨文件合并去重：优先交易号，缺交易号时用时间+金额+方向+对方。"""
    if frame is None or frame.empty:
        return frame
    trade_no = frame["trade_no"].astype(str).str.strip() if "trade_no" in frame else ""
    keys = []
    for idx, row in frame.iterrows():
        no = str(row.get("trade_no") or "").strip()
        if no and no.lower() not in ("nan", "none"):
            keys.append("no:" + no)
        else:
            keys.append(
                "mix:"
                + "|".join(
                    str(row.get(k) or "")
                    for k in ("trade_time", "amount", "direction", "counterparty")
                )
            )
    frame = frame.copy()
    frame["_dedupe_key"] = keys
    frame = frame.drop_duplicates(subset=["_dedupe_key"]).drop(columns=["_dedupe_key"])
    return frame.reset_index(drop=True)


def expand_archive(
    zip_path: str, target_dir: str, password: Optional[str] = None
) -> list:
    """解压 zip 账单包，返回其中的表格文件路径列表。"""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("压缩包格式无效或已损坏")
    ensure_dir(target_dir)
    results = []
    pwd = password.encode("utf-8") if password else None
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = os.path.basename(info.filename)
            if not name.lower().endswith(TABLE_EXT):
                continue
            try:
                with zf.open(info, pwd=pwd) as src:
                    data = src.read()
            except RuntimeError as exc:
                raise ValueError(
                    "压缩包已加密，请填写解压密码（微信账单为6位数字）"
                ) from exc
            out = os.path.join(target_dir, f"{uuid.uuid4().hex[:8]}_{name}")
            with open(out, "wb") as f:
                f.write(data)
            results.append(out)
    if not results:
        raise ValueError("压缩包内未找到 csv/xlsx 账单文件")
    return results


class BillRepository:
    """基于 pickle 的轻量数据集仓库，支持内存缓存与落盘持久化。"""

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = ensure_dir(storage_dir or abs_path("data", "bills"))
        self._cache = {}

    def _path(self, bill_id: str) -> str:
        return os.path.join(self.storage_dir, f"{bill_id}.pkl")

    def save(self, file_path: str, source_name: str) -> BillDataset:
        return self.save_many([(file_path, source_name)])

    def save_many(self, items: list) -> BillDataset:
        """解析并合并多个账单文件，统一去重后保存为一个数据集。"""
        frames = []
        channels = []
        warnings = []
        names = []
        for file_path, source_name in items:
            result = parse_bill(file_path, source_name=source_name)
            frames.append(result.df)
            channels.append(result.channel)
            warnings.extend(result.warnings)
            names.append(source_name)
        frame = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        frame = dedupe_frame(frame)
        frame = classifier.classify_frame(frame)
        unique_channels = sorted({c for c in channels if c})
        channel = (
            unique_channels[0]
            if len(unique_channels) == 1
            else "多来源合并"
            if unique_channels
            else ""
        )
        bill_id = uuid.uuid4().hex[:12]
        dataset = BillDataset(
            bill_id=bill_id,
            source_file="、".join(names),
            channel=channel,
            df=frame,
            warnings=warnings,
        )
        dataset.df.to_pickle(self._path(bill_id))
        self._cache[bill_id] = dataset
        store.index_dataset(dataset)
        logger.info(
            "账单已保存: %s (%s 条, %s 个文件)", bill_id, len(frame), len(items)
        )
        return dataset

    def get(self, bill_id: str) -> BillDataset:
        if not bill_id:
            raise KeyError("未指定账单ID")
        if bill_id in self._cache:
            return self._cache[bill_id]
        path = self._path(bill_id)
        if not os.path.exists(path):
            raise KeyError(f"账单不存在或已过期: {bill_id}")
        frame = pd.read_pickle(path)
        dataset = BillDataset(
            bill_id=bill_id,
            source_file="",
            channel=frame["channel"].iloc[0]
            if "channel" in frame and not frame.empty
            else "",
            df=frame,
        )
        self._cache[bill_id] = dataset
        return dataset

    def list_all(self) -> list:
        items = []
        if not os.path.isdir(self.storage_dir):
            return items
        for name in sorted(os.listdir(self.storage_dir)):
            if not name.endswith(".pkl"):
                continue
            bill_id = name[:-4]
            try:
                dataset = self.get(bill_id)
                items.append(
                    {
                        "bill_id": bill_id,
                        "record_count": int(len(dataset.df)),
                        "channel": dataset.channel,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取账单 %s 失败: %s", bill_id, exc)
        return items

    def delete(self, bill_id: str) -> bool:
        path = self._path(bill_id)
        self._cache.pop(bill_id, None)
        store.remove_bill(bill_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def validate_upload(self, filename: str, size_bytes: int) -> None:
        lower = (filename or "").lower()
        if not lower.endswith(ALLOWED_EXT):
            raise ValueError(f"不支持的文件类型，仅支持 {'/'.join(ALLOWED_EXT)}")
        limit = int(app_conf("max_upload_mb", 50)) * 1024 * 1024
        if size_bytes > limit:
            raise ValueError(f"文件超过大小限制 {app_conf('max_upload_mb', 50)}MB")


repository = BillRepository()


def query_filter(
    bill_id: str,
    start_date: str = "",
    end_date: str = "",
    direction: str = "",
    category: str = "",
    keyword: str = "",
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    weekday: Optional[int] = None,
    exclude_transfer: bool = False,
    exclude_ignored: bool = False,
) -> pd.DataFrame:
    dataset = repository.get(bill_id)
    df = dataset.df.copy()
    if str(exclude_ignored).lower() not in ("", "0", "false", "none"):
        df = annotations.apply_ignored(bill_id, df)
    if start_date:
        df = df[df["trade_date"] >= start_date]
    if end_date:
        df = df[df["trade_date"] <= end_date]
    if direction:
        df = df[df["direction"] == direction]
    if category:
        df = df[df["category"] == category]
    if weekday not in (None, ""):
        try:
            df = df[df["trade_weekday"] == int(weekday)]
        except (TypeError, ValueError):
            pass
    if (
        str(exclude_transfer).lower() not in ("", "0", "false", "none")
        and "is_transfer" in df
    ):
        df = df[~df["is_transfer"].astype(bool)]
    if keyword:
        pattern = str(keyword).strip()
        mask = (
            df["counterparty"].str.contains(pattern, na=False, case=False)
            | df["goods"].str.contains(pattern, na=False, case=False)
            | df["trade_type"].str.contains(pattern, na=False, case=False)
            | df["remark"].str.contains(pattern, na=False, case=False)
            | df["trade_no"].str.contains(pattern, na=False, case=False)
        )
        df = df[mask]
    if min_amount is not None:
        df = df[df["amount"] >= float(min_amount)]
    if max_amount is not None:
        df = df[df["amount"] <= float(max_amount)]
    return df.reset_index(drop=True)


def currency() -> str:
    return billing_conf("currency", "CNY")
