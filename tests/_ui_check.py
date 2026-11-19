import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "http://127.0.0.1:5105"
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.on(
        "console",
        lambda m: (
            errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None
        ),
    )
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1200)
    print("chartjs:", page.evaluate("typeof Chart"))
    count = page.locator(".bill-item").count()
    print("bills:", count)
    if count:
        page.locator(".bill-item").first.click()
        page.wait_for_timeout(5500)

    print("cards:", page.locator("#cards .card").count())
    print("year months:", page.locator("#yearMonths .month-cell").count())
    print("year kpis:", page.locator("#yearKpis .item").count())
    print("heatmap cells:", page.locator(".hm-cell").count())
    print("insights:", page.locator(".insight-card").count())
    print("tx rows:", page.locator("#txTable tbody tr").count())
    print("mark buttons:", page.locator(".mark-btn").count())
    print("report href:", page.locator("#linkReport").get_attribute("href")[:60])

    page.fill("#globalSearch", "美团")
    page.wait_for_timeout(1200)
    print("search hits:", page.locator(".search-hit").count())
    page.click("body", position={"x": 5, "y": 300})

    page.locator(".mark-btn").first.click()
    page.wait_for_timeout(500)
    print("mark dialog:", page.locator("#markDialog.show").count())
    page.fill("#markTag", "自动化测试")
    page.check("#markIgnored")
    page.click("#markSave")
    page.wait_for_timeout(1800)
    print("tagged pills:", page.locator(".tag-pill").count())
    page.locator(".mark-btn").first.click()
    page.wait_for_timeout(400)
    page.click("#markDelete")
    page.wait_for_timeout(1500)
    print("after delete pills:", page.locator(".tag-pill").count())

    page.screenshot(path="data/ui_check.png", full_page=True)
    print("errors:", errors[:8])
    browser.close()
