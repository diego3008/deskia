import datetime

import pytz

def convert_to_local(utc_dt: datetime, timezone_str: str) -> datetime:
    utc = pytz.utc.localize(utc_dt) if utc_dt.tzinfo is None else utc_dt
    local_tz = pytz.timezone(timezone_str)
    return utc.astimezone(local_tz)