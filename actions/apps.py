"""Open and close applications. Reads installed apps from .desktop files, so it knows what you have."""
import configparser, difflib, glob, os, re, shlex, subprocess
import psutil
from core.registry import tool

_DIRS = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications"),
         "/var/lib/flatpak/exports/share/applications",
         os.path.expanduser("~/.local/share/flatpak/exports/share/applications")]


def _installed() -> dict[str, str]:
    """display name (lowercase) -> Exec command"""
    apps = {}
    for d in _DIRS:
        for path in glob.glob(f"{d}/*.desktop"):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(path, encoding="utf-8")
                e = cp["Desktop Entry"]
                if e.get("NoDisplay", "false") == "true" or e.get("Type") != "Application":
                    continue
                apps[e["Name"].lower()] = re.sub(r"%[a-zA-Z]", "", e["Exec"]).strip()
            except Exception:
                continue
    return apps


@tool("List the applications installed on this computer.")
def list_apps():
    return {"apps": sorted(_installed())[:150]}


@tool("Open / launch an application by its name, e.g. 'firefox', 'terminal', 'spotify', 'files'.", risk="medium")
def open_app(name: str):
    apps = _installed()
    key = name.lower()
    match = [key] if key in apps else (difflib.get_close_matches(key, apps, n=1, cutoff=0.5)
                                       or [k for k in apps if key in k][:1])
    if match:
        subprocess.Popen(shlex.split(apps[match[0]]), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened": match[0]}
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
