"""Timezone / world clock - free WorldTimeAPI (no key)."""
import httpx
from datetime import datetime

WORLD_TIME_API = "http://worldtimeapi.org/api"

def get_time_info(location: str = "") -> str:
    """Get current time for a location using free WorldTimeAPI."""
    if not location:
        now = datetime.now()
        return f"Local time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Try as a timezone
    try:
        r = httpx.get(f"{WORLD_TIME_API}/timezone", timeout=10)
        if r.status_code == 200:
            timezones = r.json()
            loc_lower = location.lower()
            matches = [tz for tz in timezones if loc_lower in tz.lower()]
            if matches:
                tz_name = matches[0]
                r2 = httpx.get(f"{WORLD_TIME_API}/timezone/{tz_name}", timeout=10)
                if r2.status_code == 200:
                    data = r2.json()
                    return (
                        f"Time in {data.get('timezone', location)}: "
                        f"{data.get('datetime','')[:19]} "
                        f"(UTC{data.get('utc_offset','')})"
                    )
    except Exception:
        pass
    
    # Try direct city lookup
    try:
        r = httpx.get(f"{WORLD_TIME_API}/timezone/Etc/UTC", timeout=5)
        data = r.json()
        utc_dt = data.get("datetime", "")
        return f"Time for {location}: UTC {utc_dt[:19] if utc_dt else 'unknown'}"
    except Exception:
        pass
    
    return f"Local time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
