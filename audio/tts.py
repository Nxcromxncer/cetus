"""Text to speech.

Backends (TTS_BACKEND):
  edge    Microsoft neural voices via edge-tts. Natural sounding, needs internet, no API key.
  espeak  Offline, robotic, but instant and always works once espeak-ng is installed.
  off     Text only.
If the chosen backend fails, the other one is tried automatically.

say() blocks until playback is finished. The mic stream is only read again afterwards
(Listener.listen drops everything captured meanwhile), so the agent never hears itself.
"""
import os, re, shutil, subprocess, sys, tempfile, time, unicodedata
import config

PLAYERS = [("mpv", ["--no-video", "--really-quiet"]),
           ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
           ("mpg123", ["-q"])]
HINT = ("  [tts] Could not speak. Fix with:  sudo pacman -S mpv espeak-ng  &&  pip install edge-tts\n"
        "        (or set TTS_BACKEND=off in .env to silence this)")


def clean_for_speech(text: str, max_chars: int = 500) -> str:
    """Strip things that sound bad when read aloud: markdown, code blocks, URLs, emoji."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " link ", text)
    text = re.sub(r"[`*_#>~|]", "", text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Cs", "Co", "Cn"))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:                       # cut at a sentence end if possible
        cut = text[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:end + 1] if end > 100 else cut
    return text


class Speaker:
    def __init__(self):
        self.backend = config.TTS_BACKEND
        self._warned = False

    # ---------- backends ----------
    def _edge(self, text: str):
        player = next(((n, a) for n, a in PLAYERS if shutil.which(n)), None)
        if not player:
            raise RuntimeError("no audio player installed (sudo pacman -S mpv)")
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            r = subprocess.run(
                [sys.executable, "-m", "edge_tts", f"--voice={config.TTS_VOICE}", f"--rate={config.TTS_RATE}",
                 "--no-progress", f"--text={text}", f"--write-media={path}"],
                capture_output=True, text=True, timeout=20)
            if r.returncode != 0 or os.path.getsize(path) == 0:
                tail = (r.stderr.strip().splitlines() or ["no audio produced"])[-1]
                raise RuntimeError(f"edge-tts failed: {tail[:150]}")
            subprocess.run([player[0], *player[1], path], check=True, timeout=90,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _espeak(self, text: str):
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise RuntimeError("espeak-ng not installed (sudo pacman -S espeak-ng)")
        subprocess.run([exe, "-v", config.ESPEAK_VOICE, "-s", "165", "--stdin"],
                       input=text, text=True, check=True, timeout=90,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------- public ----------
    def say(self, text: str) -> bool:
        """Speak text and block until done. Returns False if nothing could be spoken."""
        text = clean_for_speech(text)
        if not text or self.backend == "off":
            return False
        errors = []
        for name in [self.backend] + [b for b in ("edge", "espeak") if b != self.backend]:
            try:
                getattr(self, f"_{name}")(text)
                time.sleep(0.25)               # let the room echo die down before the mic is read again
                return True
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                errors.append(f"{name}: {e}")
        if not self._warned:
            self._warned = True
            print("  [tts] " + " | ".join(errors) + "\n" + HINT)
        return False
