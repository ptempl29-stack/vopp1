from core.invoice_numbers import compute_next_invoice_number


def test_legacy_high_number_does_not_move_active_sequence():
    numbers = [*(f"MB-{number:04d}" for number in range(1, 64)), "MB-1008"]

    assert compute_next_invoice_number(numbers, base=63) == "MB-0064"


def test_sequence_advances_after_expected_number_is_used():
    numbers = [*(f"MB-{number:04d}" for number in range(1, 65)), "MB-1008"]

    assert compute_next_invoice_number(numbers, base=63) == "MB-0065"


def test_configured_base_is_used_when_available():
    numbers = ["MB-0001", "MB-0062", "MB-1008"]

    assert compute_next_invoice_number(numbers, base=63) == "MB-0063"


def test_invalid_invoice_numbers_are_ignored():
    numbers = [None, 64, "", "1008", "MB-invalid", "XX-0063", "MB-0063-extra"]

    assert compute_next_invoice_number(numbers, base=63) == "MB-0063"
