import os
import sys
import yaml
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "config.yaml"
)
CONFIG_PATH = os.path.abspath(CONFIG_PATH)

_DEFAULT_CONFIG = {
    "app": {
        "name": "账单查询分析系统",
        "host": "0.0.0.0",
        "port": 5105,
        "debug": False,
        "upload_dir": "data/upload",
        "export_dir": "data/export",
        "max_upload_mb": 50,
    },
    "database": {"enabled": False},
    "billing": {
        "default_channel": "微信支付",
        "currency": "CNY",
        "income_keywords": ["收入", "收款"],
        "ignore_types": [],
        "categories": {},
    },
}


def _deep_merge(base, override):
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path=None):
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        return _DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _deep_merge(_DEFAULT_CONFIG, raw)


CONFIG = load_config()


def app_conf(key, default=None):
    return CONFIG.get("app", {}).get(key, default)


def billing_conf(key, default=None):
    return CONFIG.get("billing", {}).get(key, default)


def abs_path(*parts):
    return os.path.join(BASE_DIR, *parts)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


_LOGGER_READY = False


def get_logger(name="bill"):
    global _LOGGER_READY
    logger = logging.getLogger(name)
    if _LOGGER_READY:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_dir = ensure_dir(abs_path("data", "logs"))
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bill.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    _LOGGER_READY = True
    return logger
