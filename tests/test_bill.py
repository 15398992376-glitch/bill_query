import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from bill_query import analytics, classifier, exporter  # noqa: E402
from bill_query.api import create_app  # noqa: E402
from bill_query.normalizer import parse_bill  # noqa: E402
from bill_query.repository import repository, query_filter  # noqa: E402
from tests.make_sample import write_bank_xlsx, write_weixin_csv  # noqa: E402


class NormalizerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.wx = write_weixin_csv(os.path.join(cls.tmp, "wx.csv"))
        cls.bank = write_bank_xlsx(os.path.join(cls.tmp, "bank.xlsx"))

    def test_weixin_parse(self):
        result = parse_bill(self.wx)
        self.assertGreater(len(result.df), 0)
        self.assertEqual(result.channel, "微信支付")
        self.assertIn("trade_time", result.df.columns)
        self.assertTrue((result.df["amount"] > 0).all())
        self.assertTrue(set(result.df["direction"]).issubset({"收入", "支出"}))

    def test_bank_parse(self):
        result = parse_bill(self.bank)
        self.assertGreater(len(result.df), 0)
        self.assertIn(result.channel, ("银行", "通用"))
        self.assertTrue(set(result.df["direction"]).issubset({"收入", "支出"}))

    def test_duplicate_removed(self):
        result = parse_bill(self.wx)
        keys = result.df[
            ["trade_time", "amount", "direction", "counterparty", "trade_no"]
        ]
        self.assertEqual(len(keys), len(keys.drop_duplicates()))


class AnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.wx = write_weixin_csv(os.path.join(cls.tmp, "wx.csv"))
        result = parse_bill(cls.wx)
        frame = classifier.classify_frame(result.df)
        cls.df = frame

    def test_categories(self):
        stats = classifier.category_overview(self.df)
        self.assertFalse(stats.empty)
        self.assertAlmostEqual(float(stats["ratio"].sum()), 100.0, delta=0.5)

    def test_classify_fallback(self):
        label = classifier.rule_classify("未知商户", "", "", "支出")
        self.assertEqual(label, "其他")

    def test_classify_keyword(self):
        label = classifier.rule_classify("美团外卖", "", "", "支出")
        self.assertEqual(label, "餐饮美食")

    def test_export_bytes(self):
        self.assertGreater(len(exporter.to_csv_bytes(self.df)), 0)
        self.assertGreater(len(exporter.to_excel_bytes(self.df)), 0)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.sample = write_weixin_csv(os.path.join(cls.tmp, "wx.csv"))
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_health(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

    def test_upload_and_query(self):
        with open(self.sample, "rb") as f:
            res = self.client.post(
                "/api/bills/upload",
                data={"file": (f, "wx.csv")},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 200, res.data)
        bill_id = res.get_json()["data"]["bill_id"]

        overview = self.client.get(f"/api/bills/{bill_id}/overview").get_json()
        self.assertTrue(overview["success"])
        self.assertGreater(overview["data"]["record_count"], 0)

        trend = self.client.get(f"/api/bills/{bill_id}/trend?freq=month").get_json()
        self.assertTrue(trend["success"])
        self.assertGreater(len(trend["data"]), 0)

        cats = self.client.get(f"/api/bills/{bill_id}/categories").get_json()
        self.assertTrue(cats["success"])

        tx = self.client.get(
            f"/api/bills/{bill_id}/transactions?page=1&size=10"
        ).get_json()
        self.assertTrue(tx["success"])
        self.assertLessEqual(len(tx["data"]["rows"]), 10)

        report = self.client.get(f"/api/bills/{bill_id}/report").get_json()
        self.assertTrue(report["success"])
        for key in ("overview", "monthly_trend", "category_stats", "weekday_stats"):
            self.assertIn(key, report["data"])

        exported = self.client.get(f"/api/bills/{bill_id}/export?format=csv")
        self.assertEqual(exported.status_code, 200)
        self.assertGreater(len(exported.data), 0)

        repository.delete(bill_id)

    def test_upload_rejects_bad_ext(self):
        res = self.client.post(
            "/api/bills/upload",
            data={"file": (tempfile.TemporaryFile(), "bad.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 400)

    def test_missing_bill(self):
        res = self.client.get("/api/bills/not-exists/overview")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
