"""Text REPL (no mic needed). For voice use main_voice.py."""
import config
from core import registry
from core.brain import Brain


def confirm(prompt: str) -> bool:
    return input(f"  [confirm] {prompt} (y/N) ").strip().lower() in ("y", "yes")


def main():
    if not config.active_providers():
        raise SystemExit("No LLM provider configured. Copy .env.example to .env and set GROQ_API_KEY.")
    registry.load_plugins()
    print(f"Loaded tools: {', '.join(registry.TOOLS)}\n"
          f"Providers: {', '.join(n for n, _ in config.active_providers())}. Type 'quit' to exit.\n")
    brain = Brain(confirm=confirm)
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("quit", "exit"):
            break
        if text:
            try:
                print(f"agent> {brain.run(text)}\n")
            except Exception as e:
                print(f"  [error] {e}\n")


if __name__ == "__main__":
    main()
