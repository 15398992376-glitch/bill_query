"""生成一份更贴近真实的假账单并直接上传到本地服务，输出完整分析效果。"""

import json
import os
import random
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "sample")
BASE_URL = "http://127.0.0.1:5105"

# (商户, 商品说明模板, 交易类型, 金额区间, 权重, 时段偏好)
MERCHANTS = [
    ("美团外卖", "美团外卖订单", "商户消费", (22, 78), 16, "meal"),
    ("饿了么", "饿了么订单", "商户消费", (20, 65), 9, "meal"),
    ("星巴克咖啡", "星巴克门店消费", "商户消费", (28, 58), 5, "morning"),
    ("瑞幸咖啡", "luckin coffee", "商户消费", (9, 32), 8, "morning"),
    ("肯德基", "KFC门店消费", "商户消费", (25, 70), 4, "meal"),
    ("海底捞火锅", "海底捞餐饮", "商户消费", (120, 380), 1, "dinner"),
    ("深圳地铁", "地铁乘车码", "商户消费", (2, 12), 22, "commute"),
    ("滴滴出行", "滴滴快车", "商户消费", (11, 68), 10, "evening"),
    ("哈啰单车", "共享单车骑行", "商户消费", (1.5, 6), 7, "commute"),
    ("中国石化", "加油消费", "商户消费", (220, 480), 2, "any"),
    ("永辉超市", "永辉超市购物", "商户消费", (45, 380), 5, "evening"),
    ("京东商城", "京东自营订单", "商户消费", (89, 880), 3, "evening"),
    ("淘宝", "淘宝购物", "商户消费", (35, 460), 6, "evening"),
    ("拼多多", "拼多多订单", "商户消费", (9, 120), 4, "evening"),
    ("优衣库", "优衣库门店", "商户消费", (199, 799), 1, "weekend"),
    ("万科物业", "物业费缴纳", "商户消费", (280, 460), 1, "weekend"),
    ("中国移动", "话费充值", "商户消费", (50, 200), 1, "any"),
    ("南方电网", "电费缴纳", "商户消费", (120, 380), 1, "weekend"),
    ("人人乐药房", "药店购药", "商户消费", (18, 168), 2, "any"),
    ("万达影城", "电影票购买", "商户消费", (42, 128), 1, "weekend"),
    ("哔哩哔哩", "大会员续费", "商户消费", (15, 25), 1, "any"),
    ("网易云音乐", "黑胶VIP", "商户消费", (12, 18), 1, "any"),
    ("Shell加油站", "Shell加油", "商户消费", (260, 520), 1, "any"),
]

INCOMES = [
    ("张三", "转账-来自张三", "转账", (100, 600), 8),
    ("李四", "转账-来自李四", "转账", (50, 300), 5),
    ("某科技有限公司", "代发工资", "其他", (12000, 15800), 1),
    ("王五", "红包-收到王五的红包", "其他", (6, 188), 6),
    ("客户A", "收钱码收款", "商户收款", (80, 400), 4),
]


def pick_hour(pref: str, weekday: int) -> int:
    weekend = weekday >= 6
    if pref == "morning":
        return random.randint(7, 10)
    if pref == "meal":
        return random.choice([11, 12, 13, 17, 18, 19])
    if pref == "dinner":
        return random.randint(18, 21)
    if pref == "commute":
        return random.choice([8, 9, 18, 19])
    if pref == "evening":
        return random.randint(17, 22)
    if pref == "weekend":
        return random.randint(10, 21) if weekend else random.randint(19, 22)
    return random.randint(8, 22)


