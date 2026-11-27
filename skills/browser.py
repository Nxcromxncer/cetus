"""Open sites, search and play YouTube in a Chromium-family browser (Brave, Chrome, Chromium).

By default pages open in the agent's own controlled browser window (see core/browserctl.py), so the
browser_* tools can then click, type and scroll on them. If Playwright is missing or BROWSER_CONTROL=0,
it falls back to launching a normal window (no click/type control).
"""
import re, shutil, subprocess
from typing import Literal
from urllib.parse import quote_plus, urlparse
import requests
import config
from core import browserctl
from core.registry import tool

BROWSERS = {
    "brave": ["brave", "brave-browser", "brave-browser-stable"],
    "chrome": ["google-chrome-stable", "google-chrome"],
    "chromium": ["chromium", "chromium-browser"],
}
Browser = Literal["brave", "chrome", "chromium", "default"]

SITES = {
    "github": "github.com", "kaggle": "kaggle.com", "leetcode": "leetcode.com", "youtube": "youtube.com",
    "google": "google.com", "gmail": "mail.google.com", "reddit": "reddit.com", "twitter": "x.com", "x": "x.com",
    "stackoverflow": "stackoverflow.com", "huggingface": "huggingface.co", "claude": "claude.ai",
    "chatgpt": "chatgpt.com", "linkedin": "linkedin.com", "wikipedia": "wikipedia.org",
    "maps": "maps.google.com", "netflix": "netflix.com", "amazon": "amazon.com", "drive": "drive.google.com",
    "calendar": "calendar.google.com", "colab": "colab.research.google.com", "geeksforgeeks": "geeksforgeeks.org",
}
SEARCH = {
    "google": "https://www.google.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "brave": "https://search.brave.com/search?q=",
    "youtube": "https://www.youtube.com/results?search_query=",
}
_warned = False


def _installed() -> dict[str, str]:
    found = {}
    for name, exes in BROWSERS.items():
        for exe in exes:
            if path := shutil.which(exe):
                found[name] = path
                break
    return found


def _find(browser: str):
    installed = _installed()
    if browser == "default":
        order = [config.PREFERRED_BROWSER] + [b for b in BROWSERS if b != config.PREFERRED_BROWSER]
        for b in order:
            if b in installed:
                return b, installed[b]
        return None, None
    return (browser, installed[browser]) if browser in installed else (None, None)


def _normalize(target: str) -> str:
    t = target.strip()
    if not t:
        return ""
    if "://" in t:
        if urlparse(t).scheme not in ("http", "https"):
            raise ValueError("only http/https URLs are allowed")
        return t
    if re.match(r"^(javascript|file|data|about|chrome|view-source):", t, re.I):
        raise ValueError("blocked URL scheme")
    key = t.lower().replace(" ", "")
    if key in SITES:
        return "https://" + SITES[key]
    if "." in t and " " not in t:
        return "https://" + t
    return f"https://www.{key}.com"


def _launch(browser: str, url: str, reuse_host: str | None = None):
    """Open url. Returns (browser_name, error_dict_or_None, controlled_session_or_None)."""
    global _warned
    name, exe = _find(browser)
    if not exe:
        return None, {"error": f"browser '{browser}' not found", "installed": list(_installed())}, None
    if config.BROWSER_CONTROL:
        try:
            sess = browserctl.session(name, exe)
            sess.open(url, reuse_host=reuse_host)
            return name, None, sess
        except Exception as e:
            if not _warned:
                _warned = True
                print(f"  [browser] control unavailable ({str(e)[:140]}); opening a plain window instead")
    subprocess.Popen([exe] + (["--new-tab", url] if url else []), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return name, None, None


@tool("List the Chromium-based browsers installed (brave, chrome, chromium).")
def list_browsers():
    return {"installed": list(_installed()), "preferred": config.PREFERRED_BROWSER}


@tool("Open a browser, optionally at a website. 'url' can be a full URL, a domain, or a well-known site name like "
      "'github', 'kaggle', 'leetcode'. Leave url empty to just open the browser. After opening, use browser_look "
      "to click or type on the page.", risk="medium")
def open_url(url: str = "", browser: Browser = "default"):
    try:
        target = _normalize(url)
    except ValueError as e:
        return {"error": str(e)}
    name, err, sess = _launch(browser, target)
    return err or {"opened": target or "(browser only)", "browser": name, "controllable": sess is not None}


@tool("Search the web in the browser (results page). engine can be google, duckduckgo, brave or youtube. "
      "Use for 'search for X'. For PLAYING a song or video use youtube_play instead.", risk="medium")
def web_search(query: str, engine: Literal["google", "duckduckgo", "brave", "youtube"] = "google",
               browser: Browser = "default"):
    name, err, sess = _launch(browser, SEARCH[engine] + quote_plus(query))
    return err or {"searched": query, "engine": engine, "browser": name, "controllable": sess is not None}


def _youtube_first(query: str):
    """Return (video_id, title) of the first YouTube search result."""
    if shutil.which("yt-dlp"):
        try:
            out = subprocess.run(
                ["yt-dlp", "--no-warnings", "--flat-playlist", "--print", "%(id)s\t%(title)s", f"ytsearch1:{query}"],
                capture_output=True, text=True, timeout=25).stdout.strip()
            if out:
                vid, _, title = out.splitlines()[0].partition("\t")
                return vid, title
        except subprocess.SubprocessError:
            pass
    r = requests.get("https://www.youtube.com/results", params={"search_query": query},
                     headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}, timeout=15)
    m = re.search(r'"videoId":"([\w-]{11})"', r.text)
    return (m.group(1), None) if m else (None, None)


@tool("Play a song or video: finds the first YouTube result for the query and starts playing it. "
      "Use for 'play X', 'play X on YouTube', music requests. Afterwards media_control can pause/skip "
      "and youtube_subscribe can subscribe to the channel.", risk="medium")
def youtube_play(query: str, browser: Browser = "default"):
    try:
        vid, title = _youtube_first(query)
    except requests.RequestException as e:
        return {"error": f"could not reach YouTube: {e}"}
    if not vid:
        return {"error": f"no YouTube result found for '{query}'"}
    name, err, sess = _launch(browser, f"https://www.youtube.com/watch?v={vid}", reuse_host="youtube.com")
    if err:
        return err
    state = {}
    if sess:                                              # make sure it is really playing
        sess.wait_for_video()
        state = sess.media("play")
        if state.get("paused"):                           # e.g. the player ignored play(): use YouTube's own shortcut
            sess.press("k")
            state = sess.media("status")
    return {"playing": title or query, "video_id": vid, "browser": name,
            "controllable": sess is not None, "paused": state.get("paused")}
