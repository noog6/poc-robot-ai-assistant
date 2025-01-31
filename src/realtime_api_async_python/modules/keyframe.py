class Keyframe:
    def __init__(self, id=0, name='', target_time=0):
        self.id                = id
        self.name              = name
        self.final_target_time = target_time
        self.is_initialized    = False
        self.servo_steps_left  = -1
        self.servo_step_size   = {"pan" : 0,
                                  "tilt": 0 }
        self.servo_destination = {"pan" : 0,
                                  "tilt": 0 }
        self.audio             = None
        self.next              = None

    def __str__(self):
        return f'pan :{self.servo_destination["pan"]:.3f}' + \
               f'tilt:{self.servo_destination["tilt"]:.3f}'

    def to_dict(self):
        return {
            'id':                self.id,
            'name':              self.name,
            'final_target_time': self.final_target_time,
            'is_initialized':    self.is_initialized,
            'servo_steps_left':  self.servo_steps_left,
            'servo_step_size':   self.servo_step_size,
            'servo_destination': self.servo_destination,
            'audio':             self.audio,
            'next':              self.next
        }

