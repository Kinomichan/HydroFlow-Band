import gc
gc.collect()
from machine import Pin, ADC, RTC
import time
import os
import pmic_lcd
import wifi_sync

# Unpack LCD and PMIC variables/functions from pmic_lcd for ease of use
fb = pmic_lcd.fb
fb_buf = pmic_lcd.fb_buf
bl = pmic_lcd.bl
btn = pmic_lcd.btn
is_power_button_pressed = pmic_lcd.is_power_button_pressed
draw_large_text = pmic_lcd.draw_large_text
swap_bytes = pmic_lcd.swap_bytes
set_window = pmic_lcd.set_window
width = pmic_lcd.width
height = pmic_lcd.height
buf_size = pmic_lcd.buf_size
enable_lcd_power = pmic_lcd.enable_lcd_power
disable_lcd_power = pmic_lcd.disable_lcd_power
init_lcd = pmic_lcd.init_lcd
write_cmd = pmic_lcd.write_cmd

# Initialize GSR sensor connection pin (ADC)
adc_pin = Pin(10, Pin.IN)
adc = ADC(adc_pin)
adc.atten(ADC.ATTN_11DB)

# Initialize RTC
rtc = RTC()

# Connect to WiFi and synchronize time
wifi_sync.connect_wifi_and_sync_time(rtc)

display_on = True
last_btn_press = 0

def generate_log_filename():
    now = rtc.datetime()
    timestamp = "{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}".format(
        now[0], now[1], now[2], now[4], now[5], now[6]
    )
    base_name = "gsr_{}".format(timestamp)
    ext = ".log"
    filename = base_name + ext
    counter = 1
    while True:
        try:
            os.stat(filename)
            filename = "{}_{}{}".format(base_name, counter, ext)
            counter += 1
        except OSError:
            break
    return filename

LOG_FILE = None
MAX_LOG_SIZE = 100 * 1024

def log_to_file(line):
    try:
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
            pass
            
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print("Failed to write to log file:", e)

# Global baseline variables determined by calibration
baseline_raw = 512.0
baseline_uv = 2500.0 * 1000.0
baseline_cond_us = 7.41  # Conductance in microSiemens (1000 / 135.0 kOhm)

