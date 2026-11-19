import os
import sys
import tempfile
import unittest
import zipfile

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from bill_query import analytics, annotations, classifier, store  # noqa: E402
from bill_query.api import create_app  # noqa: E402
from bill_query.normalizer import parse_bill  # noqa: E402
from bill_query.repository import (  # noqa: E402
    dedupe_frame,
    expand_archive,
    query_filter,
    repository,
)
from tests.make_sample import write_weixin_csv  # noqa: E402

ALIPAY_TITLE = ["支付宝交易记录明细查询", "", "", "", "", "", "", ""]
ALIPAY_COLUMNS = [
    "交易创建时间",
    "交易对方",
    "商品名称",
    "金额（元）",
    "收/支",
    "交易状态",
    "交易号",
    "商家订单号",
]


def write_alipay_csv(path: str) -> str:
    rows = [
        [
            "2026-03-01 12:30:45",
            "美团",
            "美团外卖订单",
            "38.50",
            "支出",
            "交易成功",
            "2026030122001",
            "M2026030101",
        ],
        [
            "2026-03-02 09:10:00",
            "星巴克",
            "咖啡",
            "32.00",
            "支出",
            "交易成功",
            "2026030222002",
            "M2026030202",
        ],
        [
            "2026-03-03 18:20:11",
            "张三",
            "转账",
            "500.00",
            "收入",
            "交易成功",
            "2026030322003",
            "",
        ],
    ]
    lines = [",".join(ALIPAY_TITLE), ",".join(ALIPAY_COLUMNS)]
    lines += [",".join(row) for row in rows]
    with open(path, "w", encoding="gbk", newline="") as f:
        f.write("\n".join(lines))
    return path


class AlipayTest(unittest.TestCase):
    def test_parse_alipay_gbk(self):
        tmp = tempfile.mkdtemp()
        path = write_alipay_csv(os.path.join(tmp, "alipay.csv"))
        result = parse_bill(path)
        self.assertEqual(result.channel, "支付宝", result.warnings)
        self.assertEqual(len(result.df), 3)
        self.assertTrue((result.df["amount"] > 0).all())
        self.assertEqual(
            sorted(result.df["direction"].tolist()), ["支出", "支出", "收入"]
        )


class DedupeTest(unittest.TestCase):
    def test_dedupe_by_trade_no(self):
        frame = pd.DataFrame(
            [
                {
                    "trade_no": "A1",
                    "trade_time": "2026-01-01 10:00:00",
                    "amount": 10.0,
                    "direction": "支出",
                    "counterparty": "甲",
                },
                {
                    "trade_no": "A1",
                    "trade_time": "2026-01-01 10:00:00",
                    "amount": 10.0,
                    "direction": "支出",
                    "counterparty": "甲",
                },
                {
                    "trade_no": "A2",
                    "trade_time": "2026-01-02 10:00:00",
                    "amount": 20.0,
                    "direction": "支出",
                    "counterparty": "乙",
                },
            ]
        )
        self.assertEqual(len(dedupe_frame(frame)), 2)

    def test_dedupe_without_trade_no(self):
        frame = pd.DataFrame(
            [
                {
                    "trade_no": "",
                    "trade_time": "2026-01-01 10:00:00",
                    "amount": 10.0,
                    "direction": "支出",
                    "counterparty": "甲",
                },
                {
                    "trade_no": "",
                    "trade_time": "2026-01-01 10:00:00",
                    "amount": 10.0,
                    "direction": "支出",
                    "counterparty": "甲",
                },
            ]
        )
        self.assertEqual(len(dedupe_frame(frame)), 1)


