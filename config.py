"""Central config. Reads .env (if present) and environment variables."""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env(path: Path):
    """Tiny .env loader (KEY=VALUE per line). Real environment variables win over the file."""
    if not path.exists():
        return
    if path.stat().st_mode & 0o077:
        print(f"warning: {path} is readable by other users. Run: chmod 600 {path}", file=sys.stderr)
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------- LLM providers ----------
def active_providers() -> list[tuple[str, dict]]:
    """Providers in preferred order that are usable (have a key).
    'groq-fallback' is a second Groq model: Groq rate-limits per model, so it works as a cheap backup."""
    groq_key = env("GROQ_API_KEY")
    effort = env("GROQ_REASONING_EFFORT", "low")          # low | medium | high (gpt-oss models only)

    def groq(model: str) -> dict:
        p = {"base_url": "https://api.groq.com/openai/v1", "key": groq_key if model else "", "model": model}
        if model.startswith("openai/gpt-oss") and effort:
            p["reasoning_effort"] = effort
        return p

    primary = env("GROQ_MODEL", "openai/gpt-oss-120b")
    backup = env("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
    table = {
        "groq": groq(primary),
        "groq-fallback": groq("" if backup == primary else backup),
        "openrouter": {"base_url": "https://openrouter.ai/api/v1",
                       "key": env("OPENROUTER_API_KEY"),
                       "model": env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")},
        "ollama": {"base_url": env("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                   "key": "ollama",
                   "model": env("OLLAMA_MODEL", "llama3.2")},
    }
    order = [p.strip() for p in env("AGENT_PROVIDERS", "groq,groq-fallback,openrouter,ollama").split(",")]
    return [(n, table[n]) for n in order if n in table and table[n]["key"]]


MAX_STEPS = 14          # agent loop cap
HISTORY_TURNS = 8       # past user/assistant exchanges kept
LOG_PATH = os.path.expanduser("~/.local/share/arch-agent/actions.log")
PREFERRED_BROWSER = env("AGENT_BROWSER", "brave")      # brave | chrome | chromium

# ---------- Speech to text ----------
STT_BACKEND = env("STT_BACKEND", "groq")               # groq | local
GROQ_STT_MODEL = env("GROQ_STT_MODEL", "whisper-large-v3")      # or whisper-large-v3-turbo
LOCAL_STT_MODEL = env("LOCAL_STT_MODEL", "base")
LOCAL_STT_DEVICE = env("LOCAL_STT_DEVICE", "cpu")
STT_LANGUAGE = env("STT_LANGUAGE", "en")               # empty = auto-detect

# ---------- Voice activity detection ----------
VAD_THRESHOLD = float(env("VAD_THRESHOLD", "0.5"))
VAD_SILENCE_MS = int(env("VAD_SILENCE_MS", "700"))     # silence that ends an utterance
VAD_MIN_SPEECH_MS = int(env("VAD_MIN_SPEECH_MS", "300"))
VAD_PREROLL_MS = int(env("VAD_PREROLL_MS", "300"))     # audio kept from before speech was detected
MAX_UTTERANCE_S = int(env("MAX_UTTERANCE_S", "15"))
MIC_DEVICE = env("MIC_DEVICE") or None

# ---------- Text to speech ----------
TTS_BACKEND = env("TTS_BACKEND", "edge")                 # edge | espeak | off
TTS_VOICE = env("TTS_VOICE", "en-IN-NeerjaNeural")       # run: python -m edge_tts --list-voices
TTS_RATE = env("TTS_RATE", "+0%")                        # e.g. +10% faster, -10% slower
ESPEAK_VOICE = env("ESPEAK_VOICE", "en-us")              # offline fallback voice (hi for Hindi)
TTS_DEBUG = env("TTS_DEBUG") == "1"                      # print what the speaker is doing
SPEAKER_DEVICE = env("SPEAKER_DEVICE") or None           # sounddevice output index/name; see: python -m sounddevice

# ---------- Browser control ----------
BROWSER_CONTROL = env("BROWSER_CONTROL", "1") != "0"     # 0 = plain launch only (no click/type control)
BROWSER_EXTRA_ARGS = env("BROWSER_EXTRA_ARGS")           # extra Chromium flags, space separated
GITHUB_USER = env("GITHUB_USER")                         # your GitHub username (lets "open repo X" find your repos)
