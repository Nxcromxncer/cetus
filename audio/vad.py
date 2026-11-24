"""Microphone capture + Silero VAD: blocks until the user says something, returns that utterance.

Segmenter  = pure state machine (easy to test, no audio needed).
Listener   = sounddevice mic stream + Silero VAD + Segmenter.
Audio format everywhere: 16 kHz, mono, 16-bit PCM bytes.
"""
import collections, queue, time
import config

RATE = 16000
FRAME = 512                  # samples per VAD frame (Silero requires exactly 512 at 16 kHz)
FRAME_BYTES = FRAME * 2
FRAME_MS = FRAME * 1000 // RATE      # 32 ms
START_FRAMES = 3             # consecutive speech frames needed to start an utterance (~96 ms)


class Segmenter:
    """Feed (frame, speech_probability). Returns the utterance bytes when speech has ended, else None."""

    def __init__(self, threshold=None, silence_ms=None, min_speech_ms=None, preroll_ms=None, max_s=None):
        self.threshold = config.VAD_THRESHOLD if threshold is None else threshold
        self.silence_frames = (config.VAD_SILENCE_MS if silence_ms is None else silence_ms) // FRAME_MS
        self.min_speech_frames = (config.VAD_MIN_SPEECH_MS if min_speech_ms is None else min_speech_ms) // FRAME_MS
        self.max_frames = (config.MAX_UTTERANCE_S if max_s is None else max_s) * 1000 // FRAME_MS
        self.preroll = collections.deque(maxlen=max(1, (config.VAD_PREROLL_MS if preroll_ms is None else preroll_ms) // FRAME_MS))
        self.reset()

    def reset(self):
        self.preroll.clear()
        self.buf: list[bytes] = []
        self.active = False
        self.speech_run = self.silence_run = self.speech_frames = 0

    def feed(self, frame: bytes, prob: float):
        speech = prob >= self.threshold
        if not self.active:
            self.preroll.append(frame)
            self.speech_run = self.speech_run + 1 if speech else 0
            if self.speech_run >= START_FRAMES:
                self.active = True
                self.buf = list(self.preroll)          # includes the audio just before speech was detected
                self.speech_frames, self.silence_run = self.speech_run, 0
            return None
        self.buf.append(frame)
        if speech:
            self.speech_frames += 1
            self.silence_run = 0
        else:
            self.silence_run += 1
        if self.silence_run >= self.silence_frames or len(self.buf) >= self.max_frames:
            utterance = b"".join(self.buf) if self.speech_frames >= self.min_speech_frames else None
            self.reset()
            return utterance                           # None = too short (cough, click): discarded
        return None


class Listener:
    def __init__(self):
        try:
            import sounddevice as sd
        except (ImportError, OSError) as e:
            raise RuntimeError("Microphone support missing. Run: sudo pacman -S portaudio && "
                               "pip install sounddevice") from e
        from pysilero_vad import SileroVoiceActivityDetector
        self._sd = sd
        self.vad = SileroVoiceActivityDetector()
        self.seg = Segmenter()
        self.q: queue.Queue[bytes] = queue.Queue()
        self._pending = b""
        self.stream = None

    def _callback(self, indata, frames, time_info, status):
        self.q.put(bytes(indata))

    def __enter__(self):
        device = int(config.MIC_DEVICE) if config.MIC_DEVICE and config.MIC_DEVICE.isdigit() else config.MIC_DEVICE
        self.stream = self._sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                              blocksize=FRAME, device=device, callback=self._callback)
        self.stream.start()
        return self

    def __exit__(self, *exc):
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def _frames(self, timeout: float = 0.5):
        """Yield exactly-512-sample frames from the mic queue (None on idle tick)."""
        try:
            self._pending += self.q.get(timeout=timeout)
        except queue.Empty:
            yield None
            return
        while len(self._pending) >= FRAME_BYTES:
            frame, self._pending = self._pending[:FRAME_BYTES], self._pending[FRAME_BYTES:]
            yield frame

    def listen(self, timeout: float | None = None):
        """Block until one utterance is captured; returns PCM bytes. With timeout, returns None if nobody spoke."""
        while not self.q.empty():          # drop audio captured while the agent was busy
            self.q.get_nowait()
        self._pending = b""
        self.vad.reset()
        self.seg.reset()
        started = time.time()
        while True:
            for frame in self._frames():
                if frame is None:
                    if timeout and not self.seg.active and time.time() - started > timeout:
                        return None
                    continue
                utterance = self.seg.feed(frame, self.vad.process_chunk(frame))
                if utterance:
                    return utterance
                if timeout and not self.seg.active and time.time() - started > timeout:
                    return None