def build_rows(days: int = 180, seed: int = 2026) -> list:
    random.seed(seed)
    rows = []
    start = datetime.now() - timedelta(days=days)
    weights = [m[4] for m in MERCHANTS]

    for i in range(days):
        day = start + timedelta(days=i)
        weekday = day.isoweekday()
        # 周末消费频次更高
        n = random.randint(2, 5) if weekday >= 6 else random.randint(1, 4)
        for _ in range(n):
            merchant, goods, ttype, (low, high), _, pref = random.choices(
                MERCHANTS, weights=weights
            )[0]
            ts = day.replace(
                hour=pick_hour(pref, weekday),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
            )
            amount = round(random.uniform(low, high), 2)
            rows.append(
                {
                    "ts": ts,
                    "trade_type": ttype,
                    "counterparty": merchant,
                    "goods": goods,
                    "direction": "支出",
                    "amount": amount,
                    "pay_method": random.choices(
                        ["零钱", "招商银行储蓄卡(1234)", "微信零钱通"],
                        weights=[45, 40, 15],
                    )[0],
                    "status": "支付成功",
                    "trade_no": f"4200{i:04d}{random.randint(100000, 999999)}",
                    "merchant_no": f"M{2026}{i:04d}{random.randint(10000, 99999)}",
                    "remark": "",
                }
            )

        # 收入：工资每月一次，红包/转账随机
        if day.day == 15:
            name, desc, ttype, (low, high), _ = INCOMES[2]
            ts = day.replace(hour=10, minute=random.randint(0, 59), second=0)
            rows.append(
                {
                    "ts": ts,
                    "trade_type": ttype,
                    "counterparty": name,
                    "goods": desc,
                    "direction": "收入",
                    "amount": round(random.uniform(low, high), 2),
                    "pay_method": "招商银行储蓄卡(1234)",
                    "status": "已到账",
                    "trade_no": f"5030{i:04d}{random.randint(100000, 999999)}",
                    "merchant_no": "",
                    "remark": f"{ts.year}年{ts.month}月工资",
                }
            )
        for _ in range(random.choices([0, 1, 2], weights=[45, 40, 15])[0]):
            name, desc, ttype, (low, high), _ = random.choices(
                INCOMES, weights=[8, 5, 1, 6, 4]
            )[0]
            if name == "某科技有限公司":
                continue
            ts = day.replace(
                hour=random.randint(8, 22),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
            )
            rows.append(
                {
                    "ts": ts,
                    "trade_type": ttype,
                    "counterparty": name,
                    "goods": desc,
                    "direction": "收入",
                    "amount": round(random.uniform(low, high), 2),
                    "pay_method": "零钱",
                    "status": "已存入零钱",
                    "trade_no": f"1000{i:04d}{random.randint(100000, 999999)}",
                    "merchant_no": "",
                    "remark": "",
                }
            )

    # 每月固定扣款：零钱提现（应被忽略类型过滤演示）
    rows.sort(key=lambda r: r["ts"])
    return rows


