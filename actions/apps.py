"""Open and close applications. Reads installed apps from .desktop files, so it knows what you have."""
import configparser, difflib, glob, os, re, shlex, shutil, subprocess
import psutil
from core.registry import tool

_DIRS = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications"),
         "/var/lib/flatpak/exports/share/applications",
         os.path.expanduser("~/.local/share/flatpak/exports/share/applications")]


def _installed() -> dict[str, tuple[str, bool]]:
    """display name (lowercase) -> (Exec command, needs_terminal)"""
    apps = {}
    for d in _DIRS:
        for path in glob.glob(f"{d}/*.desktop"):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(path, encoding="utf-8")
                e = cp["Desktop Entry"]
                if e.get("NoDisplay", "false") == "true" or e.get("Type") != "Application":
                    continue
                apps[e["Name"].lower()] = (re.sub(r"%[a-zA-Z]", "", e["Exec"]).strip(),
                                           e.get("Terminal", "false").lower() == "true")
            except Exception:
                continue
    return apps


def _match(key: str, names: list[str]):
    """Exact, then prefix, then substring (3+ chars), then a strict fuzzy match."""
    if key in names:
        return key
    cands = [n for n in names if n.startswith(key)]
    if not cands and len(key) >= 3:
        cands = [n for n in names if key in n]
    if cands:
        return min(cands, key=len)
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.8)
    return close[0] if close else None


@tool("List the desktop applications installed on this computer.")
def list_apps():
    return {"apps": sorted(_installed())[:150]}


@tool("Open / launch a desktop (GUI) application by name, e.g. 'firefox', 'files', 'spotify'. "
      "Not for command-line programs; use open_terminal for those.", risk="medium")
def open_app(name: str):
    apps = _installed()
    key = name.strip().lower()
    m = _match(key, list(apps)) if key else None
    if m:
        cmd, needs_terminal = apps[m]
        if needs_terminal:
            from skills.terminal import open_terminal
            return open_terminal(command=cmd)
        subprocess.Popen(shlex.split(cmd), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened": m}
    if key and shutil.which(key.split()[0]):
        return {"error": f"'{name}' is a command-line program, not a desktop app. "
                         f"Use open_terminal with command='{key}' to run it in a terminal window."}
    return {"error": f"no installed app matches '{name}'"}


@tool("Close / quit a running application by name.", risk="medium")
def close_app(name: str):
    key, killed = name.lower(), 0
    me = os.getuid()
    for p in psutil.process_iter(["name", "uids"]):
        try:
            if p.info["uids"].real == me and key in (p.info["name"] or "").lower():
                p.terminate(); killed += 1
        except psutil.Error:
            pass
    return {"closed_processes": killed} if killed else {"error": f"'{name}' is not running"}
