# Returns the current time as a naive UTC datetime.
#
# The app uses naive datetimes throughout, including SQLite models and
# Streamlit's date/time inputs. Using datetime.now(timezone.utc) directly
# would return an aware datetime and cause comparison errors with the
# naive datetimes already used by the app.
#
# This avoids the deprecated datetime.utcnow() while keeping everything
# consistent. Use this for scheduled_at/due-time comparisons as well.

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
