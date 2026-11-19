import json
import sys
import urllib.request
import uuid

BASE = "http://127.0.0.1:5105"
FILE = r"D:\Users\ex_lijj170\Desktop\browser-use-agent\skills\物料停启用Agent\大小群迭代\1105\data\sample\wx_sample.csv"


def upload(path):
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        data = f.read()
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="wx_sample.csv"\r\nContent-Type: text/csv\r\n\r\n'
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        BASE + "/api/bills/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())


if __name__ == "__main__":
    print("health:", get("/api/health")["data"])
    payload = upload(FILE)
    print("upload:", json.dumps(payload["data"], ensure_ascii=False))
    bill_id = payload["data"]["bill_id"]

    ov = get(f"/api/bills/{bill_id}/overview")["data"]
    print("overview:", json.dumps(ov, ensure_ascii=False))

    trend = get(f"/api/bills/{bill_id}/trend?freq=month")["data"]
    print("trend months:", len(trend), trend[:2])

    cats = get(f"/api/bills/{bill_id}/categories")["data"]
    print("categories:", [(c["category"], c["amount"], c["ratio"]) for c in cats])

    top = get(f"/api/bills/{bill_id}/counterparties?top=5")["data"]
    print("top:", [(t["counterparty"], t["amount"]) for t in top])

    hour = get(f"/api/bills/{bill_id}/hours")["data"]
    print("hours peak:", max(hour, key=lambda h: h["amount"]))

    page = get(f"/api/bills/{bill_id}/transactions?page=1&size=5")["data"]
    print("page:", page["total"], page["pages"], len(page["rows"]))
    print("first row:", json.dumps(page["rows"][0], ensure_ascii=False))

    filtered = get(
        f"/api/bills/{bill_id}/transactions?page=1&size=5"
        "&direction=%E6%94%B6%E5%85%A5&keyword=%E8%BD%AC"
    )["data"]
    print("filtered income (direction=收入 & keyword=转):", filtered["total"])
