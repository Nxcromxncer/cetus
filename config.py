"""Central config. Override with environment variables."""
import os

# Any OpenAI-compatible endpoint works: Ollama, llama.cpp server, vLLM, cloud APIs.
BASE_URL = os.getenv("AGENT_BASE_URL", "http://localhost:11434/v1")   # Ollama default
MODEL = os.getenv("AGENT_MODEL", "llama3.2")                        # needs tool-calling support
API_KEY = os.getenv("AGENT_API_KEY", "ollama")

MAX_STEPS = 10          # agent loop cap
HISTORY_TURNS = 8       # past user/assistant exchanges kept
LOG_PATH = os.path.expanduser("~/.local/share/arch-agent/actions.log")

PREFERRED_BROWSER = os.getenv("AGENT_BROWSER", "brave")   # brave | chrome | chromium
