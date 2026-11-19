import argparse
import sys

from .api import create_app
from .settings import app_conf, get_logger


def main(argv=None):
    parser = argparse.ArgumentParser(description="账单查询分析系统")
    parser.add_argument("--host", default=None, help="监听地址")
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")
    args = parser.parse_args(argv)

    logger = get_logger("bill.main")
    host = args.host or app_conf("host", "0.0.0.0")
    port = args.port or int(app_conf("port", 5105))
    debug = args.debug or bool(app_conf("debug", False))

    application = create_app()
    logger.info("启动服务 http://%s:%s", host, port)
    application.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    sys.exit(main())