class ZipTest(unittest.TestCase):
    def test_expand_archive(self):
        tmp = tempfile.mkdtemp()
        sample = write_weixin_csv(os.path.join(tmp, "wx.csv"))
        zip_path = os.path.join(tmp, "bills.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(sample, "wx.csv")
            zf.writestr("readme.txt", "ignore me")
        out_dir = os.path.join(tmp, "out")
        files = expand_archive(zip_path, out_dir)
        self.assertEqual(len(files), 1)
        self.assertTrue(os.path.exists(files[0]))

    def test_expand_archive_encrypted_raises(self):
        tmp = tempfile.mkdtemp()
        bad = os.path.join(tmp, "bad.zip")
        with open(bad, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(ValueError):
            expand_archive(bad, os.path.join(tmp, "out"))


class FeatureAnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.old_storage = repository.storage_dir
        cls.old_budget = analytics.BUDGET_FILE
        cls.old_db = store.DB_FILE
        cls.old_annotation = annotations.ANNOTATION_FILE
        repository.storage_dir = os.path.join(cls.tmp, "bills")
        os.makedirs(repository.storage_dir, exist_ok=True)
        analytics.BUDGET_FILE = os.path.join(cls.tmp, "budgets.json")
        store.DB_FILE = os.path.join(cls.tmp, "bills.db")
        annotations.ANNOTATION_FILE = os.path.join(cls.tmp, "annotations.json")
        cls.sample = write_weixin_csv(os.path.join(cls.tmp, "wx.csv"))
        cls.dataset = repository.save_many([(cls.sample, "wx.csv")])
        cls.bill_id = cls.dataset.bill_id

    @classmethod
    def tearDownClass(cls):
        repository._cache.pop(cls.bill_id, None)
        repository.storage_dir = cls.old_storage
        analytics.BUDGET_FILE = cls.old_budget
        store.DB_FILE = cls.old_db
        annotations.ANNOTATION_FILE = cls.old_annotation

    def test_heatmap_shape(self):
        data = analytics.heatmap_week_hour(self.bill_id)
        self.assertEqual(len(data["matrix"]), 7)
        self.assertTrue(all(len(row) == 24 for row in data["matrix"]))
        self.assertEqual(len(data["counts"]), 7)
        self.assertGreater(data["total"], 0)

    def test_comparison_keys(self):
        data = analytics.comparison(self.bill_id)
        for key in ("current", "previous", "delta", "categories"):
            self.assertIn(key, data)
        self.assertIn("amount_pct", data["delta"])
        if data["categories"]:
            self.assertIn("category", data["categories"][0])

    def test_insights_non_empty(self):
        items = analytics.insights(self.bill_id)
        self.assertGreater(len(items), 0)
        for item in items:
            for key in ("type", "level", "title", "detail"):
                self.assertIn(key, item)

    def test_transfer_flag_column(self):
        frame = classifier.classify_frame(self.dataset.df)
        self.assertIn("is_transfer", frame.columns)
        self.assertTrue(frame["is_transfer"].any())

    def test_nl_query_category_and_merchant(self):
        cat = analytics.nl_query(self.bill_id, "上个月餐饮")
        self.assertEqual(cat["parsed"]["category"], "餐饮美食")
        self.assertTrue(cat["parsed"]["start_date"].endswith("-01"))

        merchant = analytics.nl_query(self.bill_id, "美团一共花了多少")
        self.assertEqual(merchant["parsed"]["keyword"], "美团")
        self.assertGreater(merchant["count"], 0)

        income = analytics.nl_query(self.bill_id, "今年收入")
        self.assertEqual(income["parsed"]["direction"], "收入")

    def test_nl_query_rejects_empty(self):
        with self.assertRaises(ValueError):
            analytics.nl_query(self.bill_id, "   ")

    def test_budget_roundtrip(self):
        analytics.save_budget(self.bill_id, monthly=5000, categories={"餐饮美食": 800})
        status = analytics.budget_status(self.bill_id)
        self.assertEqual(status["monthly"], 5000.0)
        self.assertGreaterEqual(status["percent"], 0)
        self.assertEqual(len(status["categories"]), 1)
        self.assertEqual(status["categories"][0]["category"], "餐饮美食")


class FeatureApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.old_storage = repository.storage_dir
        cls.old_budget = analytics.BUDGET_FILE
        cls.old_db = store.DB_FILE
        cls.old_annotation = annotations.ANNOTATION_FILE
        repository.storage_dir = os.path.join(cls.tmp, "bills")
        os.makedirs(repository.storage_dir, exist_ok=True)
        analytics.BUDGET_FILE = os.path.join(cls.tmp, "budgets.json")
        store.DB_FILE = os.path.join(cls.tmp, "bills.db")
        annotations.ANNOTATION_FILE = os.path.join(cls.tmp, "annotations.json")
        cls.sample = write_weixin_csv(os.path.join(cls.tmp, "wx.csv"))
        cls.app = create_app()
        cls.client = cls.app.test_client()
        with open(cls.sample, "rb") as f:
            res = cls.client.post(
                "/api/bills/upload",
                data={"files": [(f, "wx.csv")]},
                content_type="multipart/form-data",
            )
        cls.bill_id = res.get_json()["data"]["bill_id"]

    @classmethod
    def tearDownClass(cls):
        repository._cache.pop(cls.bill_id, None)
        repository.storage_dir = cls.old_storage
        analytics.BUDGET_FILE = cls.old_budget
        store.DB_FILE = cls.old_db
        annotations.ANNOTATION_FILE = cls.old_annotation

    def test_new_endpoints(self):
        for name in ("heatmap", "comparison", "insights", "budget"):
            res = self.client.get(f"/api/bills/{self.bill_id}/{name}")
            self.assertEqual(res.status_code, 200, name)
            self.assertTrue(res.get_json()["success"], name)

    def test_budget_post(self):
        res = self.client.post(
            f"/api/bills/{self.bill_id}/budget",
            json={"monthly": 2000, "categories": {"餐饮美食": 500}},
        )
        self.assertEqual(res.status_code, 200)
        status = self.client.get(f"/api/bills/{self.bill_id}/budget").get_json()["data"]
        self.assertEqual(status["monthly"], 2000.0)

    def test_nl_query_endpoint(self):
        res = self.client.get(f"/api/bills/{self.bill_id}/nl-query?q=本月支出大于100")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertIn("answer", data)
        self.assertEqual(data["parsed"]["min_amount"], 100.0)

    def test_filter_weekday_and_transfer(self):
        res = self.client.get(
            f"/api/bills/{self.bill_id}/transactions?weekday=6&exclude_transfer=1&size=5"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])


class TempEnvMixin:
    """把存储、预算、索引、标注全部重定向到临时目录。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls._old = {
            "storage": repository.storage_dir,
            "budget": analytics.BUDGET_FILE,
            "db": store.DB_FILE,
            "annotation": annotations.ANNOTATION_FILE,
        }
        repository.storage_dir = os.path.join(cls.tmp, "bills")
        os.makedirs(repository.storage_dir, exist_ok=True)
        analytics.BUDGET_FILE = os.path.join(cls.tmp, "budgets.json")
        store.DB_FILE = os.path.join(cls.tmp, "bills.db")
        annotations.ANNOTATION_FILE = os.path.join(cls.tmp, "annotations.json")
        cls.sample = write_weixin_csv(os.path.join(cls.tmp, "wx.csv"))
        cls.dataset = repository.save_many([(cls.sample, "wx.csv")])
        cls.bill_id = cls.dataset.bill_id

    @classmethod
    def tearDownClass(cls):
        repository._cache.pop(cls.bill_id, None)
        repository.storage_dir = cls._old["storage"]
        analytics.BUDGET_FILE = cls._old["budget"]
        store.DB_FILE = cls._old["db"]
        annotations.ANNOTATION_FILE = cls._old["annotation"]


class StoreTest(TempEnvMixin, unittest.TestCase):
    def test_index_and_stats(self):
        data = store.stats()
        self.assertEqual(data["indexed_rows"], len(self.dataset.df))
        self.assertIn(self.bill_id, [b["bill_id"] for b in data["bills"]])
        row = next(b for b in data["bills"] if b["bill_id"] == self.bill_id)
        self.assertEqual(row["indexed_rows"], len(self.dataset.df))

    def test_search_by_merchant(self):
        result = store.search("美团")
        self.assertGreater(result["total"], 0)
        self.assertEqual(result["keyword"], "美团")
        self.assertIn("counterparty", result["rows"][0])
        self.assertEqual(result["rows"][0]["bill_id"], self.bill_id)

    def test_search_scoped_and_limit(self):
        result = store.search("支出", limit=3, bill_id=self.bill_id)
        self.assertLessEqual(len(result["rows"]), 3)
        self.assertTrue(all(r["bill_id"] == self.bill_id for r in result["rows"]))

    def test_search_empty_keyword(self):
        self.assertEqual(store.search("   ")["total"], 0)

    def test_rebuild(self):
        result = store.rebuild([self.dataset])
        self.assertEqual(result["bills"], 1)
        self.assertEqual(result["rows"], len(self.dataset.df))

    def test_remove_bill(self):
        store.remove_bill(self.bill_id)
        self.assertEqual(store.search("美团", bill_id=self.bill_id)["total"], 0)
        store.index_dataset(self.dataset)
        self.assertGreater(store.search("美团", bill_id=self.bill_id)["total"], 0)


class AnnotationTest(TempEnvMixin, unittest.TestCase):
    def test_key_for_prefers_trade_no(self):
        self.assertEqual(annotations.key_for({"trade_no": "A1"}), "no:A1")
        key = annotations.key_for(
            {
                "trade_no": "",
                "trade_time": "2026-01-01 10:00:00",
                "amount": 12.5,
                "direction": "支出",
                "counterparty": "甲",
            }
        )
        self.assertTrue(key.startswith("mix:"))
        self.assertIn("甲", key)

    def test_set_summary_and_delete(self):
        annotations.set_annotation(self.bill_id, "no:T1", tag="报销", note="差旅")
        summary = annotations.summary(self.bill_id)
        self.assertEqual(summary["tagged"], 1)
        self.assertEqual(summary["items"]["no:T1"]["tag"], "报销")

        self.assertTrue(annotations.delete_annotation(self.bill_id, "no:T1"))
        self.assertFalse(annotations.delete_annotation(self.bill_id, "no:T1"))
        self.assertEqual(annotations.summary(self.bill_id)["tagged"], 0)

    def test_empty_annotation_removes_entry(self):
        annotations.set_annotation(self.bill_id, "no:T2", tag="临时")
        annotations.set_annotation(self.bill_id, "no:T2")
        self.assertNotIn("no:T2", annotations.summary(self.bill_id)["items"])

    def test_set_requires_key(self):
        with self.assertRaises(ValueError):
            annotations.set_annotation(self.bill_id, "")

    def test_apply_ignored_filters_rows(self):
        row = self.dataset.df.iloc[0]
        key = annotations.key_for(row)
        before = len(self.dataset.df)
        annotations.set_annotation(self.bill_id, key, ignored=True)
        try:
            filtered = annotations.apply_ignored(self.bill_id, self.dataset.df)
            self.assertEqual(len(filtered), before - 1)
            self.assertEqual(annotations.summary(self.bill_id)["ignored"], 1)
        finally:
            annotations.delete_annotation(self.bill_id, key)
        self.assertEqual(
            len(annotations.apply_ignored(self.bill_id, self.dataset.df)), before
        )


class ExtraAnalyticsTest(TempEnvMixin, unittest.TestCase):
    def test_year_report(self):
        data = analytics.year_report(self.bill_id)
        for key in (
            "year",
            "available_years",
            "income_total",
            "expense_total",
            "net_total",
            "months",
            "top_categories",
            "top_merchants",
            "pay_methods",
        ):
            self.assertIn(key, data)
        self.assertEqual(len(data["months"]), 12)
        self.assertIn("2026", data["available_years"])
        self.assertGreater(data["expense_total"], 0)
        self.assertEqual(
            round(data["income_total"] - data["expense_total"], 2), data["net_total"]
        )
        if data["top_categories"]:
            self.assertGreaterEqual(data["top_categories"][0]["ratio"], 0)

    def test_year_report_unknown_year_empty(self):
        data = analytics.year_report(self.bill_id, year="1999")
        self.assertEqual(data["expense_total"], 0)
        self.assertEqual(len(data["months"]), 12)

    def test_merchant_profile(self):
        data = analytics.merchant_profile(self.bill_id, "美团")
        self.assertIn("美团", data["name"])
        self.assertGreater(data["count"], 0)
        self.assertGreater(data["total"], 0)
        self.assertGreaterEqual(data["max"], data["avg"])
        self.assertGreater(data["active_months"], 0)
        self.assertGreater(len(data["by_month"]), 0)
        self.assertTrue(data["by_hour"])
        self.assertTrue(data["by_category"])

    def test_merchant_profile_errors(self):
        with self.assertRaises(ValueError):
            analytics.merchant_profile(self.bill_id, "")
        with self.assertRaises(ValueError):
            analytics.merchant_profile(self.bill_id, "不存在的商户XYZ")

    def test_category_trend(self):
        data = analytics.category_trend(self.bill_id, top=4)
        self.assertLessEqual(len(data["categories"]), 4)
        self.assertGreater(len(data["months"]), 0)
        self.assertEqual(len(data["series"]), len(data["categories"]))
        for item in data["series"]:
            self.assertEqual(len(item["data"]), len(data["months"]))
        self.assertTrue(all(m.startswith("2026-") for m in data["months"]))

    def test_cumulative_expense(self):
        data = analytics.cumulative_expense(self.bill_id)
        self.assertGreater(len(data["rows"]), 0)
        self.assertGreater(data["total"], 0)
        values = [row["cumulative"] for row in data["rows"]]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[-1], data["total"], places=2)


class ExtraApiTest(TempEnvMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_year_report_endpoint(self):
        res = self.client.get(f"/api/bills/{self.bill_id}/year-report?year=2026")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["data"]["months"]), 12)

    def test_merchant_endpoint(self):
        res = self.client.get(f"/api/bills/{self.bill_id}/merchant?name=美团")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.get_json()["data"]["count"], 0)

    def test_merchant_endpoint_missing_name(self):
        res = self.client.get(f"/api/bills/{self.bill_id}/merchant")
        self.assertNotEqual(res.status_code, 200)

    def test_category_trend_and_cumulative(self):
        trend = self.client.get(f"/api/bills/{self.bill_id}/category-trend?top=3")
        self.assertEqual(trend.status_code, 200)
        self.assertIn("series", trend.get_json()["data"])

        cum = self.client.get(f"/api/bills/{self.bill_id}/cumulative")
        self.assertEqual(cum.status_code, 200)
        self.assertGreater(cum.get_json()["data"]["total"], 0)

    def test_annotation_endpoints(self):
        key = f"no:API{self.bill_id[:4]}"
        res = self.client.post(
            f"/api/bills/{self.bill_id}/annotations",
            json={"key": key, "tag": "重点", "note": "测试", "ignored": True},
        )
        self.assertEqual(res.status_code, 200)

        listing = self.client.get(f"/api/bills/{self.bill_id}/annotations")
        data = listing.get_json()["data"]
        self.assertEqual(data["items"][key]["tag"], "重点")
        self.assertEqual(data["ignored"], 1)

        deleted = self.client.delete(
            f"/api/bills/{self.bill_id}/annotations", json={"key": key}
        )
        self.assertEqual(deleted.status_code, 200)
        again = self.client.delete(
            f"/api/bills/{self.bill_id}/annotations", json={"key": key}
        )
        self.assertEqual(again.status_code, 404)

    def test_store_and_search_endpoints(self):
        stats = self.client.get("/api/store/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertGreaterEqual(stats.get_json()["data"]["indexed_rows"], 1)

        search = self.client.get("/api/search?q=美团&limit=5")
        self.assertEqual(search.status_code, 200)
        self.assertGreater(search.get_json()["data"]["total"], 0)

        rebuild = self.client.post("/api/store/rebuild")
        self.assertEqual(rebuild.status_code, 200)
        self.assertGreaterEqual(rebuild.get_json()["data"]["rows"], 1)

    def test_report_and_apidocs_pages(self):
        report = self.client.get(f"/report/{self.bill_id}")
        self.assertEqual(report.status_code, 200)
        self.assertIn("text/html", report.content_type)

        docs = self.client.get("/apidocs")
        self.assertEqual(docs.status_code, 200)
        self.assertIn(b"/api/store/stats", docs.data)

    def test_backup_returns_zip(self):
        res = self.client.get("/api/backup")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data[:2], b"PK")
        res.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
