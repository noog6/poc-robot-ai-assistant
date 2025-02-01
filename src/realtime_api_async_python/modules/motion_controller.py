import threading
import time
import traceback
import heapq
from .action        import Action
from .keyframe      import Keyframe
from .ServoRegistry import ServoRegistry


def millis():
    return int(time.time() * 1000)


class MotionController():
    _instance = None

    def __init__(self):
        if self._instance is None:
            self._control_loop_thread    = None
            self._stop_event             = threading.Event()
            self.control_loop_index      = 0
            self.control_loop_function   = None
            self.control_loop_frequency  = 100
            self.control_loop_start_time = [0]*100
            self.transition_time         = 1500
            self.servo_registry          = ServoRegistry.get_instance()
            self.current_servo_position  = {"pan" : 0,
                                            "tilt": 0}
            self.action_queue            = []
            self.current_action          = None
        else:
            raise Exception("You cannot create another MotionController class")


    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = MotionController()
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
            starting_frame = self.generate_base_keyframe(10, 20)
            while not self.move_to_keyframe(starting_frame):
                time.sleep(0.002)
            self._stop_event.clear()
            self.control_loop_frequency = control_loop_frequency
            self._control_loop_thread = threading.Thread(target=self._control_loop, daemon=True)
            self._control_loop_thread.start()


    def stop_control_loop(self):
        if self._control_loop_thread is not None:
            self._stop_event.set()
            self._control_loop_thread.join()
            self._control_loop_thread = None
            sit_frame = self.generate_base_frame()
            sit_frame.final_target_time = millis() + 1000
            while not self.move_to_keyframe(sit_frame):
                time.sleep(0.002)
            self.relax_all_servos()
            print(f"control loop stopped at index: {self.control_loop_index}")
            self.control_loop_index = 0


    def _control_loop(self):
        next_control_loop_time = 0
        
        while not self._stop_event.is_set():
            current_time = millis()
            if current_time >= next_control_loop_time:
                self.control_loop_index += 1

                try:
                    self.update_pose()
                except Exception as e:
                    print(f"[WARNING] Error in control loop (retrying): {e}", flush=True)
                    traceback.print_exc()

                self.control_loop_start_time.append(current_time - next_control_loop_time)
                if len(self.control_loop_start_time) > 100:
                    self.control_loop_start_time.pop(0)
                next_control_loop_time = current_time + self.control_loop_frequency
            else:
                time.sleep(0.001)


    def update_pose(self):
        if not self.current_action:
            self.current_action = self.get_next_action()

        if self.current_action:
            if self.move_to_keyframe(self.current_action.current_frame):
                # We have reached the location desired by the current frame, switch to the next frame
                self.current_action.current_frame = self.current_action.current_frame.next

                if self.current_action.current_frame == None:
                    self.current_action = self.get_next_action()


    def move_to_keyframe(self, new_frame:Keyframe):
        
        current_time = millis()
        
        if not new_frame.is_initialized:
            new_frame.servo_steps_left = int((new_frame.final_target_time - current_time) / self.control_loop_frequency)

            if new_frame.servo_steps_left < 1:
                new_frame.servo_steps_left = 1

            print( "=============================")
            print(f"New frame setup: {new_frame.name}")
            print(f"new_frame.final_taraget_time: {new_frame.final_target_time}")
            print(f"current_time                : {current_time}")
            print(f"self.control_loop_frequency : {self.control_loop_frequency}")
            print(f"new_frame.servo_steps_left: {new_frame.servo_steps_left}")
            print( "=============================")
            print(f"new_frame.servo_destination['pan']: {new_frame.servo_destination['pan']}")
            print(f"Type of new_frame.servo_destination['pan']: {type(new_frame.servo_destination['pan'])}")
            print(f"new_frame.servo_destination['tilt']: {new_frame.servo_destination['tilt']}")
            print(f"Type of new_frame.servo_destination['tilt']: {type(new_frame.servo_destination['tilt'])}")
            print("")
            print(f"[DEBUG] new_frame.servo_destination['pan']: {new_frame.servo_destination['pan']} (Type: {type(new_frame.servo_destination['pan'])})")
            print(f"[DEBUG] new_frame.servo_destination['tilt']: {new_frame.servo_destination['tilt']} (Type: {type(new_frame.servo_destination['tilt'])})")

            new_frame.servo_step_size["pan"]  = (new_frame.servo_destination["pan"]  - self.current_servo_position["pan"])  / new_frame.servo_steps_left
            new_frame.servo_step_size["tilt"] = (new_frame.servo_destination["tilt"] - self.current_servo_position["tilt"]) / new_frame.servo_steps_left

            print(f"[SETUP] new_frame.servo_destination['pan']: {new_frame.servo_destination['pan']} (Type: {type(new_frame.servo_destination['pan'])})")
            print(f"[SETUP] new_frame.servo_step_size['pan']:   {new_frame.servo_step_size['pan']}")
            print(f"[SETUP] self.current_servo_position['pan']: {self.current_servo_position['pan']} ")
            print(f"[SETUP] new_frame.servo_destination['tilt']: {new_frame.servo_destination['tilt']} (Type: {type(new_frame.servo_destination['tilt'])})")
            print(f"[SETUP] new_frame.servo_step_size['tilt']:   {new_frame.servo_step_size['tilt']}")
            print(f"[SETUP] self.current_servo_position['tilt']: {self.current_servo_position['tilt']} ")

            new_frame.is_initialized = True

        if current_time >= new_frame.final_target_time or new_frame.servo_steps_left <= 1:
            self.current_servo_position["pan"]  = new_frame.servo_destination["pan"]
            self.current_servo_position["tilt"] = new_frame.servo_destination["tilt"]
           
            self.servo_registry.servos["pan"].write_value(self.current_servo_position["pan"])
            self.servo_registry.servos["tilt"].write_value(self.current_servo_position["tilt"])

            print(f"[DONE] new_frame.servo_destination['pan']: {new_frame.servo_destination['pan']} (Type: {type(new_frame.servo_destination['pan'])})")
            print(f"[DONE] new_frame.servo_step_size['pan']:   {new_frame.servo_step_size['pan']}")
            print(f"[DONE] self.current_servo_position['pan']: {self.current_servo_position['pan']} ")
            print(f"[DONE] new_frame.servo_destination['tilt']: {new_frame.servo_destination['tilt']} (Type: {type(new_frame.servo_destination['tilt'])})")
            print(f"[DONE] new_frame.servo_step_size['tilt']:   {new_frame.servo_step_size['tilt']}")
            print(f"[DONE] self.current_servo_position['tilt']: {self.current_servo_position['tilt']} ")

            return True

        else:
            self.current_servo_position["pan"]  = self.current_servo_position["pan"]  + new_frame.servo_step_size["pan"]
            self.current_servo_position["tilt"] = self.current_servo_position["tilt"] + new_frame.servo_step_size["tilt"]
            
            self.servo_registry.servos["pan"].write_value(self.current_servo_position["pan"])
            self.servo_registry.servos["tilt"].write_value(self.current_servo_position["tilt"])

            #print(f"[DEBUG] new_frame.servo_destination['pan']: {new_frame.servo_destination['pan']} (Type: {type(new_frame.servo_destination['pan'])})")
            #print(f"[DEBUG] new_frame.servo_step_size['pan']:   {new_frame.servo_step_size['pan']}")
            print(f"[MOTION] self.current_servo_position['pan']: {self.current_servo_position['pan']:.1f} ")

            #print(f"[DEBUG] new_frame.servo_destination['tilt']: {new_frame.servo_destination['tilt']} (Type: {type(new_frame.servo_destination['tilt'])})")
            #print(f"[DEBUG] new_frame.servo_step_size['tilt']:   {new_frame.servo_step_size['tilt']}")
            print(f"[MOTION] self.current_servo_position['tilt']: {self.current_servo_position['tilt']:.1f} ")

            new_frame.servo_steps_left -= 1
            print(f"[STEPS] new_frame.servo_steps_left: {new_frame.servo_steps_left}")
            return False


    def generate_base_keyframe(self, pan_degrees:int, tilt_degrees:int):
        new_frame = Keyframe(target_time=(millis() + self.transition_time), name="base")
        new_frame.servo_destination["pan"]  = pan_degrees
        new_frame.servo_destination["tilt"] = tilt_degrees
        return(new_frame)


    def relax_all_servos(self):
        self.servo_registry.servos["pan"].relax()
        self.servo_registry.servos["tilt"].relax()


    def get_next_action(self):
        next_action  = None
        current_time = millis()
        if self.action_queue and self.action_queue[0].timestamp <= current_time:
            next_action = heapq.heappop(self.action_queue)
            next_action.set_frame_times(current_time)

        return next_action


    def add_action_to_queue(self, new_action:Action):
        heapq.heappush(self.action_queue, new_action)


