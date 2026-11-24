"""Voice loop: mic -> VAD -> STT -> brain -> (print). TTS comes next phase."""
import re
import config
from core import registry
from core.brain import Brain
from audio.vad import Listener
from audio import stt

# Whisper sometimes "hears" these in near-silence
JUNK = {"you", "thank you", "thanks", "thank you.", "thanks for watching", "thanks for watching!", "bye", "."}
YES = {"yes", "yeah", "yep", "yup", "confirm", "sure", "okay", "ok", "proceed"}
NO = {"no", "nope", "don't", "dont", "stop", "cancel", "wait", "not"}


def make_confirm(listener: Listener):
    def confirm(prompt: str) -> bool:
        print(f"  [confirm] {prompt}\n  Say 'yes' to allow. Anything else cancels (8s)...")
        pcm = listener.listen(timeout=8)
        if not pcm:
            print("  (no answer, cancelled)")
            return False
        heard = re.sub(r"[^a-z' ]", "", stt.transcribe(pcm).lower()).strip()
        print(f"  heard: {heard!r}")
        words = heard.split()
        return bool(words) and not (set(words) & NO) and (words[0] in YES or heard.startswith(("do it", "go ahead")))
    return confirm


def main():
    if not config.active_providers():
        raise SystemExit("No LLM provider configured. Copy .env.example to .env and set GROQ_API_KEY.")
    registry.load_plugins()
    try:
        listener = Listener()
    except RuntimeError as e:
        raise SystemExit(str(e))
    brain = Brain(confirm=make_confirm(listener))
    print(f"Tools: {len(registry.TOOLS)} | STT: {config.STT_BACKEND} | providers: "
          f"{', '.join(n for n, _ in config.active_providers())}\nListening... (Ctrl+C to quit)\n")
    with listener:
        while True:
            try:
                pcm = listener.listen()
                text = stt.transcribe(pcm)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"  [stt error] {e}")
                continue
            if len(text) < 2 or text.lower().strip() in JUNK:
                continue
            print(f"you> {text}")
            try:
                print(f"agent> {brain.run(text)}\n")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"  [error] {e}\n")


if __name__ == "__main__":
    main()
