"""Voice loop: mic -> VAD -> STT -> brain -> TTS."""
import re
import config
from core import registry
from core.brain import Brain
from audio.vad import Listener
from audio import stt
from audio.tts import Speaker

# Whisper sometimes "hears" these in near-silence
JUNK = {"you", "thank you", "thanks", "thank you.", "thanks for watching", "thanks for watching!", "bye", "."}
YES = {"yes", "yeah", "yep", "yup", "confirm", "sure", "okay", "ok", "proceed"}
NO = {"no", "nope", "don't", "dont", "stop", "cancel", "wait", "not"}


def spoken_version(prompt: str) -> str:
    """'Run run_shell({'command': 'ls -la'})?' -> 'Please confirm: run the command ls -la. Say yes or no.'"""
    m = re.match(r"Run (\w+)\((.*)\)\?$", prompt, re.S)
    if not m:
        return f"{prompt} Say yes or no."
    name, args = m.groups()
    cmd = re.search(r"'command': (?:'|\")(.*?)(?:'|\")\s*(?:,|\})", args)
    what = f"the command {cmd.group(1)}" if cmd and len(cmd.group(1)) < 120 else name.replace("_", " ")
    return f"Please confirm: run {what}. Say yes or no."


def make_confirm(listener: Listener, speaker: Speaker):
    def confirm(prompt: str) -> bool:
        print(f"  [confirm] {prompt}\n  Say 'yes' to allow. Anything else cancels (8s)...")
        speaker.say(spoken_version(prompt))
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
    speaker = Speaker()
    brain = Brain(confirm=make_confirm(listener, speaker))
    print(f"Tools: {len(registry.TOOLS)} | STT: {config.STT_BACKEND} | providers: "
          f"{', '.join(n for n, _ in config.active_providers())}\nListening... (Ctrl+C to quit)\n")
    with listener:
        speaker.say("Ready.")
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
                reply = brain.run(text)
                print(f"agent> {reply}\n")
                speaker.say(reply)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"  [error] {e}\n")


if __name__ == "__main__":
    main()
