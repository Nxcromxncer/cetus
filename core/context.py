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
        "The user's words come from speech recognition and may contain mistakes; interpret them sensibly.\n"
        "Never claim an action succeeded unless the tool result says so. If a tool fails, say so briefly.\n"
        "To open a terminal window, or to run a command-line program the user can see (htop, zplay, ...), use open_terminal. "
        "open_app is only for desktop GUI apps.\n"
        "You cannot install software or use sudo. If something must be installed, tell the user the exact command to run themselves.\n\n"
        "Current system state:\n- " + "\n- ".join(facts)
    )
