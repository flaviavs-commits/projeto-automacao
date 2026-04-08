from secrets import compare_digest


def safe_compare(value: str, expected: str) -> bool:
    if not value or not expected:
        return False
    return compare_digest(value, expected)
