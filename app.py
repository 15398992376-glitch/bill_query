import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bill_query.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
