import asyncio
import numpy as np
import pyaudio
import queue
import logging
from .utils import FORMAT, CHANNELS, RATE, CHUNK

AUDIO_THRESHOLD     = 40.0
AUDIO_SILENCE_TOTAL = 10

class AsyncMicrophone:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        print("Listing input devices:")
        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            print(f"Device {i}: {info['name']} | Input Channels: {info['maxInputChannels']}")
        print("Completed device list")

        self.stream = self.p.open(
            format            = FORMAT,
            channels          = CHANNELS,
            rate              = RATE,
            input             = True,
            frames_per_buffer = CHUNK,
            stream_callback   = self.callback,
        )
        self.queue                   = queue.Queue()
        self.is_recording            = False
        self.is_receiving            = False
        self.silence_count           = 0
        self.speech_stopped_callback = None
        self.websocket               = None
        logging.info("AsyncMicrophone initialized")

    def set_speech_stopped_callback(self, callback_function=None, websocket=None, loop=None):
        self.speech_stopped_callback = callback_function
        self.websocket               = websocket
        self.loop                    = loop

    def callback(self, in_data, frame_count, time_info, status):
        audio_level = round( self.rms_numpy(in_data, 2), 2)
        #print(f"[Audio Volume: {audio_level}] [Silence Count: {self.silence_count}]")
        #print(f"[Audio Volume: {audio_level}] [Silence Count: {self.silence_count}] [is_recording: {self.is_recording}] [is_receiving: {self.is_receiving}]")
        if not self.is_recording and not self.is_receiving and audio_level > AUDIO_THRESHOLD:
            self.start_recording()

        if self.is_recording and not self.is_receiving:
            self.queue.put(in_data)
            if audio_level >= AUDIO_THRESHOLD:
                self.silence_count = 0
            elif audio_level < AUDIO_THRESHOLD:
                self.silence_count += 1
                if self.silence_count >= AUDIO_SILENCE_TOTAL:
                    self.stop_recording()
                    if self.speech_stopped_callback:
                        self.loop.create_task(self.speech_stopped_callback(self.websocket))

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
        if not audio_bytes or len(audio_bytes) == 0:
            return 0.0  # Return 0 RMS for empty input
    
        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sample_width, np.int16)  # Default to 16-bit
    
        audio_array = np.frombuffer(audio_bytes, dtype=dtype)
    
        if audio_array.size == 0:
            return 0.0  # Return 0 if the array is empty
    
        rms_value = np.sqrt(np.mean(audio_array**2))
    
        if np.isnan(rms_value) or np.isinf(rms_value):
            return 0.0  # Catch and return safe value
    
        return rms_value

    def start_recording(self):
        self.is_recording = True
        self.silence_count = 0
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
        data = b""
        while not self.queue.empty():
            data += self.queue.get()
        return data if data else None

    def close(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        logging.info("AsyncMicrophone closed")
