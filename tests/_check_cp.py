import json, urllib.request, urllib.parse

base = "http://127.0.0.1:5105/api/bills/0398fc4993e3"


def get(path, params=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


q = {"top": 10, "direction": "支出", "min_amount": 1, "max_amount": 200}
rows = get("/counterparties", q)["data"]
print("=== TOP 交易对方（180天累计，筛选单笔 1~200 元）===")
for i, x in enumerate(rows, 1):
    cnt = x["count"]
    amt = x["amount"]
    print(
        f"{i:2d}. {x['counterparty']:<8} 笔数={cnt:<4} 累计=¥{amt:>8.2f} 单笔均=¥{amt / cnt:>6.2f}"
    )
