import numpy as np
import pyaudio
import queue
import logging
from .utils import FORMAT, CHANNELS, RATE, CHUNK

class AsyncMicrophone:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        print("Listing input devices:")
        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            print(f"Device {i}: {info['name']} | Input Channels: {info['maxInputChannels']}")
        print("Completed device list")

        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=self.callback,
        )
        self.queue = queue.Queue(maxsize=50)
        self.is_recording = False
        self.is_receiving = False
        logging.info("AsyncMicrophone initialized")

    def callback(self, in_data, frame_count, time_info, status):
        if self.is_recording and not self.is_receiving:
            try:
                self.queue.put_nowait(in_data)
            except queue.Full:
                # Drop audio rather than blocking the callback
                pass
        return (None, pyaudio.paContinue)


    def rms_numpy(self, audio_bytes, sample_width=2):
        """
        Compute RMS (Root Mean Square) volume level of an audio signal using NumPy.
    
        Parameters:
            audio_bytes (bytes): The raw PCM audio data.
            sample_width (int): The number of bytes per sample (default 2 for 16-bit audio).
    
        Returns:
            float: RMS value of the audio signal.
        """
        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sample_width, np.int16)  # Default to 16-bit
    
        audio_array = np.frombuffer(audio_bytes, dtype=dtype)
        rms_value = np.sqrt(np.mean(audio_array**2))
    
        return rms_value

    def start_recording(self):
        self.is_recording = True
        logging.info("Started recording")

    def stop_recording(self):
        self.is_recording = False
        logging.info("Stopped recording")

    def start_receiving(self):
        self.is_receiving = True
        self.is_recording = False
        logging.info("Started receiving assistant response")

    def stop_receiving(self):
        self.is_receiving = False
        logging.info("Stopped receiving assistant response")

    def get_audio_data(self):
        chunks = []
        while True:
            try:
                chunks.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return b"".join(chunks) if chunks else None

    def drain_queue(self, max_items: int = 9999):
        removed = 0
        while removed < max_items:
            try:
                self.queue.get_nowait()
                removed += 1
            except queue.Empty:
                break
        return removed

    def close(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        logging.info("AsyncMicrophone closed")

