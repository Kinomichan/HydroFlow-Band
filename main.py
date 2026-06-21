from machine import Pin, I2C, ADC, RTC
import time
import os

# ==========================================
# M5StickS3 / Grove GSR Sensor Reader
# ==========================================

# 1. Initialize internal I2C bus (for PMIC control)
# The internal PMIC (PY32L020) on M5StickS3 is connected to GPIO 47 (SDA) and GPIO 48 (SCL).
try:
    internal_i2c = I2C(0, sda=Pin(47), scl=Pin(48), freq=100000)
    print("Internal I2C initialized successfully.")
except Exception as e:
    print("Failed to initialize internal I2C:", e)

# PMIC register settings
PMIC_ADDR = 0x6E  # I2C address of PMIC (PY32)
REG_POWER = 0x06  # Power control register
BOOST_BIT = 0x08  # Bit 3: 5V Boost (Provides 5V power to the Grove connector)

def enable_grove_5v():
    """
    Enables the 5V output (Boost circuit) on the Grove port.
    Retries up to 3 times in case the PMIC is in sleep mode.
    """
    for attempt in range(3):
        try:
            # Read the current register value
            current_val = internal_i2c.readfrom_mem(PMIC_ADDR, REG_POWER, 1)[0]
            # Set Bit 3 to ON
            new_val = current_val | BOOST_BIT
            # Write the new value back to the register
            internal_i2c.writeto_mem(PMIC_ADDR, REG_POWER, bytes([new_val]))
            print("PMIC 5V Boost output enabled. (Reg 0x06 -> 0x{:02X})".format(new_val))
            return True
        except Exception as e:
            print("PMIC connection attempt {} failed: {}".format(attempt + 1, e))
            time.sleep_ms(50)
    return False

# Start 5V power delivery to Grove port
if not enable_grove_5v():
    print("Warning: Could not enable Grove 5V. Sensor might not power up.")

# 2. Initialize GSR sensor connection pin (ADC)
# The analog signal (SIG/SDA) on M5StickS3 Grove port (Port A) is connected to GPIO 1.
# (The white SCL wire connects to GPIO 2, but it is not used since GSR is a single analog channel)
adc_pin = Pin(1, Pin.IN)
adc = ADC(adc_pin)

# Configure ADC input range (to read from 0V to approx 3.3V)
# Uses the ESP32-S3 12-bit ADC (values from 0 to 4095)
adc.atten(ADC.ATTN_11DB)

# Initialize RTC
rtc = RTC()

LOG_FILE = "gsr_readings.log"
MAX_LOG_SIZE = 100 * 1024  # 100 KB

def log_to_file(line):
    try:
        # Check size and rotate if necessary
        try:
            stat = os.stat(LOG_FILE)
            if stat[6] > MAX_LOG_SIZE:
                try:
                    os.remove(LOG_FILE + ".bak")
                except OSError:
                    pass
                os.rename(LOG_FILE, LOG_FILE + ".bak")
                print("[Info] Log file rotated.")
        except OSError:
            # File doesn't exist yet
            pass
            
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print("Failed to write to log file:", e)

# 3. Main sensor reading loop
print("\n--- Start GSR Reading (Press Ctrl+C to stop) ---")
print("Timestamp | RawVal | Voltage(mV) | Skin_Resistance(kOhm) | Samples")

# Wait a moment for stabilization
time.sleep(1.0)

while True:
    try:
        raw_sum = 0
        uv_sum = 0
        count = 0
        
        # Integrate (sample) for exactly 10 seconds (10000 milliseconds)
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < 10000:
            raw_sum += adc.read()
            # read_uv() returns internal calibrated voltage in microvolts
            uv_sum += adc.read_uv()
            count += 1
            # 10ms sampling interval (approx. 100 samples per second)
            time.sleep_ms(10)
            
        raw_avg = raw_sum / count
        voltage_mv = (uv_sum / count) / 1000.0  # Convert to millivolts
        
        # Apply official Seeed Studio Grove GSR formula (designed for 10-bit ADC)
        # Downsample the 12-bit ADC reading to 10-bit (0 to 1023)
        adc_10bit = int(raw_avg) >> 2
        
        # Formula: ((1024 + 2 * ADC_Value) * 10000) / (512 - ADC_Value)
        # Skip calculation if the denominator is 0 or negative (extremely low resistance or not connected)
        denominator = 512 - adc_10bit
        if denominator > 0:
            resistance = ((1024 + 2 * adc_10bit) * 10000) / denominator
            resistance_k = resistance / 1000.0  # Convert to kOhm
            res_str = "{:.2f} kOhm".format(resistance_k)
        else:
            # Resistance is beyond measurement limit or fingers are not in contact
            res_str = "Out of Range (No Contact)"
            
        now = rtc.datetime()
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            now[0], now[1], now[2], now[4], now[5], now[6]
        )
        
        log_line = "[{}] Raw: {:4.1f} | Voltage: {:.2f} mV | Resistance: {} | Samples: {}".format(
            timestamp, raw_avg, voltage_mv, res_str, count
        )
        print(log_line)
        log_to_file(log_line)
        
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
        break
    except Exception as e:
        print("Error during reading:", e)
        time.sleep(1.0)
