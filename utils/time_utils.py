from datetime import datetime

import pytz

IST = pytz.timezone("Asia/Kolkata")


def ist_now():
    return datetime.now(IST)


def format_ist(dt):
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    ist_time = dt.astimezone(IST)
    return ist_time.strftime("%d %b %Y, %I:%M %p IST")
