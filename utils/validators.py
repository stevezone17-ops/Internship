import math
import re
from datetime import datetime

from utils.time_utils import IST

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def is_valid_email(email):
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def parse_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(amount) or math.isinf(amount):
        return None
    return round(amount, 2)


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
