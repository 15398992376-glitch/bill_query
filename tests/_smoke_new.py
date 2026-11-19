import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:5105"
BILL = "0398fc4993e3"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


print("health:", get("/api/health")["data"])
print("meta channels:", get("/api/meta")["data"]["channels"])

q = "exclude_transfer=1"
for name in ["overview", "heatmap", "comparison", "insights", "budget"]:
    d = get(f"/api/bills/{BILL}/{name}?{q}")["data"]
    if name == "overview":
        print(
            "overview savings:",
            d["savings_rate"],
            "transfer:",
            d["transfer_count"],
            d["transfer_amount"],
            "forecast:",
            d["forecast_month_expense"],
        )
    elif name == "heatmap":
        print(
            "heatmap total/max:",
            d["total"],
            d["max_amount"],
            "rows:",
            len(d["matrix"]),
            "cols:",
            len(d["matrix"][0]),
        )
    elif name == "comparison":
        print(
            "comparison:",
            d["previous"].get("month"),
            "->",
            d["current"].get("month"),
            "delta_pct:",
            d["delta"].get("amount_pct"),
            "cats:",
            len(d["categories"]),
        )
    elif name == "insights":
        print("insights:", len(d), [i["type"] for i in d])
    else:
        print("budget:", d["month"], d["monthly"], d["used"], d["percent"])

saved = post(
    f"/api/bills/{BILL}/budget", {"monthly": 3000, "categories": {"餐饮": 800}}
)
print("save budget:", saved["data"])
print("budget after save:", get(f"/api/bills/{BILL}/budget")["data"])

for text in ["本月支出大于100", "上个月餐饮", "美团一共花了多少", "今年收入"]:
    d = get(f"/api/bills/{BILL}/nl-query?q={urllib.parse.quote(text)}")["data"]
    print("nl:", text, "->", d["answer"], d["parsed"])

tx = get(f"/api/bills/{BILL}/transactions?exclude_transfer=1&weekday=6&size=5")["data"]
print("tx filter:", tx["total"], "rows:", len(tx["rows"]))

post(
    f"/api/bills/{BILL}/budget",
    {"monthly": 3000, "categories": {"餐饮美食": 800, "交通出行": 500}},
)
print("restored demo budget")
