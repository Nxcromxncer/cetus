"""Text to speech.

Backends (TTS_BACKEND):
  edge    Microsoft neural voices via edge-tts. Natural sounding, needs internet, no API key.
  espeak  Offline, robotic, but instant and always works once espeak-ng is installed.
  off     Text only.
If the chosen backend fails, the other one is tried automatically.

say() blocks until playback is finished. The mic stream is only read again afterwards
(Listener.listen drops everything captured meanwhile), so the agent never hears itself.
"""
import os, re, shutil, subprocess, sys, tempfile, threading, time, unicodedata
import config

# External players are only a fallback. stdin is closed and a timeout is enforced so they can never hang the agent.
PLAYERS = [("mpv", ["--no-video", "--no-terminal", "--really-quiet"]),
           ("ffplay", ["-nodisp", "-autoexit", "-nostdin", "-loglevel", "quiet"]),
           ("mpg123", ["-q"])]
PLAY_PAD = 8          # seconds of slack on top of the audio length before playback is declared stuck
EDGE_BYTES_PER_SEC = 6000   # edge-tts mp3 is ~48 kbps
RATE = 24000
HINT = ("  [tts] Could not speak. Try:  pip install -r requirements.txt  &&  sudo pacman -S espeak-ng\n"
        "        Details: TTS_DEBUG=1 python tts_test.py     (or set TTS_BACKEND=off in .env to silence this)")


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
    def _dbg(self, *msg):
        if config.TTS_DEBUG:
            print("  [tts]", *msg)

    def _play_internal(self, path: str):
        """Decode the mp3 with miniaudio and play it through sounddevice (same audio stack as the mic)."""
        import miniaudio, numpy as np, sounddevice as sd
        dec = miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.SIGNED16,
                                    nchannels=1, sample_rate=RATE)
        data = np.frombuffer(dec.samples, dtype=np.int16).copy()
        secs = len(data) / RATE
        self._dbg(f"internal playback, {secs:.1f}s, device={config.SPEAKER_DEVICE or 'default'}")
        done, err = threading.Event(), []

        def run():
            try:
                sd.play(data, RATE, device=config.SPEAKER_DEVICE)
                sd.wait()
            except Exception as e:                      # PortAudioError etc.
                err.append(e)
            finally:
                done.set()

        threading.Thread(target=run, daemon=True).start()
        if not done.wait(secs + PLAY_PAD):
            sd.stop()
            raise RuntimeError("audio output did not finish (output device stuck?)")
        if err:
            raise RuntimeError(f"audio output error: {err[0]}")

    def _play_external(self, path: str):
        timeout = os.path.getsize(path) / EDGE_BYTES_PER_SEC * 1.5 + PLAY_PAD
        errors = []
        for name, args in PLAYERS:
            if not shutil.which(name):
                continue
            self._dbg(f"external player {name}, timeout {timeout:.0f}s")
            quiet = None if config.TTS_DEBUG else subprocess.DEVNULL
            try:
                subprocess.run([name, *args, path], stdin=subprocess.DEVNULL, stdout=quiet, stderr=quiet,
                               check=True, timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                errors.append(f"{name} hung for over {timeout:.0f}s")
            except (subprocess.SubprocessError, OSError) as e:
                errors.append(f"{name}: {e}")
        raise RuntimeError("; ".join(errors) or "no audio player installed")

    def _play(self, path: str):
        try:
            return self._play_internal(path)
        except Exception as e:                           # missing module, no device, stuck device...
            self._dbg(f"internal playback failed: {e}")
            internal_error = str(e)
        try:
            return self._play_external(path)
        except RuntimeError as e:
            raise RuntimeError(f"playback failed (internal: {internal_error}; external: {e})")

    def _edge(self, text: str):
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            r = subprocess.run(
                [sys.executable, "-m", "edge_tts", f"--voice={config.TTS_VOICE}", f"--rate={config.TTS_RATE}",
                 "--no-progress", f"--text={text}", f"--write-media={path}"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
            if r.returncode != 0 or os.path.getsize(path) == 0:
                tail = (r.stderr.strip().splitlines() or ["no audio produced"])[-1]
                raise RuntimeError(f"edge-tts failed: {tail[:150]}")
            self._dbg(f"synthesized {os.path.getsize(path)} bytes")
            self._play(path)
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
                       input=text, text=True, check=True, timeout=60,
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
