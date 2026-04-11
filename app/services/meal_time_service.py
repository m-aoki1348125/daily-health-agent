from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def resolve_meal_service_date(
    consumed_at: datetime,
    *,
    timezone: str,
    rollover_hour: int,
) -> date:
    local_dt = consumed_at.astimezone(ZoneInfo(timezone))
    if local_dt.hour < rollover_hour:
        return (local_dt - timedelta(days=1)).date()
    return local_dt.date()


def format_meal_service_time(
    consumed_at: datetime,
    *,
    timezone: str,
    rollover_hour: int,
) -> str:
    local_dt = consumed_at.astimezone(ZoneInfo(timezone))
    if local_dt.hour < rollover_hour:
        return f"{local_dt.hour + 24:02d}:{local_dt.minute:02d}"
    return local_dt.strftime("%H:%M")
