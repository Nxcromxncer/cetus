"""Builds the system prompt: who the agent is + live facts about this machine."""
import os, platform, time
from core import registry


def _safe(tool_name):
    try:
        return registry.call(tool_name, {})
    except Exception:
        return {}


def build_system_prompt() -> str:
    facts = [
        f"Time: {time.strftime('%A %d %B %Y, %H:%M')}",
        f"OS: Arch Linux ({platform.release()}), host {platform.node()}",
        f"Desktop: {os.getenv('XDG_CURRENT_DESKTOP', 'unknown')} / session {os.getenv('XDG_SESSION_TYPE', 'unknown')}",
        f"User: {os.getenv('USER', 'unknown')}",
        f"Battery: {_safe('get_battery')}",
        f"Volume: {_safe('get_volume')}",
        f"Brightness: {_safe('get_brightness')}",
        f"Browsers: {_safe('list_browsers')}",
    ]
    return (
        "You are a voice-controlled assistant that controls this Arch Linux computer.\n"
        "Understand what the user wants (they speak naturally, not in commands) and use the tools to do it. "
        "Chain several tool calls when a task needs multiple steps. If no tool is needed, just answer.\n"
        "Replies are spoken aloud: keep them to one or two short sentences, no markdown.\n"
        "Never claim an action succeeded unless the tool result says so. If a tool fails, say so briefly.\n\n"
        "Current system state:\n- " + "\n- ".join(facts)
    )
