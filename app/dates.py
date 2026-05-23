from datetime import date, datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")


def today_pt() -> date:
    return datetime.now(PT).date()


def to_publish_timestamp(date_str: str) -> datetime:
    """Convert YYYY-MM-DD to 9am PT as UTC datetime."""
    local_9am = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=9, minute=0, second=0, tzinfo=PT
    )
    return local_9am.astimezone(UTC)
