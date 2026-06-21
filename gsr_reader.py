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

def disable_lcd_power():
    """
    Disables the LCD power rail by setting PMIC GPIO2 to LOW.
    """
    try:
        # Set bit 2 of register 0x11 (Set GPIO2 output LOW to disable LCD power rail)
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x11, 1)[0]
        val &= ~(1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x11, bytes([val]))
        print("PMIC LCD power rail disabled.")
        return True
    except Exception as e:
        print("Failed to disable PMIC LCD power:", e)
        return False

def setup_power_button():
    """
    Configures the PMIC to disable hardware reset on single-click
    and power-off on double-click, allowing BtnPWR to be used as a user button.
    """
    try:
        # Disable single-click reset (set Bit 0 of Reg 0x49)
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x49, 1)[0]
        val |= 0x01
        internal_i2c.writeto_mem(PMIC_ADDR, 0x49, bytes([val]))
        
        # Disable double-click shutdown (set Bit 0 of Reg 0x4A)
        val2 = internal_i2c.readfrom_mem(PMIC_ADDR, 0x4A, 1)[0]
        val2 |= 0x01
        internal_i2c.writeto_mem(PMIC_ADDR, 0x4A, bytes([val2]))
        
        print("PMIC Power Button configured as user input.")
        return True
    except Exception as e:
        print("Failed to configure PMIC Power Button:", e)
        return False

def is_power_button_pressed():
    """
    Reads the PMIC register 0x48 to check if the Power Button is currently pressed.
    Bit 0: BTN_STATE (1=Pressed, 0=Released)
    """
    try:
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x48, 1)[0]
        return (val & 0x01) == 0x01
    except Exception:
        return False

# Start power delivery
if not enable_grove_5v():
    print("Warning: Could not enable Grove 5V. Sensor might not power up.")

if not enable_lcd_power():
    print("Warning: Could not enable LCD power rail. Display might remain blank.")

# Configure Power Button to act as user button instead of hardware reset/shutdown
setup_power_button()

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

def init_lcd():
    # Reset display controller
    rst.off()
    time.sleep_ms(50)
    rst.on()
    time.sleep_ms(150)

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

# Initialize display controller
init_lcd()

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

# 3.5. Initialize KEY1 button (GPIO 11) for display power toggle control
btn = Pin(11, Pin.IN, Pin.PULL_UP)
display_on = True
last_btn_press = 0

# 4. Initialize GSR sensor connection pin (ADC)
# The analog signal (SIG) on M5StickS3 Grove port (Port A) is connected to SCL (GPIO 10 / Yellow wire).
adc_pin = Pin(10, Pin.IN)
adc = ADC(adc_pin)
adc.atten(ADC.ATTN_11DB)

# Initialize RTC
rtc = RTC()

