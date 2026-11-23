"""Battery and basic system stats."""
import psutil
from core.registry import tool


@tool("Get battery percentage and whether the charger is plugged in.")
def get_battery():
    b = psutil.sensors_battery()
    if b is None:
        return {"error": "no battery detected"}
    return {"percent": round(b.percent), "plugged_in": b.power_plugged,
            "minutes_left": None if b.secsleft < 0 else b.secsleft // 60}


@tool("Get CPU load, RAM usage and disk usage of this computer.")
def get_system_stats():
    return {"cpu_percent": psutil.cpu_percent(interval=0.5),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent}
