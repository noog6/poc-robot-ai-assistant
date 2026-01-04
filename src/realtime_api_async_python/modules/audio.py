import threading
import queue
import logging
import pyaudio
import audioop
import time
from .utils import FORMAT, CHANNELS

INPUT_RATE = 24000
OUTPUT_RATE = 44100
FRAMES_PER_BUFFER = 16384


class AudioPlayer:
    def __init__(self, on_playback_complete=None):
        self.on_playback_complete = on_playback_complete

        self.p = pyaudio.PyAudio()
        out = self.p.get_default_output_device_info()
        logging.info(
            f"Output device: {out['name']} idx={out['index']} defaultRate={out.get('defaultSampleRate')}"
        )

        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_RATE,
            output=True,
            output_device_index=out["index"],
            frames_per_buffer=FRAMES_PER_BUFFER,
            start=True,
        )

        # playback coordination
        self._q = queue.Queue(maxsize=75)  # bigger; deltas can be bursty
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending = 0                 # number of queued items not yet played
        self._response_closed = False     # set True when response.output_audio.done arrives
        self._ratecv_state = None         # persistent resampler state

        self._t = threading.Thread(target=self._worker, daemon=True)
        self._t.start()

    # --- lifecycle hooks for a single assistant response ---
    def start_response(self):
        """Call at response.created (or when you begin accepting audio for a response)."""
        self.flush()
        with self._lock:
            self._pending = 0
            self._response_closed = False
            self._ratecv_state = None

    def close_response(self):
        """Call at response.output_audio.done (no more audio will be queued for this response)."""
        with self._lock:
            self._response_closed = True
        self._maybe_fire_complete()

    # --- worker + helpers ---
    def _worker(self):
        try:
            while not self._stop.is_set():
                try:
                    audio_data = self._q.get(timeout=0.1)
                except queue.Empty:
                    continue

                if audio_data is None:
                    break

                # resample with persistent state to avoid boundary artifacts
                out_data, self._ratecv_state = audioop.ratecv(
                    audio_data, 2, 1, INPUT_RATE, OUTPUT_RATE, self._ratecv_state
                )

                # chunked write (bigger chunks = less overhead)
                chunk_bytes = 16384
                for i in range(0, len(out_data), chunk_bytes):
                    self.stream.write(out_data[i:i + chunk_bytes])

                with self._lock:
                    self._pending = max(0, self._pending - 1)

                self._maybe_fire_complete()

        except Exception:
            logging.exception("Audio output worker crashed")

    def _maybe_fire_complete(self):
        cb = None
        with self._lock:
            if self._response_closed and self._pending == 0:
                cb = self.on_playback_complete
                self._response_closed = False
    
        if cb:
            try:
                # Estimate remaining time still playing in the output pipeline
                try:
                    out_lat = float(getattr(self.stream, "get_output_latency", lambda: 0.0)())
                except Exception:
                    out_lat = 0.0
    
                buffer_secs = FRAMES_PER_BUFFER / OUTPUT_RATE  # e.g. 16384/44100 ≈ 0.37s
                time.sleep(out_lat + buffer_secs)
    
                cb()
            except Exception:
                logging.exception("on_playback_complete callback failed")

    # --- public enqueue API ---
    def play_audio(self, audio_data: bytes):
        # Track pending BEFORE enqueue; if enqueue fails, roll it back.
        with self._lock:
            self._pending += 1

        try:
            self._q.put_nowait(audio_data)
        except queue.Full:
            with self._lock:
                self._pending -= 1
            logging.warning("Audio queue full; dropping audio")
            self._maybe_fire_complete()

    def flush(self):
        removed = 0
        try:
            while True:
                self._q.get_nowait()
                removed += 1
        except queue.Empty:
            pass
    
        with self._lock:
            self._pending = max(0, self._pending - removed)
            self._ratecv_state = None

    def close(self):
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        self._t.join(timeout=1.0)
        try:
            self.stream.stop_stream()
            self.stream.close()
        finally:
            self.p.terminate()


