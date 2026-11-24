"""Terminal skills.

- run_shell:       run a command in the background and capture its output (no window).
- open_terminal:   open a real, visible, interactive terminal window.
- terminal_send / terminal_read / terminal_interrupt: type into that terminal and read what it shows.

The visible terminal is attached to a tmux session named "agent", so the agent can both
type into it AND read the output back (observe step of the agent loop). You can also type in it yourself.
Without tmux, open_terminal still opens a window, but the agent can't type into it afterwards.
"""
import os, shutil, subprocess, time
from core.registry import tool

SESSION = "agent"

# name -> how to prefix a program to run inside the terminal
TERMINALS = {
    "kitty": ["kitty"], "alacritty": ["alacritty", "-e"], "foot": ["foot"],
    "wezterm": ["wezterm", "start", "--"], "ghostty": ["ghostty", "-e"],
    "gnome-terminal": ["gnome-terminal", "--"], "konsole": ["konsole", "-e"],
    "xfce4-terminal": ["xfce4-terminal", "-x"], "terminator": ["terminator", "-x"],
    "xterm": ["xterm", "-e"], "tilix": ["tilix", "-e"], "lxterminal": ["lxterminal", "-e"],
    "qterminal": ["qterminal", "-e"], "mate-terminal": ["mate-terminal", "-x"], "st": ["st", "-e"],
    "urxvt": ["urxvt", "-e"], "sakura": ["sakura", "-e"], "terminology": ["terminology", "-e"],
    "rio": ["rio", "-e"], "cool-retro-term": ["cool-retro-term", "-e"],
}


def _find_terminal():
    env = os.getenv("TERMINAL", "").split()
    if env and (exe := shutil.which(env[0])):
        base = os.path.basename(exe)
        return base, TERMINALS.get(base, [exe, "-e"])
    try:   # the terminal this agent was started from is the best guess
        import psutil
        for p in psutil.Process().parents():
            if p.name() in TERMINALS and shutil.which(p.name()):
                return p.name(), TERMINALS[p.name()]
    except Exception:
        pass
    for name, prefix in TERMINALS.items():
        if shutil.which(name):
            return name, prefix
    return None, None


def _tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _session_ready():
    if not shutil.which("tmux"):
        return "tmux is not installed (sudo pacman -S tmux)"
    if _tmux("has-session", "-t", SESSION).returncode != 0:
        return "no agent terminal is open; call open_terminal first"
    return None


@tool("Run a shell command in the background (no window) and return its output. Use for quick non-interactive "
      "checks (files, git, pacman queries). For anything the user wants to SEE or interact with, use open_terminal.",
      risk="high")
def run_shell(command: str, timeout: int = 30):
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout}s"}
    return {"exit_code": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-1000:]}


@tool("Open a new visible, interactive terminal window. Optionally start in a folder (cwd) and run a command in it. "
      "Use when the user says 'open a terminal' or wants to run something they can watch (htop, a server, an install).",
      risk="medium")
def open_terminal(command: str = "", cwd: str = ""):
    name, prefix = _find_terminal()
    if not prefix:
        return {"error": "no terminal emulator found. Install one (e.g. sudo pacman -S kitty) or start the agent with TERMINAL=<your-terminal> python main.py"}
    workdir = os.path.expanduser(cwd or "~")
    if not os.path.isdir(workdir):
        return {"error": f"folder not found: {workdir}"}
    shell = os.environ.get("SHELL", "/bin/bash")

    if shutil.which("tmux"):
        if _tmux("has-session", "-t", SESSION).returncode == 0:
            if cwd:
                _tmux("new-window", "-t", SESSION, "-c", workdir)
        else:
            r = _tmux("new-session", "-d", "-s", SESSION, "-c", workdir)
            if r.returncode:
                return {"error": f"tmux failed: {r.stderr.strip()}"}
        argv, mode = prefix + ["tmux", "attach", "-t", SESSION], "tmux"
        if command:
            _tmux("send-keys", "-t", SESSION, "-l", command)
            _tmux("send-keys", "-t", SESSION, "Enter")
    else:
        argv = prefix + (["bash", "-lc", f"{command}; exec {shell}"] if command else [shell])
        mode = "plain"

    subprocess.Popen(argv, cwd=workdir, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"terminal": name, "mode": mode, "ran": command or None}


@tool("Type a command into the open agent terminal, press Enter, wait briefly, and return what the terminal now shows. "
      "Call open_terminal first.", risk="high")
def terminal_send(command: str, wait: int = 1):
    if err := _session_ready():
        return {"error": err}
    _tmux("send-keys", "-t", SESSION, "-l", command)
    _tmux("send-keys", "-t", SESSION, "Enter")
    time.sleep(max(0, min(wait, 10)))
    return terminal_read(20)


@tool("Read the latest lines currently shown in the open agent terminal.")
def terminal_read(lines: int = 40):
    if err := _session_ready():
        return {"error": err}
    out = _tmux("capture-pane", "-p", "-t", SESSION, "-S", f"-{max(1, min(lines, 200))}").stdout
    return {"output": out.rstrip()[-3000:]}


@tool("Stop the program currently running in the agent terminal (sends Ctrl+C).", risk="medium")
def terminal_interrupt():
    if err := _session_ready():
        return {"error": err}
    _tmux("send-keys", "-t", SESSION, "C-c")
    return {"interrupted": True}
