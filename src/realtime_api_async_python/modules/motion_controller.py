import threading
import time
import traceback
import heapq
from .action         import Action
from .keyframe       import Keyframe
from .logging        import log_info, log_warning, log_error
from .servo_registry import ServoRegistry

def millis():
    return int(time.monotonic() * 1000)

def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

def smoothstep(t: float) -> float:
    # ease-in/ease-out, zero slope at both ends
    return t * t * (3.0 - 2.0 * t)

MAX_PAN_DEG_PER_TICK  = 2.5
MAX_TILT_DEG_PER_TICK = 1.5

def limit_step(current: float,
               target: float,
               v_state: dict,
               axis: str,
               dt_s: float,
               v_max: float,
               a_max: float,
               eps: float = 1e-3) -> float:
    """
    Acceleration-limited velocity follower.

    - v_state[axis] holds the *current velocity* for this axis (deg/s).
    - v_max is max speed (deg/s)
    - a_max is max accel (deg/s^2)
    """
    v = float(v_state.get(axis, 0.0))
    err = target - current

    # If we're basically there, stop.
    if abs(err) <= eps:
        v_state[axis] = 0.0
        return target

    # "What velocity would hit the target in one tick?" then clamp to v_max.
    v_des = err / max(dt_s, 1e-6)
    if v_des >  v_max: v_des =  v_max
    if v_des < -v_max: v_des = -v_max

    # Accel limit: clamp delta-v this tick.
    dv_max = a_max * dt_s
    dv = v_des - v
    if dv >  dv_max: dv =  dv_max
    if dv < -dv_max: dv = -dv_max
    v = v + dv

    # Clamp velocity just in case.
    if v >  v_max: v =  v_max
    if v < -v_max: v = -v_max

    # Integrate position.
    nxt = current + v * dt_s

    # Prevent overshoot: if we crossed target, snap and stop.
    if (target - current) * (target - nxt) <= 0.0:
        v_state[axis] = 0.0
        return target

    v_state[axis] = v
    return nxt

def scaled_pan_step(dist_deg: float) -> float:
    PAN_STEP_MIN = 0.2   # tiny corrections
    PAN_STEP_MAX = 1.6   # big swings
    a = clamp01(abs(dist_deg) / 90.0)
    return PAN_STEP_MIN + (PAN_STEP_MAX - PAN_STEP_MIN) * a

