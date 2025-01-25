import time
from .PCA9685Actuator import PCA9685Actuator

def map_range(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min

class ServoActuator():

    # Properties for each servo
    SERVO_MIN_PWM = 500
    SERVO_MAX_PWM = 2500
    SERVO_NEUTRAL = 1500

    SERVO_MAX_DEG =  90
    SERVO_MIN_DEG = -90

    def __init__(self, id=0, name='', min_angle=-90, max_angle=90, offset=0, neutral_angle=0, is_reversed=False, pwm=None):
        self.id            = id
        self.name          = name
        self.min_angle     = min_angle
        self.max_angle     = max_angle
        self.offset        = offset
        self.is_connected  = True
        self.is_reversed   = is_reversed
        self.neutral_angle = neutral_angle
        self.current_angle = neutral_angle
        if pwm is None:
            new_pwm = PCA9685Actuator(0x40, debug=False)
            new_pwm.setPWMFreq(50)
            self.pwm = new_pwm
        else:
            self.pwm = pwm

    def initialize(self):
        pass

    def write_value(self, new_angle=0):
        if not self.is_connected:
            return

        if new_angle > self.max_angle:
            self.current_angle = self.max_angle
        elif new_angle < self.min_angle:
            self.current_angle = self.min_angle
        else:
            self.current_angle = new_angle

        if self.is_reversed:
            angle_offset = map_range(self.current_angle - self.neutral_angle, \
                                                          self.SERVO_MIN_DEG, \
                                                          self.SERVO_MAX_DEG, \
                                                          self.SERVO_MIN_PWM, \
                                                          self.SERVO_MAX_PWM)
        else:
            angle_offset = map_range(self.current_angle + self.neutral_angle, \
                                                          self.SERVO_MAX_DEG, \
                                                          self.SERVO_MIN_DEG, \
                                                          self.SERVO_MIN_PWM, \
                                                          self.SERVO_MAX_PWM)
        output_pulse = self.offset + angle_offset

        if output_pulse > self.SERVO_MAX_PWM:
            output_pulse = self.SERVO_MAX_PWM
        elif output_pulse < self.SERVO_MIN_PWM:
            output_pulse = self.SERVO_MIN_PWM
            
        self.pwm.write_value(self.id, int(output_pulse))

    def relax(self):
        self.pwm.setPWM(self.id, 0, 0)
        
    def neutral_position(self, neutral_offset=0):
        self.write_value( self.neutral_angle + neutral_offset)
    
    def read_value(self):
        values = []
        values.append(self.current_angle)
        return values
