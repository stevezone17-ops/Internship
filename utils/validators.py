from datetime import datetime

from utils.time_utils import IST


def parse_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount


def parse_date(value):
    if not value:
        return None
    normalized = value.replace("Z", "+00:00") if isinstance(value, str) else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return IST.localize(parsed)
    return parsed
