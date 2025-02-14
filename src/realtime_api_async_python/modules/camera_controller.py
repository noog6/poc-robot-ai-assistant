import asyncio
import base64
import json
import numpy as np
import threading
import time
import traceback
from io import BytesIO
from picamera2 import Picamera2
from PIL import Image
from openai import OpenAI
from .motion_controller import millis

class CameraController:
    _instance = None

    def __init__(self):
        if not CameraController._instance:
            # Initialize Picamera2 and configure for still capture
            self.picam2 = Picamera2()
            self.camera_configuration = self.picam2.create_still_configuration()
            self.picam2.configure(self.camera_configuration)
            self.picam2.start()

            self._vision_loop_thread = None
            self._stop_event = threading.Event()
            self.vision_loop_function = None
            self.vision_loop_frequency = 0
            self.vision_loop_start_time = [0] * 100
            self.vision_loop_index = 0
            self.realtime_instance = None
            self.client = OpenAI()

            CameraController._instance = self
        else:
            raise Exception("You cannot create another CameraController class")

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = CameraController()
        return cls._instance

    def start_vision_loop(self, vision_loop_frequency=15000):
        if self._vision_loop_thread is None or not self._vision_loop_thread.is_alive():
            self._stop_event.clear()
            self.vision_loop_frequency = vision_loop_frequency
            self._vision_loop_thread = threading.Thread(target=self._vision_loop, daemon=True)
            self._vision_loop_thread.start()

    def stop_vision_loop(self):
        if self._vision_loop_thread is not None:
            self._stop_event.set()
            self._vision_loop_thread.join()
            self._vision_loop_thread = None
            print(f"Control loop stopped at index: {self.vision_loop_index}")
            self.vision_loop_index = 0

    def process_image(self):
        new_image = self.take_image()
        buffered = BytesIO()
        new_image.save(buffered, format="JPEG")
        encoded_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What is in this image?",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                        },
                    ],
                }
            ],
        )
        return response.choices[0]

    def take_image(self):
        # Capture an image as a NumPy array using picamera2
        frame = self.picam2.capture_array()
        
        # Optionally, perform transformations:
        # Rotate by 270 degrees (90 CW) and flip horizontally.
        rotated_image = np.rot90(frame, k=3)
        flipped_image = np.fliplr(rotated_image)
        
        # Convert NumPy array to a PIL Image
        final_image = Image.fromarray(flipped_image)
        return final_image

    def _vision_loop(self):
        next_vision_loop_time = millis() + self.vision_loop_frequency
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_vision_loop_time:
                self.vision_loop_index += 1
                try:
                    print("Taking new image [o]")
                    if self.realtime_instance:
                        vision_response = self.process_image()
                        print(f"Image response: {vision_response.message.content}")
                        asyncio.run_coroutine_threadsafe(
                                self.realtime_instance.send_text_message_to_conversation("What you are currently looking at: " + vision_response.message.content),
                            self.realtime_instance.loop
                        )
                    else:
                        print("Unable to take image - realtime instance not available")
                except Exception as e:
                    print(f"[WARNING] Error in control loop (retrying): {e}", flush=True)
                    traceback.print_exc()

                self.vision_loop_start_time.append(current_time - next_vision_loop_time)
                if len(self.vision_loop_start_time) > 100:
                    self.vision_loop_start_time.pop(0)
                next_vision_loop_time = current_time + self.vision_loop_frequency
            else:
                time.sleep(0.001)

    def is_vision_loop_alive(self):
        return self._vision_loop_thread is not None and self._vision_loop_thread.is_alive()

    def toggle_vision_loop(self):
        if self.is_vision_loop_alive():
            self.stop_vision_loop()
        else:
            self.start_vision_loop()

    def set_realtime_instance(self, realtime_instance):
        self.realtime_instance = realtime_instance

