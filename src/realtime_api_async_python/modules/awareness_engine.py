import threading
import time
import traceback
import heapq


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
            self.action_queue            = []
            self.current_action          = None
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
        heapq.heappush(self.action_queue, new_context)


