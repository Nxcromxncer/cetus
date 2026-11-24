"""Check that the agent can speak:  python tts_test.py"""
import config
from audio.tts import Speaker

print(f"backend={config.TTS_BACKEND} voice={config.TTS_VOICE}")
ok = Speaker().say("Hello! I can talk now. Say something after the beep, or press control C to quit.")
print("spoke OK" if ok else "FAILED, see the message above")
