import asyncio
import pyaudio
import logging
from .utils import FORMAT, CHANNELS, RATE

class AudioPlayer:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)

    async def play_audio(self, audio_data):
        self.stream.write(audio_data)
    
    def __del__(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        logging.debug("Audio playback completed")

