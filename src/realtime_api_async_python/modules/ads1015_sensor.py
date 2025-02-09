import time
import smbus

#i2c address
ADS_I2C_ADDRESS = 0x48

#Pointer Register
ADS_POINTER_CONVERT               = 0x00
ADS_POINTER_CONFIG                = 0x01
ADS_POINTER_LOWTHRESH             = 0x02  
ADS_POINTER_HIGHTHRESH            = 0x03

#Config Register
ADS_CONFIG_OS_BUSY                  = 0x0000      #Device is currently performing a conversion
ADS_CONFIG_OS_NOBUSY                = 0x8000      #Device is not currently performing a conversion              
ADS_CONFIG_OS_SINGLE_CONVERT        = 0x8000      #Start a single conversion (when in power-down state)  
ADS_CONFIG_OS_NO_EFFECT             = 0x0000      #No effect
ADS_CONFIG_MUX_MUL_0_1              = 0x0000      #Input multiplexer,AINP = AIN0 and AINN = AIN1(default)
ADS_CONFIG_MUX_MUL_0_3              = 0x1000      #Input multiplexer,AINP = AIN0 and AINN = AIN3
ADS_CONFIG_MUX_MUL_1_3              = 0x2000      #Input multiplexer,AINP = AIN1 and AINN = AIN3
ADS_CONFIG_MUX_MUL_2_3              = 0x3000      #Input multiplexer,AINP = AIN2 and AINN = AIN3
ADS_CONFIG_MUX_SINGLE_0             = 0x4000      #SINGLE,AIN0
ADS_CONFIG_MUX_SINGLE_1             = 0x5000      #SINGLE,AIN1
ADS_CONFIG_MUX_SINGLE_2             = 0x6000      #SINGLE,AIN2
ADS_CONFIG_MUX_SINGLE_3             = 0x7000      #SINGLE,AIN3
ADS_CONFIG_PGA_6144                 = 0x0000      #Gain= +/- 6.144V
ADS_CONFIG_PGA_4096                 = 0x0200      #Gain= +/- 4.096V
ADS_CONFIG_PGA_2048                 = 0x0400      #Gain= +/- 2.048V(default)
ADS_CONFIG_PGA_1024                 = 0x0600      #Gain= +/- 1.024V
ADS_CONFIG_PGA_512                  = 0x0800      #Gain= +/- 0.512V
ADS_CONFIG_PGA_256                  = 0x0A00      #Gain= +/- 0.256V
ADS_CONFIG_MODE_CONTINUOUS          = 0x0000      #Device operating mode:Continuous-conversion mode        
ADS_CONFIG_MODE_NOCONTINUOUS        = 0x0100      #Device operating mode：Single-shot mode or power-down state (default)
ADS_CONFIG_DR_RATE_128              = 0x0000      #Data rate=128SPS
ADS_CONFIG_DR_RATE_250              = 0x0020      #Data rate=250SPS
ADS_CONFIG_DR_RATE_490              = 0x0040      #Data rate=490SPS
ADS_CONFIG_DR_RATE_920              = 0x0060      #Data rate=920SPS
ADS_CONFIG_DR_RATE_1600             = 0x0080      #Data rate=1600SPS
ADS_CONFIG_DR_RATE_2400             = 0x00A0      #Data rate=2400SPS
ADS_CONFIG_DR_RATE_3300             = 0x00C0      #Data rate=3300SPS
ADS_CONFIG_COMP_MODE_WINDOW         = 0x0010      #Comparator mode：Window comparator
ADS_CONFIG_COMP_MODE_TRADITIONAL    = 0x0000      #Comparator mode：Traditional comparator (default)
ADS_CONFIG_COMP_POL_LOW             = 0x0000      #Comparator polarity：Active low (default)
ADS_CONFIG_COMP_POL_HIGH            = 0x0008      #Comparator polarity：Active high
ADS_CONFIG_COMP_LAT                 = 0x0004      #Latching comparator 
ADS_CONFIG_COMP_NONLAT              = 0x0000      #Nonlatching comparator (default)
ADS_CONFIG_COMP_QUE_ONE             = 0x0000      #Assert after one conversion
ADS_CONFIG_COMP_QUE_TWO             = 0x0001      #Assert after two conversions
ADS_CONFIG_COMP_QUE_FOUR            = 0x0002      #Assert after four conversions
ADS_CONFIG_COMP_QUE_NON             = 0x0003      #Disable comparator and set ALERT/RDY pin to high-impedance (default)

class ADS1015Sensor():
    _instance = None

    def __init__(self, address=ADS_I2C_ADDRESS):
        if not ADS1015Sensor._instance:
            self._address = address
            self._bus = smbus.SMBus(1)
            self.Config_Set = 0
            self.initialize()
            
            ADS1015Sensor._instance = self
        else:
            raise Exception("You cannot create another ADS1015Sensor class")

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = ADS1015Sensor()
        return cls._instance

    def read_value(self):
        values = []
        for channel in range(4):
            values.append(self.single_read(channel))
        return values

    def _read_u16(self,cmd):
        LSB = self._bus.read_byte_data(self._address,cmd)
        MSB = self._bus.read_byte_data(self._address,cmd+1)
        return (LSB << 8) + MSB

    def _write_word(self, cmd, val):
        Val_H=val&0xff
        Val_L=val>>8
        val=(Val_H<<8)|Val_L
        self._bus.write_word_data(self._address,cmd,val)

    def initialize(self):
        self.Config_Set =  ( ADS_CONFIG_MODE_NOCONTINUOUS        |   #mode：Single-shot mode or power-down state    (default)
                        ADS_CONFIG_PGA_4096                 |   #Gain= +/- 4.096V                              (default)
                        ADS_CONFIG_COMP_QUE_NON             |   #Disable comparator                            (default)
                        ADS_CONFIG_COMP_NONLAT              |   #Nonlatching comparator                        (default)
                        ADS_CONFIG_COMP_POL_LOW             |   #Comparator polarity：Active low               (default)
                        ADS_CONFIG_COMP_MODE_TRADITIONAL    |   #Traditional comparator                        (default)
                        ADS_CONFIG_DR_RATE_1600             )   #Data rate=1600SPS                             (default)
        self._write_word(ADS_POINTER_CONFIG,self.Config_Set)
        time.sleep(0.01)

    #... (all the other methods from the ADS1015 class in ADS1015.py)

    def single_read(self, channel):                    #Read single channel data
        data=0
        if channel == 0:
            self.Config_Set |= ADS_CONFIG_MUX_SINGLE_0
        elif channel == 1:
            self.Config_Set |= ADS_CONFIG_MUX_SINGLE_1
        elif channel == 2:
            self.Config_Set |= ADS_CONFIG_MUX_SINGLE_2
        elif channel == 3:
            self.Config_Set |= ADS_CONFIG_MUX_SINGLE_3
        self.Config_Set |=ADS_CONFIG_OS_SINGLE_CONVERT
        self._write_word(ADS_POINTER_CONFIG, self.Config_Set)
        time.sleep(0.01)
        data=self._read_u16(ADS_POINTER_CONVERT)>>4
        return data

if __name__ == '__main__':
    print("\nADS1015 Test Program ...\r\n")
    ads1015=ADS1015Sensor()
    while True:
        time.sleep(0.5)
        values = ads1015.read_value()
        print('\nAIN0 = %d(%dmv) ,AIN1 = %d(%dmv) ,AIN2 = %d(%dmv) AIN3 = %d(%dmv)\n\r' % tuple(values + [v*2 for v in values]))
