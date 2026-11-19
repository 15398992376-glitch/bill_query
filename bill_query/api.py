import os
import uuid
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from . import analytics, annotations, classifier, exporter, store
from .normalizer import parse_bill
from .repository import expand_archive, query_filter, repository
from .settings import abs_path, app_conf, billing_conf, ensure_dir, get_logger

logger = get_logger("bill.api")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(BASE_DIR), "templates")
STATIC_DIR = os.path.join(os.path.dirname(BASE_DIR), "static")


def create_app(config_path=None):
    if config_path:
        from . import settings as settings_module

        settings_module.CONFIG = settings_module.load_config(config_path)

    app = Flask(
        __name__,
        template_folder=TEMPLATE_DIR,
        static_folder=STATIC_DIR,
    )
    app.config["JSON_AS_ASCII"] = False
    app.json.ensure_ascii = False

    upload_dir = ensure_dir(abs_path(app_conf("upload_dir", "data/upload")))
    export_dir = ensure_dir(abs_path(app_conf("export_dir", "data/export")))
    app.config["EXPORT_DIR"] = export_dir

    @app.errorhandler(ValueError)
    def handle_value_error(exc):
        return jsonify({"success": False, "message": str(exc)}), 400

    @app.errorhandler(KeyError)
    def handle_key_error(exc):
        message = exc.args[0] if exc.args else "资源不存在"
        return jsonify({"success": False, "message": str(message)}), 404

    @app.errorhandler(Exception)
    def handle_exception(exc):  # noqa: ANN001
        logger.exception("接口异常")
        return jsonify({"success": False, "message": f"服务异常: {exc}"}), 500

    def ok(data=None, **extra):
        payload = {"success": True}
        if data is not None:
            payload["data"] = data
        payload.update(extra)
        return jsonify(payload)

    def filter_kwargs(include_direction=False):
        """返回除日期外的筛选参数，用于 **kwargs 透传给分析函数。"""
        args = request.args
        kw = {
            "category": args.get("category", ""),
            "keyword": args.get("keyword", ""),
            "min_amount": args.get("min_amount") or None,
            "max_amount": args.get("max_amount") or None,
            "weekday": args.get("weekday") or None,
            "exclude_transfer": args.get("exclude_transfer", ""),
            "exclude_ignored": args.get("exclude_ignored", ""),
        }
        if include_direction:
            direction = args.get("direction", "")
            if direction:
                kw["direction"] = direction
        return kw

    def date_args():
        return request.args.get("start_date", ""), request.args.get("end_date", "")

    # ---------------- 页面 ----------------

    @app.get("/")
    def index():
        return render_template(
            "index.html", app_name=app_conf("name", "账单查询分析系统")
        )

    # ---------------- 上传 ----------------

    @app.post("/api/bills/upload")
    def upload_bill():
        files = request.files.getlist("files") or request.files.getlist("file")
        files = [f for f in files if f and f.filename]
        if not files:
            return jsonify({"success": False, "message": "未选择文件"}), 400
        zip_password = request.form.get("zip_password") or None
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        items = []
        for file in files:
            raw_bytes = file.read()
            repository.validate_upload(file.filename, len(raw_bytes))
            safe_name = secure_filename(file.filename) or f"bill_{uuid.uuid4().hex[:6]}"
            saved_path = os.path.join(upload_dir, f"{stamp}_{safe_name}")
            with open(saved_path, "wb") as f:
                f.write(raw_bytes)
            if saved_path.lower().endswith(".zip"):
                extracted = expand_archive(saved_path, upload_dir, zip_password)
                items.extend((path, os.path.basename(path)) for path in extracted)
            else:
                items.append((saved_path, file.filename))

        dataset = repository.save_many(items)
        return ok(dataset.summary())

    @app.post("/api/bills/preview")
    def preview_bill():
        if "file" not in request.files:
            return jsonify({"success": False, "message": "未选择文件"}), 400
        file = request.files["file"]
        raw_bytes = file.read()
        repository.validate_upload(file.filename, len(raw_bytes))
        temp_name = (
            f"preview_{uuid.uuid4().hex[:8]}{os.path.splitext(file.filename)[1]}"
        )
        temp_path = os.path.join(upload_dir, temp_name)
        with open(temp_path, "wb") as f:
            f.write(raw_bytes)
        try:
            result = parse_bill(temp_path, file.filename)
            result.df = classifier.classify_frame(result.df)
            head = result.df.head(50).to_dict(orient="records")
            return ok(
                {
                    "channel": result.channel,
                    "row_count": len(result.df),
                    "columns": list(result.df.columns),
                    "rows": head,
                    "warnings": result.warnings,
                }
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @app.get("/api/bills")
    def list_bills():
        return ok(repository.list_all())

    @app.get("/api/bills/<bill_id>")
    def bill_detail(bill_id):
        dataset = repository.get(bill_id)
        return ok(dataset.summary())

    @app.delete("/api/bills/<bill_id>")
    def delete_bill(bill_id):
        deleted = repository.delete(bill_id)
        if not deleted:
            return jsonify({"success": False, "message": "账单不存在"}), 404
        return ok({"bill_id": bill_id, "deleted": True})

    # ---------------- 查询 ----------------

    @app.get("/api/bills/<bill_id>/transactions")
    def transactions(bill_id):
        page = max(int(request.args.get("page", 1)), 1)
        size = min(max(int(request.args.get("size", 20)), 1), 500)
        df = query_filter(
            bill_id,
            start_date=request.args.get("start_date", ""),
            end_date=request.args.get("end_date", ""),
            direction=request.args.get("direction", ""),
            category=request.args.get("category", ""),
            keyword=request.args.get("keyword", ""),
            min_amount=request.args.get("min_amount") or None,
            max_amount=request.args.get("max_amount") or None,
            weekday=request.args.get("weekday") or None,
            exclude_transfer=request.args.get("exclude_transfer", ""),
            exclude_ignored=request.args.get("exclude_ignored", ""),
        )
        sort_by = request.args.get("sort_by", "trade_time")
        order = request.args.get("order", "desc")
        if sort_by in df.columns:
            df = df.sort_values(sort_by, ascending=(order == "asc"))
        total = len(df)
        start = (page - 1) * size
        page_df = df.iloc[start : start + size]
        cols = [
            "trade_time",
            "direction",
            "amount",
            "category",
            "counterparty",
            "goods",
            "trade_type",
            "pay_method",
            "status",
            "trade_no",
            "is_transfer",
        ]
        rows = page_df[[c for c in cols if c in page_df.columns]].to_dict(
            orient="records"
        )
        marks = annotations.bills_map(bill_id)
        for row in rows:
            key = annotations.key_for(row)
            row["row_key"] = key
            mark = marks.get(key) or {}
            row["tag"] = mark.get("tag", "")
            row["note"] = mark.get("note", "")
            row["ignored"] = bool(mark.get("ignored"))
        return ok(
            {
                "total": total,
                "page": page,
                "size": size,
                "pages": (total + size - 1) // size,
                "rows": rows,
            }
        )

    @app.get("/api/bills/<bill_id>/overview")
    def bill_overview(bill_id):
        start, end = date_args()
        return ok(
            analytics.overview(
                bill_id,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=True),
            )
        )

    @app.get("/api/bills/<bill_id>/trend")
    def bill_trend(bill_id):
        freq = request.args.get("freq", "month")
        if freq not in ("day", "week", "month", "year"):
            freq = "month"
        start, end = date_args()
        return ok(
            analytics.trend(
                bill_id,
                freq,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=True),
            )
        )

    @app.get("/api/bills/<bill_id>/categories")
    def bill_categories(bill_id):
        top = request.args.get("top", type=int)
        stat_direction = request.args.get("direction") or "支出"
        start, end = date_args()
        return ok(
            analytics.category_stats(
                bill_id,
                start_date=start,
                end_date=end,
                direction=stat_direction,
                top=top,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/counterparties")
    def bill_counterparties(bill_id):
        top = min(int(request.args.get("top", 20)), 100)
        stat_direction = request.args.get("direction") or "支出"
        start, end = date_args()
        return ok(
            analytics.counterparty_stats(
                bill_id,
                direction=stat_direction,
                top=top,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/weekday")
    def bill_weekday(bill_id):
        start, end = date_args()
        return ok(
            analytics.weekday_stats(
                bill_id,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=True),
            )
        )

    @app.get("/api/bills/<bill_id>/hours")
    def bill_hours(bill_id):
        start, end = date_args()
        return ok(
            analytics.hour_stats(
                bill_id,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=True),
            )
        )

    @app.get("/api/bills/<bill_id>/top")
    def bill_top(bill_id):
        top = min(int(request.args.get("top", 20)), 200)
        stat_direction = request.args.get("direction") or "支出"
        start, end = date_args()
        return ok(
            analytics.top_transactions(
                bill_id,
                top,
                direction=stat_direction,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/monthly-comparison")
    def bill_monthly_comparison(bill_id):
        return ok(analytics.monthly_comparison(bill_id))

    @app.get("/api/bills/<bill_id>/calendar")
    def bill_calendar(bill_id):
        from datetime import datetime as _dt

        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if not year or not month:
            months = analytics.available_months(bill_id)
            if months:
                last = months[-1]
                year, month = last["year"], last["month"]
            else:
                now = _dt.now()
                year, month = now.year, now.month
        direction = request.args.get("direction") or "支出"
        return ok(
            analytics.calendar_daily(
                bill_id,
                year,
                month,
                direction,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/available-months")
    def bill_available_months(bill_id):
        return ok(analytics.available_months(bill_id))

    @app.get("/api/bills/<bill_id>/report")
    def bill_report(bill_id):
        start, end = date_args()
        return ok(
            analytics.full_report(
                bill_id, start, end, **filter_kwargs(include_direction=False)
            )
        )

    @app.get("/api/bills/<bill_id>/heatmap")
    def bill_heatmap(bill_id):
        start, end = date_args()
        direction = request.args.get("direction") or "支出"
        return ok(
            analytics.heatmap_week_hour(
                bill_id,
                start,
                end,
                direction,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/comparison")
    def bill_comparison(bill_id):
        start, end = date_args()
        direction = request.args.get("direction") or "支出"
        return ok(
            analytics.comparison(
                bill_id,
                start,
                end,
                direction,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/insights")
    def bill_insights(bill_id):
        start, end = date_args()
        return ok(
            analytics.insights(
                bill_id, start, end, **filter_kwargs(include_direction=True)
            )
        )

    @app.get("/api/bills/<bill_id>/budget")
    def get_budget(bill_id):
        start, end = date_args()
        return ok(
            analytics.budget_status(
                bill_id, start, end, **filter_kwargs(include_direction=False)
            )
        )

    @app.post("/api/bills/<bill_id>/budget")
    def set_budget(bill_id):
        payload = request.get_json(silent=True) or {}
        return ok(
            analytics.save_budget(
                bill_id,
                monthly=payload.get("monthly", 0),
                categories=payload.get("categories") or {},
            )
        )

    @app.get("/api/bills/<bill_id>/nl-query")
    def bill_nl_query(bill_id):
        return ok(
            analytics.nl_query(
                bill_id,
                request.args.get("q", ""),
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/year-report")
    def bill_year_report(bill_id):
        start, end = date_args()
        return ok(
            analytics.year_report(
                bill_id,
                year=request.args.get("year"),
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=True),
            )
        )

    @app.get("/api/bills/<bill_id>/merchant")
    def bill_merchant(bill_id):
        start, end = date_args()
        return ok(
            analytics.merchant_profile(
                bill_id,
                request.args.get("name", ""),
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/category-trend")
    def bill_category_trend(bill_id):
        top = min(int(request.args.get("top", 6)), 12)
        start, end = date_args()
        return ok(
            analytics.category_trend(
                bill_id,
                top=top,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=False),
            )
        )

    @app.get("/api/bills/<bill_id>/cumulative")
    def bill_cumulative(bill_id):
        start, end = date_args()
        return ok(
            analytics.cumulative_expense(
                bill_id,
                start_date=start,
                end_date=end,
                **filter_kwargs(include_direction=False),
            )
        )

    # ---------------- 标注 ----------------

    @app.get("/api/bills/<bill_id>/annotations")
    def get_annotations(bill_id):
        return ok(annotations.summary(bill_id))

    @app.post("/api/bills/<bill_id>/annotations")
    def set_annotation(bill_id):
        payload = request.get_json(silent=True) or {}
        item = annotations.set_annotation(
            bill_id,
            payload.get("key", ""),
            tag=payload.get("tag", ""),
            note=payload.get("note", ""),
            ignored=bool(payload.get("ignored")),
        )
        return ok({"key": payload.get("key", ""), "item": item})

    @app.delete("/api/bills/<bill_id>/annotations")
    def delete_annotation(bill_id):
        payload = request.get_json(silent=True) or {}
        key = payload.get("key") or request.args.get("key", "")
        deleted = annotations.delete_annotation(bill_id, key)
        if not deleted:
            return jsonify({"success": False, "message": "标注不存在"}), 404
        return ok({"key": key, "deleted": True})

    # ---------------- 检索与索引 ----------------

    @app.get("/api/search")
    def global_search():
        keyword = request.args.get("q", "")
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
        return ok(
            store.search(keyword, limit=limit, bill_id=request.args.get("bill_id", ""))
        )

    @app.get("/api/store/stats")
    def store_stats():
        return ok(store.stats())

    @app.post("/api/store/rebuild")
    def store_rebuild():
        datasets = []
        for item in repository.list_all():
            try:
                datasets.append(repository.get(item["bill_id"]))
            except Exception:  # noqa: BLE001
                continue
        return ok(store.rebuild(datasets))

    # ---------------- 报告页 ----------------

    @app.get("/report/<bill_id>")
    def report_page(bill_id):
        start, end = date_args()
        filters = request.args.to_dict()
        for key in ("start_date", "end_date", "year"):
            filters.pop(key, None)
        report = analytics.full_report(bill_id, start, end, **filters)
        report["year_report"] = analytics.year_report(
            bill_id, start_date=start, end_date=end
        )
        report["category_trend"] = analytics.category_trend(
            bill_id, start_date=start, end_date=end
        )
        dataset = repository.get(bill_id)
        return render_template(
            "report.html",
            app_name=app_conf("name", "账单查询分析系统"),
            bill_id=bill_id,
            dataset=dataset,
            report=report,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    @app.get("/apidocs")
    def apidocs():
        rules = []
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
            if rule.endpoint == "static":
                continue
            methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
            rules.append(
                {"rule": str(rule), "methods": methods, "endpoint": rule.endpoint}
            )
        return render_template(
            "apidocs.html",
            app_name=app_conf("name", "账单查询分析系统"),
            rules=rules,
        )

    # ---------------- 备份与恢复 ----------------

    @app.get("/api/backup")
    def backup():
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for sub in ("bills", "bills.db", "budgets.json", "annotations.json"):
                path = abs_path("data", sub)
                if os.path.isfile(path):
                    zf.write(path, f"data/{sub}")
            bills_dir = abs_path("data", "bills")
            for name in os.listdir(bills_dir) if os.path.isdir(bills_dir) else []:
                if name.endswith(".pkl"):
                    zf.write(os.path.join(bills_dir, name), f"data/bills/{name}")
        buffer.seek(0)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"bill_backup_{stamp}.zip",
        )

    @app.post("/api/restore")
    def restore():
        import zipfile

        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".zip"):
            return jsonify({"success": False, "message": "请上传备份 ZIP"}), 400
        temp = os.path.join(upload_dir, f"restore_{uuid.uuid4().hex[:8]}.zip")
        file.save(temp)
        restored = 0
        try:
            with zipfile.ZipFile(temp) as zf:
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/")
                    if ".." in name or name.startswith("/"):
                        continue
                    if not name.startswith("data/") or info.is_dir():
                        continue
                    rel = name[len("data/") :]
                    if rel.startswith("bills/") or rel in (
                        "budgets.json",
                        "annotations.json",
                        "bills.db",
                    ):
                        target = abs_path("data", *rel.split("/"))
                        ensure_dir(os.path.dirname(target))
                        with zf.open(info) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                        restored += 1
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        repository._cache.clear()
        return ok({"restored_files": restored})

    # ---------------- 导出 ----------------

    @app.get("/api/bills/<bill_id>/export")
    def export_bill(bill_id):
        fmt = request.args.get("format", "xlsx").lower()
        start_date = request.args.get("start_date", "")
        end_date = request.args.get("end_date", "")
        df = query_filter(
            bill_id,
            start_date=start_date,
            end_date=end_date,
            direction=request.args.get("direction", ""),
            category=request.args.get("category", ""),
            keyword=request.args.get("keyword", ""),
            min_amount=request.args.get("min_amount") or None,
            max_amount=request.args.get("max_amount") or None,
            weekday=request.args.get("weekday") or None,
            exclude_transfer=request.args.get("exclude_transfer", ""),
            exclude_ignored=request.args.get("exclude_ignored", ""),
        )
        report = None
        if fmt != "csv":
            report = analytics.full_report(
                bill_id,
                start_date,
                end_date,
                **filter_kwargs(include_direction=False),
            )
        path = exporter.export_file(df, export_dir, fmt=fmt, analytics=report)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.get("/api/health")
    def health():
        return ok(
            {"status": "ok", "time": datetime.now().isoformat(timespec="seconds")}
        )

    @app.get("/api/meta")
    def meta():
        db_file = store.db_path()
        return ok(
            {
                "app_name": app_conf("name", "账单查询分析系统"),
                "currency": billing_conf("currency", "CNY"),
                "categories": list((billing_conf("categories", {}) or {}).keys()),
                "channels": ["微信支付", "支付宝", "银行", "多来源合并", "通用"],
                "has_db": os.path.isfile(db_file),
                "version": __import__("bill_query").__version__,
            }
        )

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host=app_conf("host", "0.0.0.0"),
        port=int(app_conf("port", 5105)),
        debug=bool(app_conf("debug", False)),
    )
