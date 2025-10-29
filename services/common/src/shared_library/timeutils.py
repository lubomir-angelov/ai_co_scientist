from datetime import datetime, timezone

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def to_iso(dt: datetime) -> str:
    # Force RFC3339 / ISO8601 with 'Z'
    return dt.astimezone(timezone.utc).isoformat()
