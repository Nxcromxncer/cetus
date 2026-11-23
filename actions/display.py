"""Screen brightness via brightnessctl (pacman -S brightnessctl)."""
import subprocess
from core.registry import tool


def _run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


@tool("Get the current screen brightness percentage.")
def get_brightness():
    dev, _cls, cur, pct, mx = _run("brightnessctl", "-m").split(",")[:5]
    return {"brightness_percent": int(pct.rstrip("%"))}


@tool("Set screen brightness to an exact percentage (1-100).")
def set_brightness(level: int):
    level = max(1, min(100, level))
    _run("brightnessctl", "set", f"{level}%")
    return get_brightness()


@tool("Make the screen brighter or dimmer by a relative amount. Positive = brighter, negative = dimmer. Default step is 10.")
def change_brightness(delta: int = 10):
    _run("brightnessctl", "set", f"{abs(delta)}%{'+' if delta >= 0 else '-'}")
    return get_brightness()
