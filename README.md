# arch-agent v2

Voice-controlled agent for Arch Linux: LLM brain (Groq / OpenRouter / Ollama), tools, VAD + STT.

## Setup
```bash
sudo pacman -S python portaudio brightnessctl tmux yt-dlp kitty    # kitty = any terminal you like
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env && chmod 600 .env       # then put your GROQ_API_KEY in .env
python main.py                               # text mode
python mic_test.py                           # check mic + VAD + STT
python main_voice.py                         # voice mode
```
Get a key: https://console.groq.com/keys

## Keys and git
`.env` is in `.gitignore`. Before your first commit run `git status` and confirm `.env` is NOT listed.
If a key was ever committed or pasted somewhere public, revoke it in the provider console and make a new one.

## Providers
`AGENT_PROVIDERS=groq,openrouter,ollama` is the order tried. A provider without a key is skipped.
On 429/5xx the agent retries once, then falls through to the next provider.

## Voice
Mic -> Silero VAD (finds start/end of speech) -> STT -> brain.
- `STT_BACKEND=groq` (default): Whisper via Groq API.
- `STT_BACKEND=local`: `pip install faster-whisper`, set `LOCAL_STT_MODEL=base` (or small).
- Tune VAD with `VAD_THRESHOLD` (higher = less sensitive) and `VAD_SILENCE_MS` (pause that ends a sentence).
- Risky actions (shell commands) need a spoken "yes"; the prompt is shown on screen until TTS is added.

## Add a capability
Drop a file in `actions/` or `skills/`:
```python
from core.registry import tool
@tool("What it does and when to use it.", risk="low")
def my_tool(arg: int): ...
```

## Roadmap
1. done: brain, registry, safety, system tools, browser, terminal, providers, VAD, STT
2. TTS (Piper) + mute mic while speaking + voice "stop"
3. memory (SQLite), zplay/music control, news/calendar/search skills
4. wake word, tool retriever, browser control via CDP, computer-use fallback
