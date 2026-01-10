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
from .logging import logger
from .motion_controller import MotionController, millis
from .tools import function_map, servo_tools, set_all_servos

class CameraController:
    _instance = None

    def __init__(self):
        if not CameraController._instance:
            # Initialize Picamera2 and configure for still capture
            self.picam2 = Picamera2()
            self._main_size = (640, 480)
            self._lores_size = (160, 90)
            self._last_luma = None
            # Full sensor resolution ??? (2592×1944)
            self.camera_configuration = self.picam2.create_preview_configuration(
                main={"size": self._main_size, "format": "RGB888"},
                lores={"size": self._lores_size, "format": "YUV420"},
                buffer_count=2,
            )
            self.picam2.configure(self.camera_configuration)
            self.picam2.start()

            self._vision_loop_thread = None
            self._stop_event = threading.Event()
            self._send_in_flight = threading.Event()
            self.vision_loop_function = None
            self.vision_loop_frequency = 0
            self.vision_loop_start_time = [0] * 100
            self.vision_loop_index = 0
            self.last_image = None
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
            logger.info(f"[CAMERA] Control loop stopped at index: {self.vision_loop_index}")
            self.vision_loop_index = 0

    def take_image(self):
        # Capture an image as a NumPy array using picamera2
        frame = self.picam2.capture_array("main")
        
        # Optionally, perform transformations:
        # Rotate by 270 degrees (90 CW) and flip horizontally.
        rotated_image = np.rot90(frame, k=3)
        
        # Convert NumPy array to a PIL Image
        final_image = Image.fromarray(rotated_image)
        return final_image

    def take_lores_luma(self) -> np.ndarray:
        """
        Returns a small uint8 grayscale (luma) frame for cheap change detection.
        For YUV420, the Y plane is the top H rows.
        """
        yuv = self.picam2.capture_array("lores")  # usually shape like (H*3/2, W) or similar
        h = self._lores_size[1]
        # Y plane is the first H rows; keep as uint8
        y = yuv[:h, :]
        return y.copy()  # IMPORTANT: avoid buffer reuse issues
    
    def take_main_pil(self) -> Image.Image:
        """
        Returns a PIL image suitable for your existing send_image_to_assistant().
        """
        frame = self.picam2.capture_array("main")  # shape (H, W, 3) RGB888
        frame = frame[:, :, ::-1]  # swap R and B
        
        # Rotate by 270 degrees (90 CW) and flip horizontally.
        rotated_image = np.rot90(frame, k=3)
        
        return Image.fromarray(rotated_image, mode="RGB")

    def _vision_loop(self):
        next_vision_loop_time = millis() + self.vision_loop_frequency
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_vision_loop_time:
                self.vision_loop_index += 1
                
                self.vision_loop_start_time.append(current_time - next_vision_loop_time)
                if len(self.vision_loop_start_time) > 100:
                    self.vision_loop_start_time.pop(0)
                
                next_vision_loop_time = current_time + self.vision_loop_frequency
                
                if self._send_in_flight.is_set():
                    time.sleep(0.01)
                    continue

                try:
                    luma = self.take_lores_luma()
                    changed, score = self.lores_changed(luma, threshold=7.0)
                    if not changed:
                        time.sleep(0.01)
                        continue

                    logger.info(f"[CAMERA] change detected (mad={score:.2f})")

                    if self.realtime_instance:
                        self._send_in_flight.set()
                        
                        new_image = self.take_main_pil()
                        
                        future = asyncio.run_coroutine_threadsafe(
                            self.realtime_instance.send_image_to_assistant(new_image),
                            self.realtime_instance.loop
                        )

                        future.add_done_callback(self._clear_send_flag)

                        logger.info("[CAMERA] Finished processing image")
                    else:
                        self._send_in_flight.clear()
                        logger.warning("[CAMERA] Unable to take image - realtime instance not available")
                
                except Exception as e:
                    self._send_in_flight.clear()
                    logger.exception(f"[CAMERA] Error in control loop (retrying): {e}", flush=True)
                    traceback.print_exc()
            else:
                time.sleep(0.01)

    def is_vision_loop_alive(self):
        return self._vision_loop_thread is not None and self._vision_loop_thread.is_alive()

    def toggle_vision_loop(self):
        if self.is_vision_loop_alive():
            self.stop_vision_loop()
        else:
            self.start_vision_loop()

    def set_realtime_instance(self, realtime_instance):
        self.realtime_instance = realtime_instance

    def _clear_send_flag(self, fut):
        try:
            fut.result()
        except Exception as e:
            logger.exception(f"[CAMERA] [WARN] Image send failed: {e}")
        finally:
            #logger.info("[CAMERA] Clearing _send_in_flight flag")
            self._send_in_flight.clear()

    def lores_changed(self, luma: np.ndarray, threshold: float = 7.0) -> tuple[bool, float]:
        """
        Mean absolute difference on tiny grayscale.
        Returns (changed, score).
        """
        if self._last_luma is None:
            self._last_luma = luma
            return True, 999.0
    
        d = luma.astype(np.int16) - self._last_luma.astype(np.int16)
        mad = float(np.abs(d).mean())
        self._last_luma = luma
        return (mad >= threshold), mad