def write_weixin_csv(path: str, days: int = 180):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = build_rows(days=days)
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
    lines = [
        "微信支付账单明细,,,,,,,,,,",
        "",
        "微信昵称：[演示用户],,,,,,,,,,",
        "",
        f"起始时间：[{(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')} 00:00:00] "
        f"终止时间：[{datetime.now().strftime('%Y-%m-%d')} 23:59:59],,,,,,,,,,",
        "",
        "导出类型：[全部],,,,,,,,,,",
        "",
        "导出时间：[%s],,,,,,,,,," % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        ",".join(columns),
    ]
    for r in rows:
        cells = [
            r["ts"].strftime("%Y-%m-%d %H:%M:%S"),
            r["trade_type"],
            r["counterparty"],
            r["goods"],
            r["direction"],
            f"¥{r['amount']:.2f}",
            r["pay_method"],
            r["status"],
            r["trade_no"],
            r["merchant_no"],
            r["remark"],
        ]
        lines.append(",".join(f'"{c}"' if "," in str(c) else str(c) for c in cells))
    lines += [
        "",
        "----------------------微信支付账单明细列表--------------------",
        f"共{len(rows)}笔记录",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("\n".join(lines))
    return path, len(rows)


def upload(path: str) -> dict:
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        data = f.read()
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{os.path.basename(path)}"\r\nContent-Type: text/csv\r\n\r\n'
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        BASE_URL + "/api/bills/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())["data"]


def get(path: str):
    with urllib.request.urlopen(BASE_URL + path, timeout=60) as resp:
        return json.loads(resp.read().decode())["data"]


def main():
    path, count = write_weixin_csv(os.path.join(OUT_DIR, "wx_demo_180d.csv"), days=180)
    print(f"✅ 已生成假账单：{path}")
    print(f"   共 {count} 笔，时间跨度 180 天\n")

    info = upload(path)
    bill_id = info["bill_id"]
    print(
        f"✅ 上传解析成功  bill_id={bill_id}  渠道={info['channel']}  记录={info['record_count']}"
    )
    print(f"   区间 {info['start_date']} ~ {info['end_date']}\n")

    ov = get(f"/api/bills/{bill_id}/overview")
    print("=" * 62)
    print("【总览】")
    print(f"  收入合计   ¥{ov['income_total']:>12,.2f}   ({ov['income_count']} 笔)")
    print(f"  支出合计   ¥{ov['expense_total']:>12,.2f}   ({ov['expense_count']} 笔)")
    print(f"  净收支     ¥{ov['net_total']:>12,.2f}")
    print(f"  统计天数   {ov['days']} 天")
    print(f"  日均支出   ¥{ov['avg_daily_expense']:>12,.2f}")
    print(f"  笔均支出   ¥{ov['avg_ticket']:>12,.2f}")
    print(
        f"  单笔区间   ¥{ov['min_expense']:,.2f} ~ ¥{ov['max_expense']:,.2f}   中位数 ¥{ov['median_expense']:,.2f}"
    )

    print("\n" + "=" * 62)
    print("【月度趋势】")
    for row in get(f"/api/bills/{bill_id}/trend?freq=month"):
        bar_in = "█" * int(row["income"] / 800)
        bar_out = "▓" * int(row["expense"] / 800)
        print(
            f"  {row['period']}  收入 {row['income']:>9,.0f}  支出 {row['expense']:>9,.0f}  "
            f"结余 {row['net']:>9,.0f}  ({row['count']}笔)"
        )
        print(f"             收 {bar_in}")
        print(f"             支 {bar_out}")

    print("\n" + "=" * 62)
    print("【支出分类 TOP】")
    cats = get(f"/api/bills/{bill_id}/categories")
    for i, c in enumerate(cats, 1):
        bar = "▇" * int(c["ratio"] / 1.2)
        print(
            f"  {i:>2}. {c['category']:<6} ¥{c['amount']:>10,.2f}  {c['ratio']:>5.1f}%  {bar}"
        )

    print("\n" + "=" * 62)
    print("【交易对方 TOP10】")
    for i, t in enumerate(get(f"/api/bills/{bill_id}/counterparties?top=10"), 1):
        print(
            f"  {i:>2}. {t['counterparty']:<22} ¥{t['amount']:>10,.2f}  ({t['count']} 笔)"
        )

    print("\n" + "=" * 62)
    print("【星期消费分布】")
    for w in get(f"/api/bills/{bill_id}/weekday"):
        bar = "▇" * int(w["amount"] / 1200)
        print(f"  {w['weekday']}  ¥{w['amount']:>10,.2f}  {w['count']:>3}笔  {bar}")

    print("\n" + "=" * 62)
    print("【时段消费分布 TOP8】")
    hours = sorted(get(f"/api/bills/{bill_id}/hours"), key=lambda x: -x["amount"])[:8]
    for h in hours:
        print(f"  {h['hour']:>2}时  ¥{h['amount']:>10,.2f}  {h['count']:>3}笔")

    print("\n" + "=" * 62)
    print("【单笔大额 TOP8】")
    for i, r in enumerate(get(f"/api/bills/{bill_id}/top?top=8"), 1):
        print(
            f"  {i}. {r['trade_time']}  {r['counterparty']:<18} ¥{r['amount']:>9,.2f}  [{r['category']}]"
        )

    print("\n" + "=" * 62)
    page = get(f"/api/bills/{bill_id}/transactions?page=1&size=8")
    print(f"【明细第1页 / 共{page['pages']}页 / {page['total']}条】")
    print(f"  {'时间':<20}{'收/支':<6}{'金额':>10}  {'分类':<6}{'交易对方'}")
    for r in page["rows"]:
        sign = "+" if r["direction"] == "收入" else "-"
        print(
            f"  {r['trade_time']:<20}{r['direction']:<6}{sign}{r['amount']:>9,.2f}  "
            f"{r['category']:<6}{r['counterparty']}"
        )

    print("\n" + "=" * 62)
    print(f"🌐 打开 http://127.0.0.1:5105 选中 bill_id = {bill_id} 查看可视化看板")
    print(f"📥 导出报告：http://127.0.0.1:5105/api/bills/{bill_id}/export?format=xlsx")


if __name__ == "__main__":
    main()
