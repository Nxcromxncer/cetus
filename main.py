"""Text REPL. Later, replace input() with VAD+STT and print() with TTS; nothing else changes."""
from core import registry
from core.brain import Brain


def confirm(prompt: str) -> bool:
    return input(f"  [confirm] {prompt} (y/N) ").strip().lower() in ("y", "yes")


def main():
    registry.load_plugins()
    print(f"Loaded tools: {', '.join(registry.TOOLS)}\nType 'quit' to exit.\n")
    brain = Brain(confirm=confirm)
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("quit", "exit"):
            break
        if text:
            print(f"agent> {brain.run(text)}\n")


if __name__ == "__main__":
    main()