class MotionController():
    _instance = None

    def __init__(self):
        if self._instance is None:
            self._control_loop_thread    = None
            self._stop_event             = threading.Event()
            self.control_loop_index      = 0
            self.control_loop_function   = None
            self.control_loop_period_ms  = 100
            self.control_loop_start_time = [0]*100
            self.transition_time         = 1500
            self.servo_registry          = ServoRegistry.get_instance()
            self.current_servo_position  = {"pan": 0,   "tilt": 0}
            self.axis_v                  = {"pan": 0.0, "tilt": 0.0}
            self.action_queue            = []
            self.current_action          = None
            self._queue_lock             = threading.Lock()
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

    def start_control_loop(self, control_loop_period_ms=20):
        if self._control_loop_thread is None or not self._control_loop_thread.is_alive():
            self.control_loop_period_ms = control_loop_period_ms
            starting_frame = self.generate_base_keyframe(pan_degrees=0, tilt_degrees=-40)
            starting_frame.name = "Starting Frame - 1"
            while not self.move_to_keyframe(starting_frame):
                time.sleep(0.02)
            time.sleep(1.0)
            starting_frame = self.generate_base_keyframe(pan_degrees=0, tilt_degrees=25)
            starting_frame.name = "Starting Frame - 2"
            while not self.move_to_keyframe(starting_frame):
                time.sleep(0.02)
            self._stop_event.clear()
            self.control_loop_period_ms = control_loop_period_ms
            self._control_loop_thread = threading.Thread(target=self._control_loop, daemon=True)
            self._control_loop_thread.start()

    def stop_control_loop(self):
        if self._control_loop_thread is not None:
            self._stop_event.set()
            self._control_loop_thread.join()
            self._control_loop_thread = None
            sit_frame = self.generate_base_keyframe(pan_degrees=0, tilt_degrees=-40)
            sit_frame.name = "Ending Frame - 1"
            sit_frame.final_target_time = 1000
            sit_frame.deadline_ms = None
            while not self.move_to_keyframe(sit_frame):
                time.sleep(0.02)
            self.relax_all_servos()
            log_info(f"[MOTION] control loop stopped at index: {self.control_loop_index}")
            self.control_loop_index = 0

    def _control_loop(self):
        next_control_loop_time = millis()
        
        while not self._stop_event.is_set():
            current_time = millis()
            while current_time >= next_control_loop_time:
                self.control_loop_index += 1

                try:
                    self.update_pose()
                except Exception as e:
                    log_error(f"[MOTION] Error in control loop (retrying): {e}")
                    traceback.print_exc()

                self.control_loop_start_time.append(current_time - next_control_loop_time)
                if len(self.control_loop_start_time) > 100:
                    self.control_loop_start_time.pop(0)
                next_control_loop_time += self.control_loop_period_ms
                current_time = millis()
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

    def move_to_keyframe(self, new_frame: Keyframe) -> bool:
        now_ms = millis()
    
        if not new_frame.is_initialized:
            self._init_frame(new_frame, now_ms)
    
        dt_s          = max(self.control_loop_period_ms, 1) / 1000.0
        desired_pan   = new_frame.servo_destination["pan"]
        desired_tilt  = new_frame.servo_destination["tilt"]
        pan_remaining = desired_pan - self.current_servo_position["pan"]
        PAN_V_MAX     = scaled_pan_step(pan_remaining) / dt_s
        TILT_V_MAX    = MAX_TILT_DEG_PER_TICK / dt_s
        PAN_A_MAX     = 600.0
        TILT_A_MAX    = 400.0
    
        limited_pan = limit_step(self.current_servo_position["pan"], desired_pan,
                                 self.axis_v, "pan", dt_s, PAN_V_MAX, PAN_A_MAX, eps=0.05)
    
        limited_tilt = limit_step(self.current_servo_position["tilt"], desired_tilt,
                                  self.axis_v, "tilt", dt_s, TILT_V_MAX, TILT_A_MAX, eps=0.05)
    
        if abs(limited_pan - self.current_servo_position["pan"]) > 1.0:
            log_info(f"[MOTION] [{new_frame.name}] 'pan' servo to ({limited_pan:.2f}) (wanted: {desired_pan:.2f}) (PAN_V_MAX:{PAN_V_MAX:.3f})")
    
        self.current_servo_position["pan"]  = limited_pan
        self.current_servo_position["tilt"] = limited_tilt
        self.servo_registry.servos["pan"].write_value(limited_pan)
        self.servo_registry.servos["tilt"].write_value(limited_tilt)
    
        # --- compute at_dest ---
        EPS = 0.5
        at_dest = (
            abs(self.current_servo_position["pan"]  - desired_pan)  <= EPS and
            abs(self.current_servo_position["tilt"] - desired_tilt) <= EPS
        )
    
        # --- completion policy ---
        done = self._frame_done(new_frame, at_dest, now_ms)
    
        if done:
            # snap to exact destination for cleanliness
            self.current_servo_position["pan"]  = desired_pan
            self.current_servo_position["tilt"] = desired_tilt
            self.servo_registry.servos["pan"].write_value(desired_pan)
            self.servo_registry.servos["tilt"].write_value(desired_tilt)
    
            log_info(f"[MOTION] 'pan' servo move completed (Cmd: {desired_pan:.3f}) (Position: {desired_pan})")
            log_info(f"[MOTION] 'tilt' servo move completed (Cmd: {desired_tilt:.3f}) (Position: {desired_tilt})")
            return True
    
        return False

    def _init_frame(self, frame: Keyframe, now_ms: int) -> None:
        frame.start_time_ms = now_ms
    
        if frame.deadline_ms is None:
            frame.deadline_ms = now_ms + max(0, int(frame.final_target_time))
    
        frame.duration_ms = max(1, int(frame.deadline_ms - now_ms))
    
        frame.start_pos = {
            "pan":  float(self.current_servo_position["pan"]),
            "tilt": float(self.current_servo_position["tilt"]),
        }
        frame.delta_pos = {
            "pan":  float(frame.servo_destination["pan"])  - frame.start_pos["pan"],
            "tilt": float(frame.servo_destination["tilt"]) - frame.start_pos["tilt"],
        }
    
        log_info(f"[MOTION] New motion frame started (Name:{frame.name}) (Duration:{frame.duration_ms})")
        log_info(f"[MOTION] Moving 'pan' servo from ({self.current_servo_position['pan']:.2f}) to ({frame.servo_destination['pan']:.2f})")
        log_info(f"[MOTION] Moving 'tilt' servo from ({self.current_servo_position['tilt']:.2f}) to ({frame.servo_destination['tilt']:.2f})")
    
        frame.is_initialized = True

    def _frame_done(self, frame: Keyframe, at_dest: bool, now_ms: int) -> bool:
        """
        Completion policy:
          - If no deadline: advance as soon as at_dest.
          - If deadline: treat as a HOLD gate:
              - advance only when at_dest AND time has passed.
          - Optional robustness: if deadline passed, allow advance even if not at_dest.
            (toggle with FAIL_OPEN_ON_DEADLINE)
        """
        FAIL_OPEN_ON_DEADLINE = False  # set True if you prefer "don't get stuck"
    
        if not frame.has_deadline():
            return at_dest
    
        time_up = now_ms >= frame.deadline_ms
    
        if at_dest:
            return time_up  # classic "hold until time passes"
    
        # Not at destination:
        if FAIL_OPEN_ON_DEADLINE and time_up:
            log_warning(f"[MOTION] Frame '{frame.name}' missed destination before deadline; advancing anyway.")
            return True
    
        return False


    def generate_base_keyframe(self, pan_degrees:int, tilt_degrees:int):
        new_frame = Keyframe(target_time=self.transition_time, name="base")
        new_frame.servo_destination["pan"]  = pan_degrees
        new_frame.servo_destination["tilt"] = tilt_degrees
        return new_frame

    def relax_all_servos(self):
        self.servo_registry.servos["pan"].relax()
        self.servo_registry.servos["tilt"].relax()

    def get_next_action(self):
        next_action = None
        current_time = millis()
        with self._queue_lock:
            if self.action_queue and self.action_queue[0].timestamp <= current_time:
                next_action = heapq.heappop(self.action_queue)
        if next_action:
            next_action.set_frame_times(current_time)
        return next_action
    
    def add_action_to_queue(self, new_action: Action):
        with self._queue_lock:
            heapq.heappush(self.action_queue, new_action)

