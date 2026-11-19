import json
import urllib.request

BASE = "http://127.0.0.1:5105"
BILL_ID = "0398fc4993e3"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())["data"]


# 模拟用户截图里的筛选：2026-10-07 单日 + 金额 1~100
q = "start_date=2026-10-07&end_date=2026-10-07&min_amount=1&max_amount=100"

print("=" * 60)
print("筛选条件: 2026-10-07 单日, 金额 1~100")
print("=" * 60)

overview = get(f"/api/bills/{BILL_ID}/overview?{q}")
print(
    f"\n[总览] 记录={overview['record_count']}  支出={overview['expense_total']}  "
    f"笔数={overview['expense_count']}"
)

trend = get(f"/api/bills/{BILL_ID}/trend?freq=month&{q}")
print(f"\n[月度趋势] {trend}")

cats = get(f"/api/bills/{BILL_ID}/categories?{q}")
print(f"\n[支出分类] {cats}")

top = get(f"/api/bills/{BILL_ID}/counterparties?top=10&{q}")
print(f"\n[交易对方] {top}")

weekday = get(f"/api/bills/{BILL_ID}/weekday?{q}")
print(f"\n[星期分布] {weekday}")

hours = get(f"/api/bills/{BILL_ID}/hours?{q}")
nonzero = [h for h in hours if h["amount"] > 0]
print(f"\n[时段分布] 非零: {nonzero}")

tx = get(f"/api/bills/{BILL_ID}/transactions?page=1&size=10&{q}")
print(f"\n[明细] 总条数={tx['total']}")

print("\n" + "=" * 60)
print("校验：图表数据口径是否与明细一致")
print("=" * 60)
print(f"  总览记录数        = {overview['record_count']}")
print(f"  明细总条数        = {tx['total']}")
print(f"  分类笔数合计      = {sum(c['count'] for c in cats)}")
print(f"  对方笔数合计      = {sum(t['count'] for t in top)}")
print(f"  星期笔数合计      = {sum(w['count'] for w in weekday)}")
print(f"  时段笔数合计      = {sum(h['count'] for h in hours)}")
ok = (
    overview["record_count"]
    == tx["total"]
    == sum(c["count"] for c in cats)
    == sum(t["count"] for t in top)
    == sum(w["count"] for w in weekday)
    == sum(h["count"] for h in hours)
)
print(f"\n  {'✅ 全部一致' if ok else '❌ 仍不一致'}")

# 无金额筛选的对照
print("\n" + "=" * 60)
print("对照：2026-10-07 单日，不加金额限制")
print("=" * 60)
q2 = "start_date=2026-10-07&end_date=2026-10-07"
o2 = get(f"/api/bills/{BILL_ID}/overview?{q2}")
t2 = get(f"/api/bills/{BILL_ID}/transactions?page=1&size=10&{q2}")
print(
    f"  总览记录={o2['record_count']}  明细={t2['total']}  支出={o2['expense_total']}"
)
print(f"  {'✅ 一致' if o2['record_count'] == t2['total'] else '❌ 不一致'}")
