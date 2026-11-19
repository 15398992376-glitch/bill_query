import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:5105"
BILL = "0398fc4993e3"


def get(path, raw=False):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        body = r.read()
        return body if raw else json.loads(body.decode("utf-8"))


def request(path, method="POST", payload=None):
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else b""
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


print("store before:", get("/api/store/stats")["data"]["indexed_rows"])
print(
    "rebuild:",
    get("/api/store/rebuild", raw=False) if False else request("/api/store/rebuild"),
)
stats = get("/api/store/stats")["data"]
print("store after:", stats["indexed_rows"], "bills:", len(stats["bills"]))

hit = get(f"/api/search?q={urllib.parse.quote('美团')}")["data"]
print(
    "search 美团:",
    hit["total"],
    "first:",
    (hit["rows"][0]["counterparty"] if hit["rows"] else None),
)

year = get(f"/api/bills/{BILL}/year-report")["data"]
print(
    "year:",
    year["year"],
    year["expense_total"],
    "months:",
    len(year["months"]),
    "cats:",
    len(year["top_categories"]),
    "pay:",
    len(year["pay_methods"]),
)

merchant = get(f"/api/bills/{BILL}/merchant?name={urllib.parse.quote('美团')}")["data"]
print(
    "merchant:",
    merchant["name"],
    merchant["count"],
    merchant["total"],
    "interval:",
    merchant["avg_interval_days"],
    "months:",
    len(merchant["by_month"]),
)

trend = get(f"/api/bills/{BILL}/category-trend")["data"]
print("cat trend:", len(trend["months"]), "series:", len(trend["series"]))

cum = get(f"/api/bills/{BILL}/cumulative")["data"]
print("cumulative rows:", len(cum["rows"]), "total:", cum["total"])

ann = get(f"/api/bills/{BILL}/annotations")["data"]
print("annotations:", ann["total"])

tx = get(f"/api/bills/{BILL}/transactions?size=1")["data"]["rows"][0]
key = tx["row_key"]
print("tx row key:", key[:40])
print(
    "set annotation:",
    request(
        f"/api/bills/{BILL}/annotations",
        payload={"key": key, "tag": "报销", "note": "测试", "ignored": True},
    ),
)
ann = get(f"/api/bills/{BILL}/annotations")["data"]
print("annotations after set:", ann["total"], ann["ignored"], ann["tagged"])
filtered = get(f"/api/bills/{BILL}/transactions?size=1&exclude_ignored=1")["data"]
print("tx with exclude_ignored:", filtered["total"])
print(
    "delete annotation:",
    request(f"/api/bills/{BILL}/annotations", method="DELETE", payload={"key": key}),
)

report_html = get(f"/report/{BILL}", raw=True).decode("utf-8")
print(
    "report page:",
    len(report_html),
    "账单分析报告" in report_html,
    "打印" in report_html,
)
docs = get("/apidocs", raw=True).decode("utf-8")
print("apidocs page:", len(docs), "/api/bills/&lt;bill_id&gt;/heatmap" in docs)

backup = get("/api/backup", raw=True)
print("backup bytes:", len(backup), "zip:", backup[:2] == b"PK")
