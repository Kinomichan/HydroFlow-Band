from machine import Pin, I2C, ADC, RTC, SPI
import time
import os
import framebuf

# ==========================================
# M5StickS3 / Grove GSR Sensor Reader with Display
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

def enable_lcd_power():
    """
    Enables the L3B power domain on the PMIC to power up the LCD display.
    This routes power to the ST7789P3 screen.
    """
    try:
        # Clear bit 2 of register 0x16 (Configure GPIO2 of PM1 as GPIO)
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x16, 1)[0]
        val &= ~(1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x16, bytes([val]))
        
        # Set bit 2 of register 0x10 (Configure GPIO2 mode as Output)
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x10, 1)[0]
        val |= (1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x10, bytes([val]))
        
        # Clear bit 2 of register 0x13 (Configure GPIO2 as Push-Pull)
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x13, 1)[0]
        val &= ~(1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x13, bytes([val]))
        
        # Set bit 2 of register 0x11 (Set GPIO2 output HIGH to enable LCD power rail)
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x11, 1)[0]
        val |= (1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x11, bytes([val]))
        
        # Disable I2C idle sleep mode (Write 0x00 to register 0x09)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x09, bytes([0x00]))
        print("PMIC LCD power rail enabled.")
        return True
    except Exception as e:
        print("Failed to enable PMIC LCD power:", e)
        return False

# Start power delivery
if not enable_grove_5v():
    print("Warning: Could not enable Grove 5V. Sensor might not power up.")

if not enable_lcd_power():
    print("Warning: Could not enable LCD power rail. Display might remain blank.")
time.sleep_ms(100)

# 2. Turn on display backlight (GPIO 38 controls backlight on M5StickS3)
bl = Pin(38, Pin.OUT)
bl.on()

# 3. SPI display setup
# CS: 41, DC: 45, RST: 21, SCLK: 40, MOSI: 39
spi = SPI(1, baudrate=40000000, sck=Pin(40), mosi=Pin(39))
cs = Pin(41, Pin.OUT, value=1)
dc = Pin(45, Pin.OUT, value=0)
rst = Pin(21, Pin.OUT, value=1)

# Reset display controller
rst.off()
time.sleep_ms(50)
rst.on()
time.sleep_ms(150)

def write_cmd(cmd):
    dc.off()
    cs.off()
    spi.write(bytes([cmd]))
    cs.on()

def write_data(data):
    dc.on()
    cs.off()
    spi.write(data)
    cs.on()

# ST7789 display controller initialization commands
write_cmd(0x01) # SWRESET (Software reset)
time.sleep_ms(150)
write_cmd(0x11) # SLPOUT (Sleep out)
time.sleep_ms(120)

# COLMOD: Interface Pixel Format (0x3A) -> set to 16-bit color (0x55)
write_cmd(0x3A)
write_data(bytes([0x55]))

# MADCTL: Memory Data Access Control (0x36) -> BGR color order filter (0x08)
write_cmd(0x36)
write_data(bytes([0x08]))

# INVON: Display Inversion On (0x21) -> required for colors to display correctly
write_cmd(0x21)

# NORON: Normal Display Mode On (0x13)
write_cmd(0x13)
time.sleep_ms(10)

# DISPON: Display On (0x29)
write_cmd(0x29)
time.sleep_ms(100)

# LCD dimensions and offsets
width = 135
height = 240
offset_x = 52
offset_y = 40