def show_sync_status(title, lines):
    # Clear screen with pure black
    fb.fill(0x0000)
    
    # Header bar
    fb.fill_rect(0, 0, width, 24, 0x9000) # Dark red / crimson background
    fb.text(title, (width - len(title) * 8) // 2, 8, 0xFFFF)
    fb.line(0, 24, width, 24, 0xC618)
    
    # Draw each line of status text
    y = 40
    for text in lines:
        fb.text(text, 10, y, 0xFFFF)
        y += 20
        
    # Push to display
    swap_bytes(fb_buf, buf_size)
    set_window(0, 0, width - 1, height - 1)
    dc.on()
    cs.off()
    spi.write(fb_buf)
    cs.on()

def connect_wifi_and_sync_time():
    import json
    import network
    import ntptime
    
    show_sync_status("WIFI CONNECT", ["Loading config..."])
    
    try:
        with open("wifi_config.json", "r") as f:
            config = json.load(f)
    except Exception as e:
        print("Failed to load wifi_config.json:", e)
        show_sync_status("CONFIG ERROR", [
            "wifi_config.json",
            "not found or",
            "invalid.",
            "Skipping sync."
        ])
        time.sleep(2.0)
        return
        
    ssid = config.get("ssid", "")
    password = config.get("password", "")
    timezone_offset_hours = config.get("timezone_offset_hours", 0)
    
    if ssid == "YOUR_WIFI_SSID" or not ssid:
        print("SSID is not configured. Skipping WiFi/NTP sync.")
        show_sync_status("WIFI SKIP", [
            "SSID not configured",
            "in wifi_config.json",
            "Skipping sync."
        ])
        time.sleep(2.0)
        return
        
    show_sync_status("WIFI CONNECT", [
        "SSID:",
        "  " + ssid[:12] + ("..." if len(ssid) > 12 else ""),
        "Status:",
        "  Connecting..."
    ])
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
    # Wait up to 15 seconds for connection
    connected = False
    for i in range(15):
        if wlan.isconnected():
            connected = True
            break
        time.sleep(1.0)
        show_sync_status("WIFI CONNECT", [
            "SSID:",
            "  " + ssid[:12] + ("..." if len(ssid) > 12 else ""),
            "Status:",
            "  Connecting" + "." * (i % 4 + 1)
        ])
        
    if not connected:
        print("WiFi connection failed.")
        show_sync_status("WIFI FAIL", [
            "SSID:",
            "  " + ssid[:12] + ("..." if len(ssid) > 12 else ""),
            "Status:",
            "  Connection Failed!",
            "Proceeding..."
        ])
        wlan.active(False)
        time.sleep(2.0)
        return
        
    ip = wlan.ifconfig()[0]
    print("WiFi connected! IP:", ip)
    show_sync_status("NTP SYNC", [
        "WiFi: Connected",
        "IP: " + ip,
        "NTP Syncing..."
    ])
    
    # Try to synchronize time
    sync_success = False
    for attempt in range(3):
        try:
            ntp_host = config.get("ntp_host", "pool.ntp.org")
            ntptime.host = ntp_host
            ntptime.settime()
            sync_success = True
            break
        except Exception as e:
            print("NTP sync attempt {} failed: {}".format(attempt + 1, e))
            time.sleep(1.0)
            
    if sync_success:
        try:
            utc_epoch = time.time()
            local_epoch = utc_epoch + int(timezone_offset_hours * 3600)
            tm = time.localtime(local_epoch)
            rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
            
            now_dt = rtc.datetime()
            time_str = "{:02d}:{:02d}:{:02d}".format(now_dt[4], now_dt[5], now_dt[6])
            print("NTP Sync Success! Time set to:", time_str)
            show_sync_status("SYNC SUCCESS", [
                "NTP Sync: OK",
                "Time Set:",
                "  " + time_str,
                "Saving power..."
            ])
        except Exception as e:
            print("Failed to set local time:", e)
            show_sync_status("SYNC ERROR", [
                "NTP Sync: OK",
                "Failed to set",
                "local timezone!"
            ])
    else:
        print("NTP sync failed.")
        show_sync_status("SYNC FAIL", [
            "WiFi: Connected",
            "NTP Sync: Failed!",
            "Proceeding..."
        ])
        
    time.sleep(1.5)
    
    print("Disconnecting WiFi to save power...")
    show_sync_status("WIFI CLOSE", [
        "Disconnecting WiFi",
        "to save power..."
    ])
    try:
        wlan.disconnect()
        wlan.active(False)
    except Exception as e:
        print("Failed to disable WLAN interface:", e)
        
    show_sync_status("WIFI CLOSE", [
        "WiFi Interface OFF",
        "Power Saved.",
        "Starting GSR..."
    ])
    time.sleep(1.0)

# Connect to WiFi and synchronize time
connect_wifi_and_sync_time()

def generate_log_filename():
    now = rtc.datetime()
    # now format: (year, month, day, weekday, hour, minute, second, subsecond)
    timestamp = "{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}".format(
        now[0], now[1], now[2], now[4], now[5], now[6]
    )
    
    base_name = "gsr_{}".format(timestamp)
    ext = ".log"
    filename = base_name + ext
    
    # Avoid duplicate filenames in case of rapid restarts or RTC reset to default (e.g. 2000-01-01)
    counter = 1
    while True:
        try:
            os.stat(filename)
            # File exists, increment suffix
            filename = "{}_{}{}".format(base_name, counter, ext)
            counter += 1
        except OSError:
            # File does not exist, safe to use
            break
            
    return filename

LOG_FILE = generate_log_filename()
print("Logging to file:", LOG_FILE)
MAX_LOG_SIZE = 100 * 1024  # 100 KB

def log_to_file(line):
    try:
        # Check size and rotate if necessary
        try:
            stat = os.stat(LOG_FILE)
            if stat[6] > MAX_LOG_SIZE:
                bak_file = LOG_FILE + ".bak"
                try:
                    os.remove(bak_file)
                except OSError:
                    pass
                os.rename(LOG_FILE, bak_file)
                print("[Info] Log file rotated to", bak_file)
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

# Accumulation variables for 10-second averages
accum_raw_sum = 0
accum_uv_sum = 0
accum_count = 0
loop_count = 0

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
            
            # Check KEY1 press or Power Button press
            btn_pressed = False
            if btn.value() == 0:
                btn_pressed = True
            elif is_power_button_pressed():
                btn_pressed = True
                
            if btn_pressed:
                now_ms = time.ticks_ms()
                if time.ticks_diff(now_ms, last_btn_press) > 300:
                    last_btn_press = now_ms
                    display_on = not display_on
                    if display_on:
                        print("[System] Turning display ON (Normal Mode)...")
                        enable_lcd_power()
                        time.sleep_ms(50)
                        init_lcd()
                        bl.on()
                        print("[System] Display ON complete.")
                    else:
                        print("[System] Turning display OFF (Power Saving Mode)...")
                        bl.off()
                        try:
                            write_cmd(0x28) # Display Off
                            write_cmd(0x10) # Sleep In
                        except Exception as e:
                            print("[System] Failed display sleep cmd:", e)
                        disable_lcd_power()
                        print("[System] Display OFF complete.")
            
            # 10ms sampling interval (approx. 100 samples per second)
            time.sleep_ms(10)
            
        # Calculate 1-second average for display purposes
        raw_avg_1s = raw_sum / count
        voltage_mv_1s = (uv_sum / count) / 1000.0  # Convert to millivolts
        
        # Apply official Seeed Studio Grove GSR formula for display
        adc_10bit_1s = int(voltage_mv_1s * 1023 / 5000.0)
        denominator_1s = 512 - adc_10bit_1s
        if denominator_1s > 0:
            resistance_1s = ((1024 + 2 * adc_10bit_1s) * 10000) / denominator_1s
            resistance_k_1s = resistance_1s / 1000.0
            res_str = "{:.1f}k".format(resistance_k_1s)
            connected = True
        else:
            res_str = "---"
            connected = False
            
        # Accumulate for 10-second logging
        accum_raw_sum += raw_sum
        accum_uv_sum += uv_sum
        accum_count += count
        loop_count += 1
        
        # Log to file every 10 seconds
        if loop_count >= 10:
            raw_avg_10s = accum_raw_sum / accum_count
            voltage_mv_10s = (accum_uv_sum / accum_count) / 1000.0
            
            adc_10bit_10s = int(voltage_mv_10s * 1023 / 5000.0)
            denominator_10s = 512 - adc_10bit_10s
            if denominator_10s > 0:
                resistance_10s = ((1024 + 2 * adc_10bit_10s) * 10000) / denominator_10s
                resistance_k_10s = resistance_10s / 1000.0
                log_res_str = "{:.2f} kOhm".format(resistance_k_10s)
            else:
                log_res_str = "Out of Range (No Contact)"
                
            now = rtc.datetime()
            timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                now[0], now[1], now[2], now[4], now[5], now[6]
            )
            
            log_line = "[{}] Raw: {:4.1f} | Voltage: {:.2f} mV | Resistance: {} | Samples: {}".format(
                timestamp, raw_avg_10s, voltage_mv_10s, log_res_str, accum_count
            )
            print("[Log] " + log_line)
            log_to_file(log_line)
            
            # Reset accumulation variables
            accum_raw_sum = 0
            accum_uv_sum = 0
            accum_count = 0
            loop_count = 0
            
        now = rtc.datetime()
        time_str = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], now[6])
        date_str = "{:04d}-{:02d}-{:02d}".format(now[0], now[1], now[2])
        
        # ==========================================
        # Render UI onto the frame buffer
        # ==========================================
        if display_on:
            # Clear screen with pure black
            fb.fill(0x0000)
            
            # Header bar
            fb.fill_rect(0, 0, width, 24, 0x9000) # Dark red / crimson background
            fb.text("GSR MONITOR", 23, 8, 0xFFFF)  # Centered title
            fb.line(0, 24, width, 24, 0xC618)      # Light grey separator line
            
            # 1. Raw Value Section
            fb.text("RAW VALUE", 31, 35, 0x8410)   # Grey label
            raw_val_str = "{:d}".format(int(raw_avg_1s))
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
