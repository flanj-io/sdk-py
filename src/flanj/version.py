"""Package version, and the OTLP scope version the collector sees."""

from __future__ import annotations

from typing import Final

# Plain assignment, no annotation: the build backend reads this line with a
# regex and an annotated target does not match it.
__version__ = "0.1.0.dev0"

#: `flanj.capture.version` - the WIRE contract version (CONTRACTS section 2),
#: deliberately NOT the package version. It changes only when the record shape
#: does, in the canonical contract, for every SDK at once.
CAPTURE_VERSION: Final = "1"

#: The OTLP instrumentation scope name this SDK reports.
SCOPE_NAME: Final = "flanj"