def run_calibration():
    global baseline_raw, baseline_uv, baseline_cond_us
    
    print("\n--- Starting GSR Calibration (10s) ---")
    print("Please touch the electrodes and remain still.")
    
    duration_s = 10
    samples_per_update = 20
    total_updates = (duration_s * 1000) // (samples_per_update * 10)
    
    raw_samples = []
    uv_samples = []
    skipped = False
    
    for update in range(total_updates):
        btn_pressed = False
        if btn.value() == 0:
            btn_pressed = True
        elif is_power_button_pressed():
            btn_pressed = True
            
        if btn_pressed:
            print("Calibration skipped by user.")
            skipped = True
            break
            
        update_raw_sum = 0
        update_uv_sum = 0
        update_count = 0
        for _ in range(samples_per_update):
            val = adc.read()
            uv = adc.read_uv()
            raw_samples.append(val)
            uv_samples.append(uv)
            
            update_raw_sum += val
            update_uv_sum += uv
            update_count += 1
            time.sleep_ms(10)
            
        avg_raw = update_raw_sum / update_count
        avg_uv = update_uv_sum / update_count
        avg_mv = avg_uv / 1000.0
        
        adc_10bit = int(avg_mv * 1023 / 5000.0)
        denom = 512 - adc_10bit
        if denom > 0:
            res = ((1024 + 2 * adc_10bit) * 10000) / denom
            res_k = res / 1000.0
            cond_us = 1000.0 / res_k if res_k > 0 else 0.0
            res_str = "{:.2f}uS".format(cond_us)
            connected = True
        else:
            res_str = "---"
            connected = False
            
        fb.fill(0x0000)
        
        fb.fill_rect(0, 0, width, 24, 0x18C3)
        fb.text("CALIBRATION", 23, 8, 0xFDA0)
        fb.line(0, 24, width, 24, 0xC618)
        
        fb.rect(8, 36, width - 16, 128, 0x3186)
        fb.text("ESTABLISHING", 20, 46, 0x8410)
        fb.text("BASELINE", 36, 58, 0x8410)
        
        secs_left = duration_s - int((update * samples_per_update * 10) / 1000)
        secs_str = "{:d}s".format(secs_left)
        draw_large_text(fb, secs_str, (width - len(secs_str)*8*3)//2, 76, 3, 0xFFFF)
        
        progress_pct = int((update + 1) / total_updates * 100)
        bar_x = 16
        bar_y = 112
        bar_w = width - 32
        bar_h = 8
        fb.rect(bar_x, bar_y, bar_w, bar_h, 0x18C3)
        fb.fill_rect(bar_x + 2, bar_y + 2, int((bar_w - 4) * progress_pct / 100), bar_h - 4, 0xFDA0)
        
        raw_text = "RAW: {:d}".format(int(avg_raw))
        fb.text(raw_text, (width - len(raw_text)*8)//2, 130, 0xC618)
        if connected:
            res_text = "COND: {}".format(res_str)
            fb.text(res_text, (width - len(res_text)*8)//2, 144, 0x07E0)
        else:
            res_text = "NO CONTACT"
            fb.text(res_text, (width - len(res_text)*8)//2, 144, 0xF800)
            
        fb.line(0, 175, width, 175, 0x4208)
        fb.text("KEEP STILL", 27, 185, 0xFDA0)
        fb.text("Btn A to Skip", 15, 205, 0x8410)
        
        swap_bytes(fb_buf, buf_size)
        set_window(0, 0, width - 1, height - 1)
        dc = pmic_lcd.dc
        cs = pmic_lcd.cs
        spi = pmic_lcd.spi
        dc.on()
        cs.off()
        spi.write(fb_buf)
        cs.on()
        
    if not skipped and len(raw_samples) > 0:
        baseline_raw = sum(raw_samples) / len(raw_samples)
        baseline_uv = sum(uv_samples) / len(uv_samples)
        
        baseline_mv = baseline_uv / 1000.0
        adc_10bit = int(baseline_mv * 1023 / 5000.0)
        denom = 512 - adc_10bit
        if denom > 0:
            res = ((1024 + 2 * adc_10bit) * 10000) / denom
            res_k = res / 1000.0
            baseline_cond_us = 1000.0 / res_k if res_k > 0 else 0.0
        else:
            baseline_cond_us = None
    else:
        baseline_raw = 512.0
        baseline_uv = 2500.0 * 1000.0
        baseline_cond_us = 7.41
        
    fb.fill(0x0000)
    fb.fill_rect(0, 0, width, 24, 0x18C3)
    status_title = "CALIB SKIPPED" if skipped else "CALIB COMPLETE"
    fb.text(status_title, (width - len(status_title)*8)//2, 8, 0x07E0 if not skipped else 0xFDA0)
    fb.line(0, 24, width, 24, 0xC618)
    
    fb.rect(8, 36, width - 16, 128, 0x3186)
    fb.text("BASELINE RAW:", 14, 48, 0x8410)
    raw_res_str = "{:.1f}".format(baseline_raw)
    fb.text(raw_res_str, (width - len(raw_res_str)*8)//2, 64, 0xFFFF)
    
    fb.text("BASELINE COND:", 14, 88, 0x8410)
    if baseline_cond_us is not None:
        res_val_str = "{:.2f} uS".format(baseline_cond_us)
        fb.text(res_val_str, (width - len(res_val_str)*8)//2, 104, 0xFFFF)
    else:
        fb.text("Out of Range", (width - 12*8)//2, 104, 0xF800)
        
    fb.line(0, 175, width, 175, 0x4208)
    fb.text("STARTING LOG...", 11, 195, 0x07E0)
    
    swap_bytes(fb_buf, buf_size)
    set_window(0, 0, width - 1, height - 1)
    dc = pmic_lcd.dc
    cs = pmic_lcd.cs
    spi = pmic_lcd.spi
    dc.on()
    cs.off()
    spi.write(fb_buf)
    cs.on()
    
    now = rtc.datetime()
    timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        now[0], now[1], now[2], now[4], now[5], now[6]
    )
    res_log_str = "{:.3f} uS".format(baseline_cond_us) if baseline_cond_us is not None else "Out of Range"
    log_line = "[{}] [System] Baseline established. Raw: {:.1f} | Voltage: {:.1f} mV | Conductance: {}".format(
        timestamp, baseline_raw, baseline_uv / 1000.0, res_log_str
    )
    print(log_line)
    log_to_file(log_line)
    
    time.sleep(2.0)

def show_menu_and_wait():
    """Displays a start menu and waits for the user to press KEY1 to start calibration."""
    print("[System] Displaying start menu. Press KEY1 (M5 Button) to start calibration.")
    
    # Initial display state
    res_str = "---"
    connected = False
    
    def draw_menu():
        fb.fill(0x0000)
        
        # Header: "GSR MONITOR"
        fb.fill_rect(0, 0, width, 24, 0x18C3)
        fb.text("GSR MONITOR", 23, 8, 0xFDA0)
        fb.line(0, 24, width, 24, 0xC618)
        
        # Main outer rectangle for menu
        fb.rect(8, 36, width - 16, 128, 0x3186)
        
        # Instruction text
        fb.text("START MENU", (width - 10 * 8) // 2, 42, 0x07FF) # Cyan color for title
        fb.text("Press KEY1", (width - 10 * 8) // 2, 58, 0xFFFF)  # White color
        fb.text("to calibrate", (width - 12 * 8) // 2, 70, 0x8410)
        
        # GSR Value text
        fb.text("GSR VALUE", (width - 9 * 8) // 2, 92, 0x8410)
        if connected:
            res_w = len(res_str) * 8 * 2
            res_x = (width - res_w) // 2
            draw_large_text(fb, res_str, res_x, 108, 2, 0xFFE0)
            fb.text("CONNECTED", (width - 9 * 8) // 2, 132, 0x07E0)
        else:
            draw_large_text(fb, "---", (width - 3 * 8 * 2) // 2, 108, 2, 0xF800)
            fb.text("NO CONTACT", (width - 10 * 8) // 2, 132, 0xF800)
            
        # Footer: status line and waiting message
        fb.line(0, 175, width, 175, 0x4208)
        fb.text("WAITING...", 27, 195, 0xFDA0) # Orange
        fb.text("Btn A to Calib", 11, 215, 0x8410)
        
        # Flush frame buffer to LCD
        swap_bytes(fb_buf, buf_size)
        set_window(0, 0, width - 1, height - 1)
        dc = pmic_lcd.dc
        cs = pmic_lcd.cs
        spi = pmic_lcd.spi
        dc.on()
        cs.off()
        spi.write(fb_buf)
        cs.on()

    # Draw the initial screen immediately
    draw_menu()
    
    # Simple loop to wait for KEY1 press (low signal)
    # Debounce: wait for button to be released if it was already pressed
    while btn.value() == 0:
        time.sleep_ms(10)
        
    button_pressed = False
    while not button_pressed:
        raw_sum = 0
        uv_sum = 0
        count = 0
        
        start_time = time.ticks_ms()
        # Sample for 1 second (1000 ms)
        while time.ticks_diff(time.ticks_ms(), start_time) < 1000:
            raw_sum += adc.read()
            uv_sum += adc.read_uv()
            count += 1
            
            # Check button press
            if btn.value() == 0:
                time.sleep_ms(20) # debounce
                if btn.value() == 0:
                    button_pressed = True
                    # Wait for release
                    while btn.value() == 0:
                        time.sleep_ms(10)
                    break
            time.sleep_ms(10)
            
        if button_pressed:
            break
            
        # Calculate average of 1 second sample
        if count > 0:
            voltage_mv = (uv_sum / count) / 1000.0
            adc_10bit = int(voltage_mv * 1023 / 5000.0)
            denominator = 512 - adc_10bit
            if denominator > 0:
                resistance = ((1024 + 2 * adc_10bit) * 10000) / denominator
                resistance_k = resistance / 1000.0
                conductance_us = 1000.0 / resistance_k if resistance_k > 0 else 0.0
                res_str = "{:.2f}uS".format(conductance_us)
                connected = True
            else:
                res_str = "---"
                connected = False
        else:
            res_str = "---"
            connected = False
            
        # Redraw screen with new values
        draw_menu()

# Show start menu and wait for KEY1 to start
show_menu_and_wait()

# Initialize log file name when calibration starts
LOG_FILE = generate_log_filename()
print("Logging to file:", LOG_FILE)

run_calibration()

print("\n--- Start GSR Reading (Press Ctrl+C to stop) ---")
print("Timestamp | RawVal | Voltage(mV) | Skin_Conductance(uS) | Samples")
time.sleep(1.0)

accum_raw_sum = 0
accum_uv_sum = 0
accum_count = 0
loop_count = 0

while True:
    try:
        raw_sum = 0
        uv_sum = 0
        count = 0
        
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < 1000:
            raw_sum += adc.read()
            uv_sum += adc.read_uv()
            count += 1
            
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
                            write_cmd(0x28)
                            write_cmd(0x10)
                        except Exception as e:
                            print("[System] Failed display sleep cmd:", e)
                        disable_lcd_power()
                        print("[System] Display OFF complete.")
            
            time.sleep_ms(10)
            
        raw_avg_1s = raw_sum / count
        voltage_mv_1s = (uv_sum / count) / 1000.0
        
        adc_10bit_1s = int(voltage_mv_1s * 1023 / 5000.0)
        denominator_1s = 512 - adc_10bit_1s
        if denominator_1s > 0:
            resistance_1s = ((1024 + 2 * adc_10bit_1s) * 10000) / denominator_1s
            resistance_k_1s = resistance_1s / 1000.0
            conductance_us_1s = 1000.0 / resistance_k_1s if resistance_k_1s > 0 else 0.0
            res_str = "{:.2f}uS".format(conductance_us_1s)
            connected = True
        else:
            res_str = "---"
            connected = False
            
        accum_raw_sum += raw_sum
        accum_uv_sum += uv_sum
        accum_count += count
        loop_count += 1
        
        if loop_count >= 10:
            raw_avg_10s = accum_raw_sum / accum_count
            voltage_mv_10s = (accum_uv_sum / accum_count) / 1000.0
            
            adc_10bit_10s = int(voltage_mv_10s * 1023 / 5000.0)
            denominator_10s = 512 - adc_10bit_10s
            if denominator_10s > 0:
                resistance_10s = ((1024 + 2 * adc_10bit_10s) * 10000) / denominator_10s
                resistance_k_10s = resistance_10s / 1000.0
                conductance_us_10s = 1000.0 / resistance_k_10s if resistance_k_10s > 0 else 0.0
                log_res_str = "{:.3f} uS".format(conductance_us_10s)
                if baseline_cond_us is not None:
                    res_diff = conductance_us_10s - baseline_cond_us
                    log_res_str += " (diff: {:+.3f} uS)".format(res_diff)
            else:
                log_res_str = "Out of Range (No Contact)"
                
            raw_diff_10s = raw_avg_10s - baseline_raw
            
            now = rtc.datetime()
            timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                now[0], now[1], now[2], now[4], now[5], now[6]
            )
            
            log_line = "[{}] Raw: {:4.1f} (diff: {:+5.1f}) | Voltage: {:.2f} mV | Conductance: {} | Baseline Raw: {:.1f} | Samples: {}".format(
                timestamp, raw_avg_10s, raw_diff_10s, voltage_mv_10s, log_res_str, baseline_raw, accum_count
            )
            print("[Log] " + log_line)
            log_to_file(log_line)
            
            accum_raw_sum = 0
            accum_uv_sum = 0
            accum_count = 0
            loop_count = 0
            
        now = rtc.datetime()
        time_str = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], now[6])
        date_str = "{:04d}-{:02d}-{:02d}".format(now[0], now[1], now[2])
        
        if display_on:
            fb.fill(0x0000)
            fb.fill_rect(0, 0, width, 24, 0x9000)
            fb.text("GSR MONITOR", 23, 8, 0xFFFF)
            fb.line(0, 24, width, 24, 0xC618)
            
            fb.text("RAW VALUE", 31, 35, 0x8410)
            raw_val_str = "{:d}".format(int(raw_avg_1s))
            raw_len = len(raw_val_str)
            raw_scale = 4 if raw_len <= 4 else 3
            raw_w = raw_len * 8 * raw_scale
            raw_x = (width - raw_w) // 2
            raw_color = 0x07E0 if connected else 0xFD20
            draw_large_text(fb, raw_val_str, raw_x, 50, raw_scale, raw_color)
            
            if connected:
                fb.fill_rect(21, 90, 93, 14, 0x03E0)
                fb.text("CONNECTED", 31, 93, 0xFFFF)
            else:
                fb.fill_rect(17, 90, 101, 14, 0x7800)
                fb.text("NO CONTACT", 27, 93, 0xFFFF)
                
            fb.text("CONDUCTANCE", 27, 120, 0x8410)
            res_w = len(res_str) * 8 * 2
            res_x = (width - res_w) // 2
            draw_large_text(fb, res_str, res_x, 135, 2, 0xFFE0)
            
            diff = raw_avg_1s - baseline_raw
            diff_str = "{:+.1f}".format(diff)
            base_text = "B:{:.1f} d:{}".format(baseline_raw, diff_str)
            fb.text(base_text, (width - len(base_text)*8)//2, 160, 0xC618)
            
            fb.line(0, 175, width, 175, 0x4208)
            fb.text(date_str, 27, 185, 0x8410)
            draw_large_text(fb, time_str, 3, 200, 2, 0x07FF)
            
            swap_bytes(fb_buf, buf_size)
            set_window(0, 0, width - 1, height - 1)
            dc = pmic_lcd.dc
            cs = pmic_lcd.cs
            spi = pmic_lcd.spi
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
