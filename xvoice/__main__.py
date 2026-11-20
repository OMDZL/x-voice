"""Allow `python -m xvoice` from the project folder."""

import sys

from xvoice.app import main

if __name__ == "__main__":
    sys.exit(main())
