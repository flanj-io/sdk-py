"""Phone validator - ``phonenumbers`` (the Python port of libphonenumber).

The TypeScript floor decides with ``libphonenumber-js/max`` and the Go floor with
``nyaruka/phonenumbers``; this is the same metadata in a third runtime, which is
why the floor only ever redacts INTERNATIONAL numbers: without a ``+`` country
code there is no region to validate against, and a loose phone regex is exactly
what re-caught a Luhn-spared order id in the original library evaluation.

Pure function, no I/O - libphonenumber metadata is compiled into the package.
"""

from __future__ import annotations

import phonenumbers


def is_valid_phone_number(value: str) -> bool:
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        return False
    return phonenumbers.is_valid_number(parsed)
