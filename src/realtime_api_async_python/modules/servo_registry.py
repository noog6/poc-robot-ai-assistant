from .pca9685_servo_controller import PCA9685Actuator
from .servo_actuator           import ServoActuator

class ServoRegistry:
    _instance = None

    def __init__(self):
        if not ServoRegistry._instance:
            self.pwm                = PCA9685Actuator(0x40, debug=False)
            self.pwm.setPWMFreq(50)
            self.servos             = self._create_servos()
            ServoRegistry._instance = self
        else:
            raise Exception("You cannot create another ServoRegistry class")

    def _create_servos(self):
        servos = {
            'pan':  ServoActuator(id=9, name='Pan_Servo',  min_angle=-90, max_angle=90, offset=0, neutral_angle=0, is_reversed=False, pwm=self.pwm),
            'tilt': ServoActuator(id=8, name='Tilt_Servo', min_angle=-45, max_angle=45, offset=0, neutral_angle=0, is_reversed=False, pwm=self.pwm)
        }

        return servos

    def get_servos(self):
        """Return the existing servo instances."""
        return self.servos

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = ServoRegistry()
        return cls._instance

    def get_servo_names(self):
        """Return a list of the names of all servos in the registry."""
        return list(self.get_servos().keys())

    def refresh_servos(self):
        """Destroy existing servo objects, reload config, and recreate servos."""
        # 1) Destroy any objects in `self.servos`
        self.servos.clear()
        # 2) Reload the config data
        self.config = self.config_controller.get_config()
        # 3) Recreate the list of servos
        self.servos = self._create_servos()
         
