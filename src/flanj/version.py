"""Package version, and the OTLP scope version the collector sees."""

from __future__ import annotations

from typing import Final

# Plain assignment, no annotation: the build backend reads this line with a
# regex and an annotated target does not match it.
#
# Bumped by hand for each release, never mechanically: this number is a one-line
# call for whoever cuts it. 0.2.1 is the first fix release after 0.2.0: the export
# wrapper compared the exporter's result against the wrong Enum class under the
# OpenTelemetry versions a fresh install resolves, and printed "export failed"
# on every successful export. The TypeScript SDK numbers itself separately
# (0.3.0 at the time of this release) — the wire contract below is what the two
# share, not the package version. Must stay greater than any version already
# registered for this package and PEP 440-valid; see CONTRIBUTING.md's Releasing section.
__version__ = "0.2.1"

#: `flanj.capture.version` - the WIRE contract version (CONTRACTS section 2),
#: deliberately NOT the package version. It changes only when the record shape
#: does, in the canonical contract, for every SDK at once.
CAPTURE_VERSION: Final = "1"

#: The OTLP instrumentation scope name this SDK reports.
SCOPE_NAME: Final = "flanj"
