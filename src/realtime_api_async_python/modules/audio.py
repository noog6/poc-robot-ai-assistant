import asyncio
import pyaudio
import logging
from .utils import FORMAT, CHANNELS, RATE

class AudioPlayer:

    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)

    async def play_audio(self, audio_data):
        
        # Add a small delay of silence at the start to prevent popping, and weird crackling
        silence_duration = 0.4
        silence_frames = int(RATE * silence_duration)
        silence = b"\x00" * (
            silence_frames * CHANNELS * 2
        )  # 2 bytes per sample for 16-bit audio
        self.stream.write(silence)
    
        # Write our actual audio out
        self.stream.write(audio_data)
    
        # Add a small delay of silence at the end to prevent popping, and weird cuts off sounds
        silence_duration = 0.6
        silence_frames = int(RATE * silence_duration)
        silence = b"\x00" * (
            silence_frames * CHANNELS * 2
        )  # 2 bytes per sample for 16-bit audio
        self.stream.write(silence)

    def __del__(self):
        # Add a small pause before closing the stream to make sure the audio is fully played
        #await asyncio.sleep(0.5)
    
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        logging.debug("Audio playback completed")

