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

def get_median_in_place(lst):
    if not lst:
        return 0.0
    lst.sort()
    n = len(lst)
    if n % 2 == 1:
        return float(lst[n // 2])
    else:
        return (lst[n // 2 - 1] + lst[n // 2]) / 2.0

# Global baseline variables determined by calibration
baseline_raw = 512.0
baseline_uv = 2500.0 * 1000.0
baseline_cond_us = 7.41  # Conductance in microSiemens (1000 / 135.0 kOhm)
sweat_score = 0.0

def draw_screen(connected, conductance_us, is_calibrating=False):
    """Draws the main logging display screen layout.
    
    If is_calibrating is True, it draws a calibration mark instead of the baseline diff,
    and a blinking indicator in the header.
    """
    # Retrieve current date/time from RTC
    now = rtc.datetime()
    time_str = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], now[6])
    date_str = "{:04d}-{:02d}-{:02d}".format(now[0], now[1], now[2])
    
    fb.fill(0x0000)
    
    # Header: GSR Monitor title (flashes red/dark red if sweat score is above 10000)
    if not is_calibrating and sweat_score > 10000:
        if (time.ticks_ms() // 500) % 2 == 0:
            fb.fill_rect(0, 0, width, 24, 0xF800)  # Bright Red
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 8, 0xFFFF)  # White text
        else:
            fb.fill_rect(0, 0, width, 24, 0x7800)  # Dark Red
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 8, 0xFFFF)  # White text
    else:
        fb.fill_rect(0, 0, width, 24, 0x18C3)  # Clean dark gray/blue
        fb.text("GSR MONITOR", 23, 8, 0xFDA0)  # Orange
    fb.line(0, 24, width, 24, 0xC618)
    
    # Blinking red/orange square indicator if calibrating
    if is_calibrating:
        if (time.ticks_ms() // 500) % 2 == 0:
            fb.fill_rect(118, 7, 10, 10, 0xF800)  # Red
        else:
            fb.fill_rect(118, 7, 10, 10, 0xFDA0)  # Orange
        fb.rect(117, 6, 12, 12, 0xFFFF)           # White border
        
    # Connection status bar (green when connected, red when no contact)
    if connected:
        fb.fill_rect(0, 25, width, 16, 0x03E0)
        fb.text("CONNECTED", (width - 9 * 8) // 2, 29, 0xFFFF)
    else:
        fb.fill_rect(0, 25, width, 16, 0x7800)
        fb.text("NO CONTACT", (width - 10 * 8) // 2, 29, 0xFFFF)
        
    # Skin conductance label
    fb.text("CONDUCTANCE", (width - 11 * 8) // 2, 53, 0x8410)
    
    # Large skin conductance numeric display (scale 3)
    val_str = "{:.2f}".format(conductance_us) if connected else "---"
    val_len = len(val_str)
    val_scale = 3
    val_w = val_len * 8 * val_scale
    val_x = (width - val_w) // 2
    draw_large_text(fb, val_str, val_x, 69, val_scale, 0xFFFF)
    
    # Unit text display
    fb.text("uS", (width - 2 * 8) // 2, 98, 0xFFE0)
    
    # Subtle divider
    fb.line(10, 114, width - 10, 114, 0x3186)
    
    # Baseline and Difference/Calibration displays
    if is_calibrating:
        base_txt = "Base: Calibrating"
        fb.text(base_txt, (width - len(base_txt) * 8) // 2, 124, 0xC618)
        
        # Blinking [CALIBRATING] message
        if (time.ticks_ms() // 500) % 2 == 0:
            diff_txt = "[CALIBRATING]"
            fb.text(diff_txt, (width - len(diff_txt) * 8) // 2, 142, 0xFDA0)
            
        score_txt = "Score: ---"
        fb.text(score_txt, (width - len(score_txt) * 8) // 2, 158, 0x8410)
    else:
        base_txt = "Base: {:.2f} uS".format(baseline_cond_us) if baseline_cond_us is not None else "Base: ---"
        fb.text(base_txt, (width - len(base_txt) * 8) // 2, 124, 0xC618)
        
        # Real-time conductance difference from baseline
        cond_diff_str = "---"
        cond_diff_color = 0x8410
        if connected and baseline_cond_us is not None:
            cond_diff = conductance_us - baseline_cond_us
            cond_diff_str = "{:+.2f} uS".format(cond_diff)
            if cond_diff > 0:
                cond_diff_color = 0xFD20  # Orange/Red for increase (stress)
            elif cond_diff < 0:
                cond_diff_color = 0x07E0  # Green for decrease (relaxation)
            else:
                cond_diff_color = 0xFFFF  # White for no change
                
        diff_txt = "Diff: {}".format(cond_diff_str)
        fb.text(diff_txt, (width - len(diff_txt) * 8) // 2, 142, cond_diff_color)
        
        # Display Sweat Score (flashes if it exceeds 10000)
        score_txt = "Score: {:.1f}".format(sweat_score)
        if sweat_score > 10000:
            score_color = 0xF800 if (time.ticks_ms() // 250) % 2 == 0 else 0xFFE0  # Flashing Red/Yellow
            fb.text(score_txt, (width - len(score_txt) * 8) // 2, 158, score_color)
        else:
            fb.text(score_txt, (width - len(score_txt) * 8) // 2, 158, 0x07FF)
        

    
    # Footer: date & time display
    fb.line(0, 175, width, 175, 0x4208)
    fb.text(date_str, 27, 185, 0x8410)
    draw_large_text(fb, time_str, 3, 200, 2, 0x07FF)
    
    # Overlay a thick flashing red border if alarm is active
    if not is_calibrating and sweat_score > 10000:
        if (time.ticks_ms() // 500) % 2 == 0:
            fb.rect(0, 0, width, height, 0xF800)
            fb.rect(1, 1, width - 2, height - 2, 0xF800)
            
    swap_bytes(fb_buf, buf_size)
    set_window(0, 0, width - 1, height - 1)
    dc = pmic_lcd.dc
    cs = pmic_lcd.cs
    spi = pmic_lcd.spi
    dc.on()
    cs.off()
    spi.write(fb_buf)
    cs.on()

def run_calibration():
    global baseline_raw, baseline_uv, baseline_cond_us
    
    print("\n--- Starting GSR Calibration (120s) ---")
    print("Please touch the electrodes and remain still.")
    
    duration_s = 120
    samples_per_update = 20
    total_updates = (duration_s * 1000) // (samples_per_update * 10)
    
    total_raw_sum = 0
    total_uv_sum = 0
    total_sample_count = 0
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
            
        update_raw_samples = []
        update_uv_samples = []
        for _ in range(samples_per_update):
            val = adc.read()
            uv = adc.read_uv()
            update_raw_samples.append(val)
            update_uv_samples.append(uv)
            time.sleep_ms(10)
            
        if len(update_raw_samples) > 0:
            median_raw = get_median_in_place(update_raw_samples)
            median_uv = get_median_in_place(update_uv_samples)
        else:
            median_raw = 512.0
            median_uv = 2500.0 * 1000.0
            
        total_raw_sum += median_raw
        total_uv_sum += median_uv
        total_sample_count += 1
        
        avg_raw = median_raw
        avg_uv = median_uv
        avg_mv = avg_uv / 1000.0
        
        adc_10bit = int(avg_mv * 1023 / 5000.0)
        denom = 512 - adc_10bit
        if denom > 0:
            res = ((1024 + 2 * adc_10bit) * 10000) / denom
            res_k = res / 1000.0
            cond_us = 1000.0 / res_k if res_k > 0 else 0.0
            connected = True
        else:
            connected = False
            cond_us = 0.0
            
        if display_on:
            draw_screen(connected, cond_us, is_calibrating=True)
            
    if not skipped and total_sample_count > 0:
        baseline_raw = total_raw_sum / total_sample_count
        baseline_uv = total_uv_sum / total_sample_count
        
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
        
    if display_on:
        draw_screen(True if baseline_cond_us is not None else False, baseline_cond_us if baseline_cond_us is not None else 7.41, is_calibrating=False)
        
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

def show_menu_and_wait():
    """Displays a start menu and waits for the user to press the M5 Button to start logging."""
    print("[System] Displaying start menu. Press M5 Button to start logging.")
    
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
        
        # Title of the box
        fb.text("START MENU", (width - 10 * 8) // 2, 48, 0x07FF) # Cyan color for title
        
        # GSR Value text
        fb.text("GSR VALUE", (width - 9 * 8) // 2, 76, 0x8410)
        if connected:
            res_w = len(res_str) * 8 * 2
            res_x = (width - res_w) // 2
            draw_large_text(fb, res_str, res_x, 96, 2, 0xFFE0)
            fb.text("CONNECTED", (width - 9 * 8) // 2, 128, 0x07E0)
        else:
            draw_large_text(fb, "---", (width - 3 * 8 * 2) // 2, 96, 2, 0xF800)
            fb.text("NO CONTACT", (width - 10 * 8) // 2, 128, 0xF800)
            
        # Footer: status line and instructions
        fb.line(0, 175, width, 175, 0x4208)
        fb.text("Press M5 Button", (width - 15 * 8) // 2, 190, 0xFDA0) # Orange
        fb.text("to Start Log", (width - 12 * 8) // 2, 208, 0x8410) # Gray
        
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

accum_raw_medians = []
accum_uv_medians = []
accum_sample_count = 0
loop_count = 0

while True:
    try:
        raw_samples = []
        uv_samples = []
        
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < 1000:
            raw_samples.append(adc.read())
            uv_samples.append(adc.read_uv())
            
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
            
        if len(raw_samples) > 0:
            raw_median_1s = get_median_in_place(raw_samples)
            voltage_mv_1s = get_median_in_place(uv_samples) / 1000.0
        else:
            raw_median_1s = 512.0
            voltage_mv_1s = 2500.0
            
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
            conductance_us_1s = 0.0
            
        if connected and baseline_cond_us is not None:
            diff_1s = conductance_us_1s - baseline_cond_us
            if diff_1s > 0:
                sweat_score += diff_1s * 1.0
            
        accum_raw_medians.append(raw_median_1s)
        accum_uv_medians.append(voltage_mv_1s * 1000.0)
        accum_sample_count += len(raw_samples)
        loop_count += 1
        
        if loop_count >= 10:
            raw_median_10s = get_median_in_place(accum_raw_medians)
            voltage_mv_10s = get_median_in_place(accum_uv_medians) / 1000.0
            
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
                
            raw_diff_10s = raw_median_10s - baseline_raw
            
            now = rtc.datetime()
            timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                now[0], now[1], now[2], now[4], now[5], now[6]
            )
            
            # Add alarm tag to the log message if the threshold is crossed
            alarm_tag = " [ALARM]" if sweat_score > 10000 else ""
            log_line = "[{}]{} Raw: {:4.1f} (diff: {:+5.1f}) | Voltage: {:.2f} mV | Conductance: {} | Sweat Score: {:.1f} | Baseline Raw: {:.1f} | Samples: {}".format(
                timestamp, alarm_tag, raw_median_10s, raw_diff_10s, voltage_mv_10s, log_res_str, sweat_score, baseline_raw, accum_sample_count
            )
            print("[Log] " + log_line)
            log_to_file(log_line)
            
            accum_raw_medians = []
            accum_uv_medians = []
            accum_sample_count = 0
            loop_count = 0
            
        if display_on:
            draw_screen(connected, conductance_us_1s, is_calibrating=False)
            
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
        break
    except Exception as e:
        print("Error during reading/display update:", e)
        time.sleep(1.0)
