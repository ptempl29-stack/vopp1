import re
from collections.abc import Iterable


_INVOICE_NUMBER_RE = re.compile(r"^MB-(\d+)$")


def compute_next_invoice_number(invoice_numbers: Iterable[object], base: int) -> str:
    """Return the first unused MB number at or above the configured base.

    Using the first available number keeps a stray high legacy invoice from
    moving the active sequence forward while still preventing duplicates.
    """
    used = set()
    for invoice_number in invoice_numbers:
        if not isinstance(invoice_number, str):
            continue
        match = _INVOICE_NUMBER_RE.fullmatch(invoice_number)
        if match:
            used.add(int(match.group(1)))

    candidate = base
    while candidate in used:
        candidate += 1
    return f"MB-{candidate:04d}"