def set_window(x0, y0, x1, y1):
    """Sets the active window area to draw pixels in on the ST7789 display."""
    x0 += offset_x
    x1 += offset_x
    y0 += offset_y
    y1 += offset_y
    write_cmd(0x2A) # Column Address Set
    write_data(bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
    write_cmd(0x2B) # Row Address Set
    write_data(bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
    write_cmd(0x2C) # RAM Write

@micropython.viper
def swap_bytes(buf_ptr: ptr8, size: int):
    """Swaps bytes in-place to convert little-endian RGB565 to big-endian."""
    for i in range(0, size, 2):
        t = buf_ptr[i]
        buf_ptr[i] = buf_ptr[i+1]
        buf_ptr[i+1] = t

def draw_large_text(fb_target, text, x, y, scale, color):
    """Draws custom scaled text using standard 8x8 font bits onto a framebuffer."""
    tw = len(text) * 8
    th = 8
    temp_buf = bytearray(tw * th // 8)
    temp_fb = framebuf.FrameBuffer(temp_buf, tw, th, framebuf.MONO_VLSB)
    temp_fb.text(text, 0, 0, 1)
    
    for tx in range(tw):
        for ty in range(th):
            if temp_fb.pixel(tx, ty):
                fb_target.fill_rect(x + tx * scale, y + ty * scale, scale, scale, color)

# Initialize display framebuffer
buf_size = width * height * 2
fb_buf = bytearray(buf_size)
fb = framebuf.FrameBuffer(fb_buf, width, height, framebuf.RGB565)

# 4. Initialize GSR sensor connection pin (ADC)
# The analog signal (SIG/SDA) on M5StickS3 Grove port (Port A) is connected to GPIO 1.
adc_pin = Pin(1, Pin.IN)
adc = ADC(adc_pin)
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

# 5. Main sensor reading loop
print("\n--- Start GSR Reading (Press Ctrl+C to stop) ---")
print("Timestamp | RawVal | Voltage(mV) | Skin_Resistance(kOhm) | Samples")

# Wait a moment for stabilization
time.sleep(1.0)

while True:
    try:
        raw_sum = 0
        uv_sum = 0
        count = 0
        
        # Integrate (sample) for exactly 1 second (1000 milliseconds)
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < 1000:
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
            res_str = "{:.1f}k".format(resistance_k)
            log_res_str = "{:.2f} kOhm".format(resistance_k)
            connected = True
        else:
            # Resistance is beyond measurement limit or fingers are not in contact
            res_str = "---"
            log_res_str = "Out of Range (No Contact)"
            connected = False
            
        now = rtc.datetime()
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            now[0], now[1], now[2], now[4], now[5], now[6]
        )
        time_str = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], now[6])
        date_str = "{:04d}-{:02d}-{:02d}".format(now[0], now[1], now[2])
        
        log_line = "[{}] Raw: {:4.1f} | Voltage: {:.2f} mV | Resistance: {} | Samples: {}".format(
            timestamp, raw_avg, voltage_mv, log_res_str, count
        )
        print(log_line)
        log_to_file(log_line)
        
        # ==========================================
        # Render UI onto the frame buffer
        # ==========================================
        # Clear screen with pure black
        fb.fill(0x0000)
        
        # Header bar
        fb.fill_rect(0, 0, width, 24, 0x9000) # Dark red / crimson background
        fb.text("GSR MONITOR", 23, 8, 0xFFFF)  # Centered title
        fb.line(0, 24, width, 24, 0xC618)      # Light grey separator line
        
        # 1. Raw Value Section
        fb.text("RAW VALUE", 31, 35, 0x8410)   # Grey label
        raw_val_str = "{:d}".format(int(raw_avg))
        raw_len = len(raw_val_str)
        # Choose scale 4 if value fits, otherwise scale 3
        raw_scale = 4 if raw_len <= 4 else 3
        raw_w = raw_len * 8 * raw_scale
        raw_x = (width - raw_w) // 2
        # Color coding: Green if contact is detected, Orange if disconnected
        raw_color = 0x07E0 if connected else 0xFD20
        draw_large_text(fb, raw_val_str, raw_x, 50, raw_scale, raw_color)
        
        # Connection status badge
        if connected:
            fb.fill_rect(21, 90, 93, 14, 0x03E0)  # Dark green pill
            fb.text("CONNECTED", 31, 93, 0xFFFF)
        else:
            fb.fill_rect(17, 90, 101, 14, 0x7800) # Dark red pill
            fb.text("NO CONTACT", 27, 93, 0xFFFF)
            
        # 2. Skin Resistance Section
        fb.text("RESISTANCE", 27, 120, 0x8410)  # Grey label
        res_w = len(res_str) * 8 * 2
        res_x = (width - res_w) // 2
        draw_large_text(fb, res_str, res_x, 135, 2, 0xFFE0) # Yellow text
        
        # 3. Date & Time Section (Footer)
        fb.line(0, 175, width, 175, 0x4208)    # Divider line
        fb.text(date_str, 27, 185, 0x8410)      # Centered date in grey
        # Large current time centered
        draw_large_text(fb, time_str, 3, 200, 2, 0x07FF) # Centered time in cyan
        
        # ==========================================
        # Push Frame Buffer to Display SPI
        # ==========================================
        swap_bytes(fb_buf, buf_size)            # Convert endianness
        set_window(0, 0, width - 1, height - 1)
        dc.on()
        cs.off()
        spi.write(fb_buf)
        cs.on()
        
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
        break
    except Exception as e:
        print("Error during reading/display update:", e)
        time.sleep(1.0)
