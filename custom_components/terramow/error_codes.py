"""Known TerraMow device error codes mapped to human-readable text.

The firmware reports faults as bare numeric codes on two channels: the
dp_116 ``error_list`` (all currently active faults, ``{code, time}``) and
dp_115 (the newest fault's code alone — the same mirror relationship the
dp_114 "latest event code" has to the dp_123 event log).

The vendor never published a code table, so this catalog is
community-sourced (issue #171): each entry was captured live from a debug
log while the vendor app displayed the matching fault message. Unknown
codes fall back to ``Error <code>`` — when one shows up, map it here.
"""

from __future__ import annotations

ERROR_CODES: dict[int, str] = {
    # S1200 fw 9.9.210, issue #171 comment 5048257950: app said the mower
    # was lifted off the ground while mowing.
    201: "Mower lifted",
    # S1200 fw 9.9.210, issue #171 comment 5061068395: app said the mower
    # got stuck and could not free itself.
    903: "Mower stuck",
    # S1200 fw 9.9.210, issue #171 comment 5069633047: a second stuck-type
    # fault the app also labels "mower stuck".
    909: "Mower stuck",
}


def describe_error(code: object) -> str:
    """Human text for a device error code, falling back to the bare number.

    Tolerates arbitrary payload values: only a real int (bools excluded)
    resolves through the catalog; everything else just echoes the value so
    a malformed entry still produces a usable string.
    """
    if (
        isinstance(code, int)
        and not isinstance(code, bool)
        and code in ERROR_CODES
    ):
        return ERROR_CODES[code]
    return f"Error {code}"
