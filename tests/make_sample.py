import os
import random
from datetime import datetime, timedelta

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(BASE_DIR, "data", "sample")

MERCHANTS = [
    ("美团外卖", "餐饮美食", 28, 88),
    ("星巴克咖啡", "餐饮美食", 25, 60),
    ("滴滴出行", "交通出行", 12, 80),
    ("深圳地铁", "交通出行", 3, 12),
    ("永辉超市", "日用百货", 50, 400),
    ("京东商城", "日用百货", 80, 1200),
    ("中国移动话费", "通讯数码", 50, 200),
    ("万科物业", "住房物业", 300, 800),
    ("人人乐药房", "医疗健康", 20, 150),
    ("万达影城", "文教娱乐", 40, 120),
    ("中国石化加油站", "交通出行", 200, 500),
    ("优衣库", "服饰鞋包", 199, 899),
]

INCOMERS = [
    ("张三", "转账-来自张三", 100, 800),
    ("李四", "收钱码收款", 50, 500),
    ("公司工资", "代发工资", 8000, 15000),
    ("王五", "红包-收到", 5, 200),
]


def build_weixin_rows(days: int = 90, seed: int = 42) -> list:
    random.seed(seed)
    rows = []
    start = datetime.now() - timedelta(days=days)
    for i in range(days):
        day = start + timedelta(days=i)
        for _ in range(random.randint(1, 5)):
            merchant, category, low, high = random.choice(MERCHANTS)
            ts = day.replace(
                hour=random.randint(7, 22),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
            )
            amount = round(random.uniform(low, high), 2)
            rows.append(
                [
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "商户消费",
                    merchant,
                    merchant + "订单",
                    "支出",
                    f"¥{amount:.2f}",
                    "零钱",
                    "支付成功",
                    f"42000{i:04d}{random.randint(1000, 9999)}",
                    f"M2026{i:04d}{random.randint(1000, 9999)}",
                    "",
                ]
            )
        if random.random() < 0.35:
            name, desc, low, high = random.choice(INCOMERS)
            ts = day.replace(
                hour=random.randint(8, 21),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
            )
            amount = round(random.uniform(low, high), 2)
            rows.append(
                [
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "转账" if "转账" in desc else "其他",
                    name,
                    desc,
                    "收入",
                    f"¥{amount:.2f}",
                    "零钱",
                    "已存入零钱",
                    f"10000{i:04d}{random.randint(1000, 9999)}",
                    "",
                    "",
                ]
            )
    rows.sort(key=lambda r: r[0])
    return rows


def write_weixin_csv(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header_title = ["微信支付账单明细", "", "", "", "", "", "", "", "", "", ""]
    meta = [
        ["微信昵称：[示例用户]", "", "", "", "", "", "", "", "", "", ""],
        [
            "起始时间：[2026-01-01 00:00:00] 终止时间：[2026-04-01 00:00:00]",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        ["导出时间：[2026-04-01 10:00:00]", "", "", "", "", "", "", "", "", "", ""],
    ]
    columns = [
        "交易时间",
        "交易类型",
        "交易对方",
        "商品",
        "收/支",
        "金额(元)",
        "支付方式",
        "当前状态",
        "交易单号",
        "商户单号",
        "备注",
    ]
    rows = build_weixin_rows()
    lines = []
    for item in header_title + meta:
        lines.append(",".join(item))
    lines.append(",".join(columns))
    for row in rows:
        lines.append(",".join([f'"{v}"' if "," in str(v) else str(v) for v in row]))
    lines.append("")
    lines.append("----------------------微信支付账单明细列表--------------------")
    lines.append(f"共{len(rows)}笔记录")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("\n".join(lines))
    return path


BANK_COLUMNS = ["交易日期", "摘要", "对方户名", "发生额", "余额", "借贷标志", "流水号"]
BANK_ABSTRACT = [
    ("消费", "华润万家超市", -156.80),
    ("消费", "顺丰速运", -23.00),
    ("转账", "陈小明", -2000.00),
    ("代发工资", "某某科技有限公司", 12500.00),
    ("消费", "国家电网电费", -320.45),
    ("转账", "李华", 800.00),
    ("消费", "肯德基", -68.50),
    ("消费", "shell加油站", -400.00),
]


def write_bank_xlsx(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    random.seed(7)
    start = datetime.now() - timedelta(days=60)
    balance = 50000.0
    records = []
    for i in range(60):
        day = start + timedelta(days=i)
        if random.random() < 0.6:
            summary, party, delta = random.choice(BANK_ABSTRACT)
            ts = day.replace(hour=random.randint(8, 20), minute=random.randint(0, 59))
            balance = round(balance + delta, 2)
            records.append(
                [
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    summary,
                    party,
                    delta,
                    balance,
                    "贷" if delta > 0 else "借",
                    f"SN{2026000000 + i}",
                ]
            )
    frame = pd.DataFrame(records, columns=BANK_COLUMNS)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            [["银行账户交易明细"], ["户名：示例用户", "账号：6222 **** 8888"]]
        ).to_excel(writer, index=False, header=False, sheet_name="明细")
        frame.to_excel(writer, index=False, startrow=2, sheet_name="明细")
    return path


if __name__ == "__main__":
    weixin_path = write_weixin_csv(os.path.join(SAMPLE_DIR, "wx_sample.csv"))
    bank_path = write_bank_xlsx(os.path.join(SAMPLE_DIR, "bank_sample.xlsx"))
    print("生成示例账单：")
    print(" -", weixin_path)
    print(" -", bank_path)
