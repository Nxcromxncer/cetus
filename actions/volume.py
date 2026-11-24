"""Volume control via PipeWire's wpctl (default on Arch)."""
import re, subprocess
from typing import Literal
from core.registry import tool

SINK = "@DEFAULT_AUDIO_SINK@"


def _run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


@tool("Get the current speaker volume (0-100) and whether it is muted.")
def get_volume():
    out = _run("wpctl", "get-volume", SINK)           # "Volume: 0.45 [MUTED]"
    m = re.search(r"([\d.]+)", out)
    return {"volume": round(float(m.group(1)) * 100), "muted": "MUTED" in out}


@tool("Set the speaker volume to an exact level from 0 to 100.")
def set_volume(level: int):
    level = max(0, min(100, level))
    _run("wpctl", "set-volume", "-l", "1.0", SINK, f"{level}%")
    return get_volume()


@tool("Make the volume louder or quieter by a relative amount. Positive delta = louder, negative = quieter. Default step is 10.")
def change_volume(delta: int = 10):
    sign = "+" if delta >= 0 else "-"
    _run("wpctl", "set-volume", "-l", "1.0", SINK, f"{abs(delta)}%{sign}")
    return get_volume()


@tool("Mute, unmute, or toggle mute of the speakers.")
def set_mute(state: Literal["on", "off", "toggle"]):
    _run("wpctl", "set-mute", SINK, {"on": "1", "off": "0", "toggle": "toggle"}[state])
    return get_volume()
