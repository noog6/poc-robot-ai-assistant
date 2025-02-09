import base64
import json
import numpy as np
import time
import traceback
from picamera2 import Picamera2, Preview
from PIL import Image
from openai import OpenAI

class CameraController:
    _instance = None

    def __init__(self):
        if not CameraController._instance:
            self.camera                           = Picamera2()
            self.camera.options["quality"]        = 10
            #self.camera.options["compress_level"] = 2
            self.vision_loop_function             = None
            self.vision_loop_frequency            = 0
            self.vision_loop_start_time           = [0]*100
            self.realtime_instance                = None
            self.camera.start()
            self.client                           = OpenAI()
            
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
            self._vision_loop_thread = threading.Thread(target=self._vision_loop)
            self._vision_loop_thread.start()

    def stop_vision_loop(self):
        if self._vision_loop_thread is not None:
            self._stop_event.set()
            self._vision_loop_thread.join()
            self._vision_loop_thread = None
            print(f"control loop stopped at index: {self.vision_loop_index}")
            self.vision_loop_index = 0

    def process_image(self):
        new_image     = self.take_image()
        encoded_image = base64.b64encode(new_image).decode("utf-8")
        response      = self.client.chat.completions.create(
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
        data          = self.camera.capture_array("main")
        # The following will rotate the image by 270 deg
        rot_array     = np.rot90(data, 3)
        # Next we will flip the image horizontally
        flipped_array = np.fliplr(rot_array)
        final_image   = Image.fromarray(flipped_array)
        return final_image

    def _vision_loop(self):
        next_vision_loop_time = 0
        
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_vision_loop_time:
                self.vision_loop_index += 1

                # Do work here!!!
                try:
                    if self.realtime_instance:
                        vision_response = self.process_image()
                        self.realtime_instance.send_text_message_to_assistant(vision_respose)
                
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
        if self._vision_loop_thread is None:
            return False
        
        return self._vision_loop_thread.is_alive()
    
    def toggle_vision_loop(self):
        if self.is_vision_loop_alive():
            self.stop_vision_loop()
        else:
            self.start_vision_loop()

