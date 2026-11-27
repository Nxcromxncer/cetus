"""Drives a dedicated Chromium-family browser window (Brave / Chrome / Chromium) through the DevTools protocol.

The agent gets its OWN browser profile (~/.local/share/arch-agent/browser/<name>), so it never touches your
everyday profile. Sign in to YouTube, GitHub, LeetCode... once in that window and it is remembered.

How it "sees": SNAPSHOT_JS numbers every visible clickable/typeable element. The LLM picks a number and we
click its centre with real mouse events (move + click), so it works on any website without per-site code.
"""
import atexit, os, re, subprocess, time
from pathlib import Path
from urllib.parse import urlparse
import requests
import config

PORTS = {"brave": 9222, "chrome": 9223, "chromium": 9224}
PROFILE_ROOT = Path(os.path.expanduser("~/.local/share/arch-agent/browser"))
BLANK = ("about:blank", "chrome://newtab", "chrome://new-tab-page", "brave://newtab", "chrome-search://", "edge://newtab")


class BrowserUnavailable(RuntimeError):
    pass


SNAPSHOT_JS = r"""
(maxItems) => {
  const SEL = 'a[href],button,input:not([type=hidden]),textarea,select,summary,[role=button],[role=link],[role=tab],' +
    '[role=menuitem],[role=checkbox],[role=switch],[role=option],[role=combobox],[role=searchbox],[role=textbox],' +
    '[contenteditable=""],[contenteditable="true"],[onclick]';
  const vw = window.innerWidth, vh = window.innerHeight, items = [], seen = new Set();
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  function consider(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0' || cs.pointerEvents === 'none') return;
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), vw - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 1), vh - 1);
    const rootNode = el.getRootNode();
    const top = (rootNode.elementFromPoint ? rootNode : document).elementFromPoint(cx, cy);
    const host = rootNode.host;
    if (!top || !(el.contains(top) || top.contains(el) || (host && (host === top || host.contains(top))))) return;

    const tag = el.tagName.toLowerCase();
    const type = tag === 'input' ? (el.type || 'text') : '';
    let label = el.getAttribute('aria-label') || '';
    if (!label && el.labels && el.labels[0]) label = el.labels[0].innerText;
    if (!label) label = (type === 'submit' || type === 'button') ? el.value : (el.innerText || '');
    if (!label) label = el.placeholder || el.title || el.alt || el.getAttribute('name') || '';
    if (!label) { const img = el.querySelector('img[alt]'); if (img) label = img.alt; }
    label = clean(label).slice(0, 90);
    const isField = tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
    if (!label && !isField) return;

    let href = '';
    if (tag === 'a') {
      try { const u = new URL(el.href); href = (u.host === location.host ? '' : u.host) + u.pathname + (u.search.length < 40 ? u.search : ''); } catch (e) {}
      href = href.slice(0, 70);
    }
    const key = tag + '|' + label + '|' + href;
    if (seen.has(key)) return;
    seen.add(key);

    let role = tag === 'a' ? 'link' : (tag === 'button' || el.getAttribute('role') === 'button') ? 'button'
             : tag === 'input' ? 'input[' + type + ']' : (tag === 'textarea' ? 'textarea' : (el.getAttribute('role') || tag));
    let value = '';
    if (isField && type !== 'password' && type !== 'checkbox' && type !== 'radio' && tag !== 'select') value = clean(el.value || '').slice(0, 40);
    if (tag === 'select') value = clean(el.options && el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '');
    const checked = (type === 'checkbox' || type === 'radio') ? el.checked : null;
    const id = items.length + 1;
    el.setAttribute('data-agent-id', String(id));
    items.push({id, role, label, type, href, value, checked});
  }

  function walk(root) {
    for (const el of root.querySelectorAll('*')) {
      if (el.hasAttribute('data-agent-id')) el.removeAttribute('data-agent-id');
      if (el.shadowRoot) walk(el.shadowRoot);
      if (items.length < maxItems && el.matches(SEL)) consider(el);
    }
  }
  walk(document);
  return {title: document.title, url: location.href, y: Math.round(window.scrollY),
          max: Math.max(0, Math.round(document.documentElement.scrollHeight - vh)), items};
}
"""

MEDIA_JS = r"""
async (action) => {
  const vids = [...document.querySelectorAll('video, audio')];
  const v = vids.find(x => x.readyState > 0 && x.duration > 0) || vids[0];
  if (!v) return {error: 'no video or audio on this page'};
  const play = async () => { try { await v.play(); } catch (e) {} };
  if (action === 'play') await play();
  else if (action === 'pause') v.pause();
  else if (action === 'toggle') { if (v.paused) await play(); else v.pause(); }
  else if (action === 'mute') v.muted = true;
  else if (action === 'unmute') { v.muted = false; if (v.volume < 0.2) v.volume = 0.6; }
  else if (action === 'forward') v.currentTime = Math.min((v.duration || 1e9), v.currentTime + 10);
  else if (action === 'back') v.currentTime = Math.max(0, v.currentTime - 10);
  else if (action === 'restart') { v.currentTime = 0; await play(); }
  return {paused: v.paused, muted: v.muted, position_s: Math.round(v.currentTime), duration_s: Math.round(v.duration || 0), title: document.title};
}
"""


