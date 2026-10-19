"""Allow ``python -m mj`` to invoke the CLI."""

import sys

from mj.gateway.cli import main

sys.exit(main())
