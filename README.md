# arch-agent

Phase 1: text-only brain + tool registry + safety gate for Arch Linux.

## Setup
    sudo pacman -S python python-psutil python-requests brightnessctl yt-dlp pipewire-pulse wireplumber ollama
    ollama serve &            # or: sudo systemctl enable --now ollama
    ollama pull llama3.2
    python main.py

Use another model/provider: AGENT_BASE_URL, AGENT_MODEL, AGENT_API_KEY.

Browser (Brave is AUR): `yay -S brave-bin`. Choose default browser: `AGENT_BROWSER=chrome`.

## Add a capability
Drop a file in `actions/` or `skills/`:

    from core.registry import tool
    @tool("What it does and when to use it.", risk="low")
    def my_tool(arg: int): ...

Restart. The brain picks it up automatically.

## Roadmap
1. (done) brain, registry, safety, volume/brightness/battery/apps/shell
2. memory.py (SQLite facts + preferences)
3. audio/: Silero VAD -> faster-whisper STT -> Piper TTS
4. skills: news, calendar, web search
5. tool retriever (embeddings) once >30 tools
6. wake word, computer-use fallback (screenshots)
