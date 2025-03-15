import asyncio
import heapq
import json
import math
import threading
import time
import traceback
from .tools import read_battery_voltage

def millis():
    return int(time.time() * 1000)

class AwarenessEngine():
    _instance = None

    def __init__(self):
        if self._instance is None:
            self._control_loop_thread    = None
            self._stop_event             = threading.Event()
            self.control_loop_index      = 0
            self.control_loop_function   = None
            self.control_loop_frequency  = 100
            self.control_loop_start_time = [0]*100
            self.context_queue           = []
            self.alert_queue             = []
            self.sensor_data             = None
        else:
            raise Exception("You cannot create another MotionController class")


    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = AwarenessEngine()
        return cls._instance


    def is_control_loop_alive(self):
        if self._control_loop_thread is None:
            return False
        
        return self._control_loop_thread.is_alive()


    def toggle_control_loop(self):
        if self.is_control_loop_alive():
            self.stop_control_loop()
        else:
            self.start_control_loop()


    def start_control_loop(self, control_loop_frequency=20):
        if self._control_loop_thread is None or not self._control_loop_thread.is_alive():
            self._stop_event.clear()
            self.control_loop_frequency = control_loop_frequency
            self._control_loop_thread = threading.Thread(target=self._control_loop, daemon=True)
            self._control_loop_thread.start()


    def stop_control_loop(self):
        if self._control_loop_thread is not None:
            self._stop_event.set()
            self._control_loop_thread.join()
            self._control_loop_thread = None
            print(f"Awareness Engine loop stopped at index: {self.control_loop_index}")
            self.control_loop_index = 0


    def _control_loop(self):
        next_control_loop_time = 0
        
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_control_loop_time:
                self.control_loop_index += 1

                try:
                    print("Awareness Engine: Todo - become aware here...")
                    
                    # Stage 1 - Consolidate Context
                    new_context = self.get_next_context()
                    if new_context:
                        print(f"Found new context: {new_context}")
                    
                    # Stage 2 - Update and manage awareness state
                    self.sensor_data = self.get_sensor_data()

                    # State 3 - Inject updated context back into Theo's higher level thinking

                    # Stage 4 - Trigger any actions needed

                except Exception as e:
                    print(f"[WARNING] Error in awareness loop (retrying): {e}", flush=True)
                    traceback.print_exc()

                self.control_loop_start_time.append(current_time - next_control_loop_time)
                if len(self.control_loop_start_time) > 100:
                    self.control_loop_start_time.pop(0)
                next_control_loop_time = current_time + self.control_loop_frequency
            else:
                time.sleep(0.001)

    def add_context(self, new_context):
        heapq.heappush(self.context_queue, new_context)

    def get_next_context(self):
        next_context = None

        if self.context_queue:
            next_context = heapq.heappop(self.context_queue)
        
        return next_context

    async def get_sensor_data(self):
        current_battery_voltage = round(await read_battery_voltage(), 2)
        latest_sensor_data = {
            "battery_level": current_battery_voltage,
        }

        return json.dumps(latest_sensor_data)

