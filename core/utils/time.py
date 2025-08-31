# core/utils/time.py
from datetime import datetime, timedelta, timezone

# Define Brisbane timezone manually (no DST adjustment)
BRISBANE_TZ = timezone(timedelta(hours=10))


def now():
    """
    Returns the current datetime in Brisbane timezone.
    Usage: `now()` replaces `datetime.utcnow()`
    """
    return datetime.now(BRISBANE_TZ)


def now_iso():
    """
    Returns current Brisbane time as an ISO 8601 string.
    """
    return now().isoformat()
