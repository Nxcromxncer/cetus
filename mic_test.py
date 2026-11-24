"""Check mic + VAD (+ STT). Speak a few sentences; each detected utterance is printed."""
from audio.vad import Listener
from audio import stt

with Listener() as listener:
    print("Speak. Ctrl+C to quit.")
    while True:
        try:
            pcm = listener.listen()
        except KeyboardInterrupt:
            break
        print(f"utterance {len(pcm) / 2 / 16000:.1f}s", end="  ")
        try:
            print("->", stt.transcribe(pcm))
        except Exception as e:
            print(f"(STT failed: {e})")
