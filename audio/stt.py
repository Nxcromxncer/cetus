"""Speech to text. Backend chosen by STT_BACKEND: 'groq' (Whisper API) or 'local' (faster-whisper)."""
import io, os, wave
import requests
import config

_local_model = None


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _groq(pcm: bytes) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("STT_BACKEND=groq needs GROQ_API_KEY in .env (or set STT_BACKEND=local)")
    data = {"model": config.GROQ_STT_MODEL, "response_format": "json", "temperature": "0"}
    if config.STT_LANGUAGE:
        data["language"] = config.STT_LANGUAGE
    r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                      headers={"Authorization": f"Bearer {key}"},
                      files={"file": ("speech.wav", pcm_to_wav(pcm), "audio/wav")},
                      data=data, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Groq STT HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("text", "").strip()


def _local(pcm: bytes) -> str:
    global _local_model
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("STT_BACKEND=local needs: pip install faster-whisper") from e
    if _local_model is None:
        print(f"  [stt] loading local model '{config.LOCAL_STT_MODEL}' (first run downloads it)...")
        _local_model = WhisperModel(config.LOCAL_STT_MODEL, device=config.LOCAL_STT_DEVICE, compute_type="int8")
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = _local_model.transcribe(audio, language=config.STT_LANGUAGE or None, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe(pcm: bytes) -> str:
    return _local(pcm) if config.STT_BACKEND == "local" else _groq(pcm)
