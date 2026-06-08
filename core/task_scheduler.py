import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def compute_next_run(schedule: str) -> str:
    if not schedule:
        return (datetime.utcnow() + timedelta(hours=1)).isoformat()
    s = schedule.strip().lower()
    now = datetime.utcnow()
    if s.startswith("daily@"):
        parts = s.split("@")
        if len(parts) >= 2:
            time_part = parts[1]
            try:
                h, m = time_part.split(":")
                target = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                return target.isoformat()
            except (ValueError, IndexError):
                pass
    elif s.startswith("weekly@"):
        parts = s.split("@")
        if len(parts) >= 3:
            day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                       "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
                       "saturday": 5, "sunday": 6}
            target_day = day_map.get(parts[1].lower())
            if target_day is not None:
                try:
                    h, m = parts[2].split(":")
                    target = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                    days_ahead = (target_day - now.weekday()) % 7
                    if days_ahead == 0 and target <= now:
                        days_ahead = 7
                    target += timedelta(days=days_ahead)
                    return target.isoformat()
                except (ValueError, IndexError):
                    pass
    elif s == "hourly":
        return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0).isoformat()
    elif s.startswith("interval:"):
        try:
            minutes = int(s.split(":")[1])
            return (now + timedelta(minutes=minutes)).isoformat()
        except (ValueError, IndexError):
            pass
    return (now + timedelta(hours=1)).isoformat()