def format_snapshot(snap: dict) -> str:
    more = f", {snap['max'] - snap['y']}px more below" if snap["max"] - snap["y"] > 40 else ""
    lines = [f"Page: {snap['title'][:80]!r} | {snap['url'][:110]}", f"Scroll: {snap['y']}px of {snap['max']}px{more}"]
    for it in snap["items"]:
        s = f"[{it['id']}] {it['role']} \"{it['label']}\""
        if it["href"]:
            s += f" -> {it['href']}"
        if it["value"]:
            s += f" (value: {it['value']!r})"
        if it["checked"] is not None:
            s += " (checked)" if it["checked"] else " (unchecked)"
        lines.append(s)
    if not snap["items"]:
        lines.append("(no clickable elements visible; try browser_scroll or browser_read)")
    return "\n".join(lines)


class BrowserSession:
    def __init__(self, name: str, exe: str):
        self.name, self.exe = name, exe
        self.port = PORTS.get(name, 9222)
        self.profile = PROFILE_ROOT / name
        self._pw = self._browser = self.context = self.page = None
        self.labels: dict[int, tuple] = {}          # index -> (role, label, type) from the last snapshot

    # ---------- connection ----------
    def _cdp_alive(self) -> bool:
        s = requests.Session()
        s.trust_env = False                         # never route localhost through a proxy
        try:
            return s.get(f"http://127.0.0.1:{self.port}/json/version", timeout=0.6).ok
        except requests.RequestException:
            return False

    def _launch_browser(self):
        self.profile.mkdir(parents=True, exist_ok=True)
        cmd = [self.exe, f"--remote-debugging-port={self.port}", f"--user-data-dir={self.profile}",
               "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required",
               "--ozone-platform-hint=auto", *config.BROWSER_EXTRA_ARGS.split(), "about:blank"]
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            if self._cdp_alive():
                return
            time.sleep(0.25)
        raise BrowserUnavailable(
            f"{self.name} started but did not open its debugging port {self.port}. If an agent-browser window is "
            f"already open from an earlier run, close it and try again.")

    def ensure(self):
        if self._browser and self._browser.is_connected():
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserUnavailable("playwright is not installed (pip install playwright)")
        if not self._cdp_alive():
            self._launch_browser()
        if self._pw is None:
            self._pw = sync_playwright().start()
            atexit.register(self.close)
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        self.context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        self.page = None

    def close(self):
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

    @staticmethod
    def _visible(page) -> bool:
        try:
            return page.evaluate("document.visibilityState") == "visible"
        except Exception:
            return False

    def pages(self):
        self.ensure()
        pages = [p for p in self.context.pages if not p.is_closed()]
        return pages or [self.context.new_page()]

    def current_page(self):
        """The tab the user is actually looking at (they may have switched tabs by hand)."""
        pages = self.pages()
        if self.page in pages and self._visible(self.page):
            return self.page
        for p in reversed(pages):
            if self._visible(p):
                self.page = p
                return p
        self.page = self.page if self.page in pages else pages[-1]
        return self.page

    # ---------- navigation ----------
    def open(self, url: str = "", reuse_host: str | None = None) -> dict:
        page = self.current_page()
        if not url:
            page.bring_to_front()
            return {"url": page.url, "title": page.title(), "status": None}
        host = urlparse(page.url).hostname or ""
        reuse = page.url.startswith(BLANK) or bool(reuse_host and reuse_host in host)
        if not reuse:
            page = self.context.new_page()
        status = None
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            status = resp.status if resp else None
        except Exception as e:
            if "Timeout" not in type(e).__name__:
                raise
        page.bring_to_front()
        self.page = page
        return {"url": page.url, "title": page.title(), "status": status}

    def _settle(self, page):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        page.wait_for_timeout(400)

    # ---------- seeing ----------
    def snapshot(self, max_items: int = 60) -> dict:
        page = self.current_page()
        try:
            snap = page.evaluate(SNAPSHOT_JS, max_items)
        except Exception:                            # page was navigating
            self._settle(page)
            snap = page.evaluate(SNAPSHOT_JS, max_items)
        self.labels = {i["id"]: (i["role"], i["label"], i["type"]) for i in snap["items"]}
        return snap

    def read(self, max_chars: int = 3000) -> str:
        text = self.current_page().inner_text("body")
        return re.sub(r"\n\s*\n+", "\n", text).strip()[:max_chars]

    # ---------- acting ----------
    def _mouse_click(self, page, locator):
        locator.scroll_into_view_if_needed(timeout=3000)
        box = locator.bounding_box()
        if not box:
            raise RuntimeError("element is not visible")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        before = list(self.context.pages)
        page.mouse.move(x, y, steps=12)
        page.mouse.click(x, y)
        page.wait_for_timeout(600)          # pumps Playwright events (plain sleep would miss a new tab)
        new = [p for p in self.context.pages if p not in before and not p.is_closed()]
        if new:                                      # link opened a new tab: follow it
            self.page = new[-1]
            self._settle(self.page)
            self.page.bring_to_front()
        else:
            self._settle(page)

    def _element(self, index: int):
        page = self.current_page()
        loc = page.locator(f'[data-agent-id="{index}"]').first
        if loc.count() == 0:
            raise RuntimeError(f"element [{index}] is gone. Call browser_look again to get fresh numbers.")
        return page, loc

    def click(self, index: int) -> dict:
        page, loc = self._element(index)
        label = self.labels.get(index, ("", "", ""))[1]
        self._mouse_click(page, loc)
        cur = self.page if self.page and not self.page.is_closed() else page
        return {"clicked": label, "url": cur.url, "title": cur.title()}

    def click_locator(self, locator):
        self._mouse_click(self.current_page(), locator)

    def type_text(self, index: int, text: str, submit: bool = False) -> dict:
        role, label, kind = self.labels.get(index, ("", "", ""))
        if kind == "password":
            raise RuntimeError("that is a password field. I never type passwords; please type it yourself.")
        page, loc = self._element(index)
        self._mouse_click(page, loc)
        page = self.current_page()
        page.keyboard.press("Control+A")
        page.keyboard.type(text, delay=20)
        if submit:
            page.keyboard.press("Enter")
            self._settle(page)
        return {"typed": text, "into": label, "submitted": submit, "url": page.url}

    def press(self, key: str) -> dict:
        page = self.current_page()
        page.keyboard.press(key)
        self._settle(page)
        return {"pressed": key, "url": page.url}

    def scroll(self, direction: str, pages: int = 1) -> dict:
        page = self.current_page()
        vh = page.evaluate("window.innerHeight")
        if direction == "top":
            page.evaluate("window.scrollTo(0, 0)")
        elif direction == "bottom":
            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        else:
            page.mouse.move(400, 300)
            page.mouse.wheel(0, (1 if direction == "down" else -1) * int(vh * 0.8) * max(1, pages))
        page.wait_for_timeout(500)
        return {"scrolled": direction, "y": page.evaluate("Math.round(window.scrollY)")}

    def back(self) -> dict:
        page = self.current_page()
        page.go_back(wait_until="domcontentloaded", timeout=8000)
        return {"url": page.url, "title": page.title()}

    def tabs(self) -> list[dict]:
        cur = self.current_page()
        return [{"index": i, "title": p.title()[:60], "url": p.url[:90], "active": p == cur}
                for i, p in enumerate(self.pages())]

    def switch_tab(self, index: int) -> dict:
        pages = self.pages()
        if not 0 <= index < len(pages):
            raise RuntimeError(f"no tab {index}; there are {len(pages)} tabs (0..{len(pages) - 1})")
        pages[index].bring_to_front()
        self.page = pages[index]
        return {"active": index, "title": self.page.title(), "url": self.page.url}

    def close_tab(self) -> dict:
        page = self.current_page()
        page.close()
        self.page = None
        rest = self.pages()
        self.page = rest[-1]
        rest[-1].bring_to_front()
        return {"closed": True, "now_on": self.page.url}

    def media(self, action: str) -> dict:
        page = self.current_page()
        keys = {"next": "Shift+N", "previous": "Shift+P", "fullscreen": "f"}
        if action in keys:
            page.keyboard.press(keys[action])
            page.wait_for_timeout(800)
            return {"pressed": keys[action], "title": page.title()}
        return page.evaluate(MEDIA_JS, action)

    def wait_for_video(self, timeout_ms: int = 8000) -> bool:
        try:
            self.current_page().wait_for_selector("video", timeout=timeout_ms)
            return True
        except Exception:
            return False


_sessions: dict[str, BrowserSession] = {}
_current: BrowserSession | None = None


def session(name: str, exe: str) -> BrowserSession:
    global _current
    _current = _sessions.setdefault(name, BrowserSession(name, exe))
    return _current


def current() -> BrowserSession | None:
    return _current


def describe(index) -> str:
    """Label of an element from the last browser_look (used by the safety gate)."""
    try:
        role, label, kind = _current.labels.get(int(index), ("", "", ""))
        return f"{role} {label}"
    except Exception:
        return ""
