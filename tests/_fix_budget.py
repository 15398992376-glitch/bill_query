import json

path = "data/budgets.json"
data = {
    "0398fc4993e3": {
        "monthly": 3000.0,
        "categories": {"餐饮美食": 800.0, "交通出行": 500.0},
    }
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(open(path, encoding="utf-8").read())
