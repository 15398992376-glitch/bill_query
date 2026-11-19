"""验证日历 API 输出效果。"""

import json
import urllib.request

BASE = "http://127.0.0.1:5105"
BILL_ID = "0398fc4993e3"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())["data"]


months = get(f"/api/bills/{BILL_ID}/available-months")
print("可用月份:", [m["label"] for m in months])

for ym in [(2026, 10), (2026, 8), (2026, 6)]:
    y, m = ym
    data = get(
        f"/api/bills/{BILL_ID}/calendar?year={y}&month={m}&direction=%E6%94%AF%E5%87%BA"
    )
    s = data["month_summary"]
    print(f"\n{'=' * 60}")
    print(f"{y}年{m}月 日历概览")
    print(f"  支出合计: ¥{s['total_expense']:,.2f}  笔数: {s['total_count']}")
    print(
        f"  消费天数: {s['active_days']}/{s['days_in_month']}  日均: ¥{s['avg_expense']:,.2f}"
    )
    print(f"  单日峰值: ¥{s['max_expense']:,.2f}  日期: {s['max_date']}")

    # 渲染文字版热力图
    cells = data["cells"]
    levels = {"0": "·", "1": "░", "2": "▒", "3": "▓", "4": "█"}
    print(f"\n  日历热力图（{y}-{m:02d}）：")
    print("  一   二   三   四   五   六   日")
    week = []
    for c in cells:
        if not c["in_month"]:
            week.append("  ·  ")
        else:
            lv = levels.get(str(c["level"]), "·")
            day = f"{c['day']:>2}"
            amt = f"{c['expense']:>6.0f}" if c["expense"] > 0 else "    ·"
            week.append(f"{day}{lv}{amt}")
        if len(week) == 7:
            print("  " + " ".join(week))
            week = []
    if week:
        print("  " + " ".join(week))

    # 热力等级分布
    in_cells = [c for c in cells if c["in_month"]]
    dist = {}
    for c in in_cells:
        dist[c["level"]] = dist.get(c["level"], 0) + 1
    print(
        f"\n  热力等级分布: "
        + "  ".join(f"L{k}:{v}天" for k, v in sorted(dist.items()))
    )
