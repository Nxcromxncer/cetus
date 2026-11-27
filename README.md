# arch-agent v2

Voice-controlled agent for Arch Linux: LLM brain (Groq / OpenRouter / Ollama), tools, VAD + STT.

## Setup
```bash
sudo pacman -S python portaudio brightnessctl tmux yt-dlp kitty espeak-ng    # kitty = any terminal you like
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # includes playwright (no browser download needed)

cp .env.example .env && chmod 600 .env       # then put your GROQ_API_KEY in .env
python main.py                               # text mode
python mic_test.py                           # check mic + VAD + STT
python tts_test.py                           # check the agent can speak
python main_voice.py                         # voice mode
```
Get a key: https://console.groq.com/keys

## Keys and git
`.env` is in `.gitignore`. Before your first commit run `git status` and confirm `.env` is NOT listed.
If a key was ever committed or pasted somewhere public, revoke it in the provider console and make a new one.

## Providers
`AGENT_PROVIDERS=groq,groq-fallback,openrouter,ollama` is the order tried (`groq-fallback` = a second Groq model, `GROQ_FALLBACK_MODEL`). A provider without a key is skipped.
On 429/5xx the agent retries once, then falls through to the next provider.

## Voice
Mic -> Silero VAD (finds start/end of speech) -> STT -> brain.
- `STT_BACKEND=groq` (default): Whisper via Groq API.
- `STT_BACKEND=local`: `pip install faster-whisper`, set `LOCAL_STT_MODEL=base` (or small).
- Tune VAD with `VAD_THRESHOLD` (higher = less sensitive) and `VAD_SILENCE_MS` (pause that ends a sentence).
- Replies are spoken with `audio/tts.py` (edge-tts voices, espeak-ng offline fallback). The mic is not read while the agent speaks, so it can't hear itself.
- Risky actions (shell commands) need a spoken "yes"; the prompt is shown on screen until TTS is added.

## Browser control (new)
The agent drives its **own** Brave/Chrome window (separate profile, so your everyday profile is never touched).
- First run: it opens that window. **Sign in once** to YouTube / GitHub / LeetCode there; logins are remembered
  in `~/.local/share/arch-agent/browser/`.
- How it works: `browser_look` numbers every visible clickable/typeable element, the model picks a number,
  and the code clicks it with real mouse events (`browser_click`), types (`browser_type`), scrolls, reads, switches tabs.
  Shortcuts: `youtube_play`, `youtube_subscribe`, `media_control` (pause / next / mute...), `github_repo`.
- Try: "open brave and play mango shake", "subscribe to this channel", "pause", "open leetcode",
  "open my arch-agent repo on github" (set `GITHUB_USER` in `.env`), "search github for playwright and open the first result".
- Safety: clicks on buttons like Delete / Buy / Pay need a spoken "yes"; passwords are never typed; page text is
  treated as untrusted data. Set `BROWSER_CONTROL=0` to go back to plain window launching.
- It listens on `127.0.0.1` only (ports 9222 brave, 9223 chrome, 9224 chromium).
- If Brave opens but control fails: close any agent-browser window left from an earlier run and retry.

## Add a capability
Drop a file in `actions/` or `skills/`:
```python
from core.registry import tool
@tool("What it does and when to use it.", risk="low")
def my_tool(arg: int): ...
```

## Roadmap
1. done: brain, registry, safety, system tools, browser, terminal, providers, VAD, STT, TTS
2. voice "stop"/barge-in (interrupt while it is speaking), optional Piper for fully offline TTS
3. memory (SQLite), zplay/music control, news/calendar/search skills
4. wake word, tool retriever (34 tools now), computer-use fallback (screenshots + OS-level mouse for non-browser apps)

## Troubleshooting voice output
`TTS_DEBUG=1 python tts_test.py` shows each step. Playback uses sounddevice (no external player); mpv/ffplay/mpg123
are only a fallback and are killed if they hang. If you hear nothing, test the basics: `espeak-ng "hello"`,
`wpctl status` (is the right Sink the default?), and set `SPEAKER_DEVICE` (see `python -m sounddevice`).
