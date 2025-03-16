import asyncio
import pyaudio
import logging
from .utils import FORMAT, CHANNELS, RATE

class AudioStreamer:
    def __init__(self):
        self.p           = None
        self.stream      = None
        self._reset_audio_stream()
        self.audio_queue = asyncio.Queue()  # Queue to handle streaming
        self.is_playing  = False

    async def play_audio_streaming(self):
        """ Continuously plays audio chunks as they arrive. """
        if self.is_playing:
            return  # Prevent multiple instances
    
        self.is_playing = True
        logging.info("🔊 Starting real-time audio playback...")
    
        preload_chunks = 5
        buffer = []
        silence_timeout = 2.0  # Silence timeout before stopping (seconds)
        last_chunk_time = asyncio.get_event_loop().time()
    
        try:
            # Preload audio chunks before starting playback
            while len(buffer) < preload_chunks:
                try:
                    audio_chunk = self.audio_queue.get_nowait()  # 🔹 Use get_nowait() to avoid blocking
                    buffer.append(audio_chunk)
                    last_chunk_time = asyncio.get_event_loop().time()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.05)  # 🔹 Short sleep instead of blocking
                    if asyncio.get_event_loop().time() - last_chunk_time > silence_timeout:
                        logging.info("⏳ No audio received in preload phase, stopping playback.")
                        self.is_playing = False
                        return  # Exit early if no audio arrives
    
            logging.info("🔊 Buffer preloaded, starting playback...")
    
            # Play preloaded chunks first
            for chunk in buffer:
                if self.stream is not None:
                    self.stream.write(chunk)
    
            buffer = []  # Clear buffer after preloading
    
            # Now continue normal streaming playback
            while self.is_playing:
                try:
                    audio_chunk = self.audio_queue.get_nowait()  # 🔹 Non-blocking retrieval
                    if audio_chunk is None:
                        break  # Stop signal received
    
                    if self.stream is None or not self.stream.is_active():
                        logging.warning("⚠️ Audio stream closed unexpectedly. Restarting...")
                        self._reset_audio_stream()
    
                    if self.stream is not None:
                        self.stream.write(audio_chunk)
                        last_chunk_time = asyncio.get_event_loop().time()  # Update last activity time
    
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.05)  # 🔹 Small sleep to avoid busy-waiting
                    if asyncio.get_event_loop().time() - last_chunk_time > silence_timeout:
                        logging.info("🛑 No new audio received, stopping playback.")
                        break  # Gracefully exit if silent too long
    
        except Exception as e:
            logging.error(f"Audio playback error: {e}")
    
        finally:
            self.is_playing = False
            self._close_audio_stream()
            logging.info("🔇 Audio playback finished.")

    async def queue_audio_chunk(self, audio_chunk):
        """ Add an audio chunk to the playback queue. """
        await self.audio_queue.put(audio_chunk)

    async def stop_audio(self):
        """ Stops audio playback. """
        await self.audio_queue.put(None)  # Send stop signal

    def is_streaming(self):
            """ Returns True if audio is actively playing, False otherwise. """
            return self.is_playing

    def _reset_audio_stream(self):
        """ Safely restart the PyAudio stream if it was closed unexpectedly. """
        self._close_audio_stream()
        self.p      = pyaudio.PyAudio()
        self.stream = self.p.open(
            format            = FORMAT,
            channels          = CHANNELS,
            rate              = RATE,
            output            = True,
            frames_per_buffer = 2048  # ⬅️ Increased buffer size (default is usually 1024)
        )

    def _close_audio_stream(self):
        """ Gracefully close the PyAudio stream and prevent resource leaks. """
        if self.stream is not None:
            if self.stream.is_active():
                self.stream.stop_stream()
            self.stream.close()
            self.stream = None  # Ensure we don't reference a closed stream
    
        if self.p is not None:
            self.p.terminate()
            self.p = None  # Ensure PyAudio instance is completely reset

