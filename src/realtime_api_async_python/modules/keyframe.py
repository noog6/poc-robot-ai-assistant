# keyframe.py
class Keyframe:
    def __init__(self, id=0, name='', target_time=0):
        self.id                = id
        self.name              = name
        self.final_target_time = target_time      # duration (ms)
        self.deadline_ms       = None             # absolute (ms) filled by Action.set_frame_times()
        self.is_initialized    = False
        self.start_time_ms     = None
        self.duration_ms       = None
        self.start_pos         = {"pan": 0.0, "tilt": 0.0}
        self.delta_pos         = {"pan": 0.0, "tilt": 0.0}
        self.servo_destination = {"pan": 0, "tilt": 0}
        self.audio             = None
        self.next              = None

    def has_deadline(self) -> bool:
        return self.deadline_ms is not None

    def remaining_ms(self, now_ms: int) -> int:
        if self.deadline_ms is None:
            return 0
        return max(0, int(self.deadline_ms - now_ms))

    def __str__(self):
        return f'pan :{self.servo_destination["pan"]:.3f} ' + \
               f'tilt:{self.servo_destination["tilt"]:.3f}'

    def to_dict(self):
        return {
            'id':                self.id,
            'name':              self.name,
            'final_target_time': self.final_target_time,
            'is_initialized':    self.is_initialized,
            'servo_destination': self.servo_destination,
            'audio':             self.audio,
            'next':              self.next
        }

