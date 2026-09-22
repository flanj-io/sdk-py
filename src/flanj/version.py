"""Package version, and the OTLP scope version the collector sees."""

from __future__ import annotations

from typing import Final

# Plain assignment, no annotation: the build backend reads this line with a
# regex and an annotated target does not match it.
#
# The first real release. Bumped from the "0.1.0.dev0" placeholder deliberately, not
# automatically: this number is a one-line call for whoever cuts the release, not a
# mechanical increment. 0.2.0 matches the TypeScript SDK: apart from HTTP capture the
# two are the same SDK - same defaults, same records, same entry points - so one
# version number for both is the honest one, and a release note that names one
# version is enough. It must stay greater than any version already registered for
# this package and PEP 440-valid; see CONTRIBUTING.md's Releasing section.
__version__ = "0.2.0"

#: `flanj.capture.version` - the WIRE contract version (CONTRACTS section 2),
#: deliberately NOT the package version. It changes only when the record shape
#: does, in the canonical contract, for every SDK at once.
CAPTURE_VERSION: Final = "1"

#: The OTLP instrumentation scope name this SDK reports.
SCOPE_NAME: Final = "flanj"
