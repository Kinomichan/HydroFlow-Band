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

# Initialize control buttons
boot_btn = Pin(0, Pin.IN, Pin.PULL_UP)
key2_btn = Pin(12, Pin.IN, Pin.PULL_UP)

# Initialize RTC
rtc = RTC()

# Connect to WiFi and synchronize time
wifi_sync.connect_wifi_and_sync_time(rtc)

display_on = True
last_btn_press = 0

def check_and_handle_display_toggle():
    global display_on, last_btn_press
    btn_pressed = False
    if boot_btn.value() == 0:
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
            return True
    return False

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
countdown_seconds = None

def draw_screen(connected, conductance_us, is_calibrating=False):
    """Draws the main logging display screen layout.
    
    If is_calibrating is True, it draws a calibration mark instead of the baseline diff,
    and a blinking indicator in the header.
    """
    fb.fill(0x0000)
    
    global countdown_seconds
    
    # 1. Header: GSR Monitor title (flashes red/dark red if countdown reaches 0)
    if not is_calibrating and countdown_seconds == 0:
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
        
    # 2. Connection Status (Modern dot indicator style)
    # Background for connection status panel to make it look premium
    fb.fill_rect(8, 28, width - 16, 18, 0x0841) # Dark gray background
    fb.rect(8, 28, width - 16, 18, 0x18C3)      # Border
    if connected:
        # "CONNECTED" (9 chars) -> 72px width. Dot 6px + Gap 6px + Text 72px = 84px.
        # Start X = (135 - 84) // 2 = 25px
        fb.fill_rect(25, 34, 6, 6, 0x07E0) # Green dot
        fb.text("CONNECTED", 37, 33, 0xFFFF)
    else:
        # "NO CONTACT" (10 chars) -> 80px width. Dot 6px + Gap 6px + Text 80px = 92px.
        # Start X = (135 - 92) // 2 = 21px
        fb.fill_rect(21, 34, 6, 6, 0xF800) # Red dot
        fb.text("NO CONTACT", 33, 33, 0xF800)
        
    # 3. Skin Conductance Panel
    fb.text("CONDUCTANCE", (width - 11 * 8) // 2, 53, 0x5AEB) # Stylish blue-gray
    
    # Large skin conductance numeric display (scale 3)
    val_str = "{:.2f}".format(conductance_us) if connected else "---"
    val_len = len(val_str)
    val_scale = 3
    val_w = val_len * 8 * val_scale
    val_x = (width - val_w) // 2
    draw_large_text(fb, val_str, val_x, 67, val_scale, 0xFFFF)
    
    # Unit text display
    fb.text("uS", (width - 2 * 8) // 2, 95, 0xFFE0)
    
    # Subtle divider
    fb.line(10, 112, width - 10, 112, 0x3186)
    
    # 4. Baseline and Difference/Calibration displays (Re-spaced)
    if is_calibrating:
        base_txt = "Base: Calibrating"
        fb.text(base_txt, (width - len(base_txt) * 8) // 2, 126, 0xC618)
        
        # Blinking [CALIBRATING] message
        if (time.ticks_ms() // 500) % 2 == 0:
            diff_txt = "[CALIBRATING]"
            fb.text(diff_txt, (width - len(diff_txt) * 8) // 2, 146, 0xFDA0)
    else:
        base_txt = "Base: {:.2f} uS".format(baseline_cond_us) if baseline_cond_us is not None else "Base: ---"
        fb.text(base_txt, (width - len(base_txt) * 8) // 2, 126, 0x8410) # Gray
        
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
        fb.text(diff_txt, (width - len(diff_txt) * 8) // 2, 146, cond_diff_color)
        
    # 5. Footer: Countdown Timer Display (Replacing Date/Time)
    # Background for footer section
    footer_bg = 0x10A2 # Default dark gray-blue background
    
    if not is_calibrating and countdown_seconds == 0:
        # Alarm flashing background
        if (time.ticks_ms() // 250) % 2 == 0:
            footer_bg = 0x7800 # Dark Red
        else:
            footer_bg = 0x0000 # Black
            
    fb.fill_rect(0, 175, width, 65, footer_bg)
    fb.line(0, 175, width, 175, 0x3186) # Divider line
    
    if is_calibrating:
        fb.text("TIMER", (width - 5 * 8) // 2, 182, 0x8410)
        # Display "---" during calibration
        draw_large_text(fb, "---", (width - 3 * 8 * 3) // 2, 198, 3, 0x8410)
    else:
        if countdown_seconds is None:
            fb.text("TIMER", (width - 5 * 8) // 2, 182, 0x8410)
            # Display "STANDBY" (7 chars) in scale 2
            draw_large_text(fb, "STANDBY", (width - 7 * 8 * 2) // 2, 198, 2, 0x5AEB)
        elif countdown_seconds > 0:
            mins = countdown_seconds // 60
            secs = countdown_seconds % 60
            timer_str = "{:02d}:{:02d}".format(mins, secs)
            
            # Determine color based on remaining time
            if countdown_seconds <= 60: # 1 minute or less
                timer_color = 0xF800 # Red
                fb.text("REHYDRATE NOW", (width - 13 * 8) // 2, 182, 0xF800)
            elif countdown_seconds <= 180: # 3 minutes or less
                timer_color = 0xFDA0 # Orange
                fb.text("HURRY UP", (width - 8 * 8) // 2, 182, 0xFDA0)
            else:
                timer_color = 0x07FF # Cyan
                fb.text("COUNTDOWN", (width - 9 * 8) // 2, 182, 0x5AEB)
                
            draw_large_text(fb, timer_str, (width - 5 * 8 * 3) // 2, 198, 3, timer_color)
        else:
            # Alarm state (00:00)
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 182, 0xFFFF)
            timer_color = 0xF800 if (time.ticks_ms() // 250) % 2 == 0 else 0xFFFF
            draw_large_text(fb, "00:00", (width - 5 * 8 * 3) // 2, 198, 3, timer_color)
            
    # Overlay a thick flashing red border if alarm is active
    if not is_calibrating and countdown_seconds == 0:
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
    
    print("\n--- Starting GSR Calibration (60s) ---")
    print("Please touch the electrodes and remain still.")
    
    duration_s = 60
    samples_per_update = 20
    total_updates = (duration_s * 1000) // (samples_per_update * 10)
    
    total_raw_sum = 0
    total_uv_sum = 0
    total_sample_count = 0
    skipped = False
    
    for update in range(total_updates):
        check_and_handle_display_toggle()
        
        btn_pressed = False
        if btn.value() == 0 or key2_btn.value() == 0:
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

def show_interrupt_menu():
    """Displays the interrupt menu when KEY Button is pressed.
    
    Allows the user to choose between:
    - Continue Logging (Option 0)
    - Calibrate & Restart (Option 1)
    - Reboot Device (Option 2)
    
    KEY button: Cycles selection
    M5 button: Confirms selection
    """
    print("[System] Displaying interrupt menu.")
    
    selected_option = 0  # 0: Continue Logging, 1: Calibrate & Restart, 2: Reboot Device
    
    # Wait until buttons are released first to prevent accidental instant select
    while key2_btn.value() == 0 or btn.value() == 0:
        time.sleep_ms(10)
        
    last_action_time = time.ticks_ms()
    
    def draw_menu_options():
        fb.fill(0x0000)
        
        # Header: "SYSTEM MENU"
        fb.fill_rect(0, 0, width, 24, 0x18C3) # Dark blue/gray header
        fb.text("SYSTEM MENU", 23, 8, 0xFDA0) # Orange text
        fb.line(0, 24, width, 24, 0xC618)
        
        # Outer box
        fb.rect(6, 36, width - 12, 128, 0x3186)
        
        # Option 1: Continue Logging
        opt1_color = 0xFFFF if selected_option == 0 else 0x8410
        opt1_bg = 0x18C3 if selected_option == 0 else 0x0000
        fb.fill_rect(10, 44, width - 20, 28, opt1_bg)
        fb.rect(10, 44, width - 20, 28, opt1_color)
        fb.text("Continue Log", 20, 54, opt1_color)
        
        # Option 2: Recalibrate & Restart
        opt2_color = 0xFFFF if selected_option == 1 else 0x8410
        opt2_bg = 0x18C3 if selected_option == 1 else 0x0000
        fb.fill_rect(10, 80, width - 20, 36, opt2_bg)
        fb.rect(10, 80, width - 20, 36, opt2_color)
        fb.text("Recalibrate", 20, 85, opt2_color)
        fb.text("& Restart", 20, 98, opt2_color)
        
        # Option 3: Reboot Device
        opt3_color = 0xFFFF if selected_option == 2 else 0x8410
        opt3_bg = 0x18C3 if selected_option == 2 else 0x0000
        fb.fill_rect(10, 124, width - 20, 28, opt3_bg)
        fb.rect(10, 124, width - 20, 28, opt3_color)
        fb.text("Reboot Device", 20, 134, opt3_color)
        
        # Footer instruction
        fb.line(0, 175, width, 175, 0x4208)
        fb.text("KEY: Select", (width - 11 * 8) // 2, 190, 0xFDA0) # Orange
        fb.text("M5: Confirm", (width - 11 * 8) // 2, 208, 0x8410) # Gray
        
        # Flush to screen
        swap_bytes(fb_buf, buf_size)
        set_window(0, 0, width - 1, height - 1)
        dc = pmic_lcd.dc
        cs = pmic_lcd.cs
        spi = pmic_lcd.spi
        dc.on()
        cs.off()
        spi.write(fb_buf)
        cs.on()

    draw_menu_options()
    
    while True:
        now = time.ticks_ms()
        # Read buttons
        key2_pressed = (key2_btn.value() == 0)
        key1_pressed = (btn.value() == 0)
        
        if key2_pressed and time.ticks_diff(now, last_action_time) > 300:
            last_action_time = now
            selected_option = (selected_option + 1) % 3  # Cycle between 0, 1, 2
            draw_menu_options()
            # Wait for button release
            while key2_btn.value() == 0:
                time.sleep_ms(10)
                
        elif key1_pressed and time.ticks_diff(now, last_action_time) > 300:
            last_action_time = now
            # Wait for release
            while btn.value() == 0:
                time.sleep_ms(10)
            return selected_option
            
        time.sleep_ms(20)

def show_alarm_menu():
    """Displays the alarm/rehydration menu when the countdown reaches 0.
    
    Allows the user to choose between:
    - Rehydrate & Continue (Option 0)
    - Rehydrate & End Workout (Option 1)
    
    KEY 2 button: Cycles selection
    KEY 1 button: Confirms selection
    """
    print("[System] Displaying alarm rehydration menu.")
    
    selected_option = 0  # 0: Rehydrate & Continue, 1: Rehydrate & End Workout
    
    # Wait until buttons are released first to prevent accidental instant select
    while key2_btn.value() == 0 or btn.value() == 0:
        time.sleep_ms(10)
        
    last_action_time = time.ticks_ms()
    
    def draw_alarm_menu_options():
        fb.fill(0x0000)
        
        # Header: Flashing Alarm Title
        if (time.ticks_ms() // 500) % 2 == 0:
            fb.fill_rect(0, 0, width, 24, 0xF800)  # Bright Red
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 8, 0xFFFF)
        else:
            fb.fill_rect(0, 0, width, 24, 0x7800)  # Dark Red
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 8, 0xFFFF)
        fb.line(0, 24, width, 24, 0xC618)
        
        # Outer box
        fb.rect(6, 36, width - 12, 128, 0xF800) # Red box
        
        # Instruction text
        fb.text("Please rehydrate", 16, 44, 0xFFFF)
        
        # Option 1: Rehydrate & Continue
        opt1_color = 0xFFFF if selected_option == 0 else 0x8410
        opt1_bg = 0x18C3 if selected_option == 0 else 0x0000
        fb.fill_rect(10, 68, width - 20, 38, opt1_bg)
        fb.rect(10, 68, width - 20, 38, opt1_color)
        fb.text("Rehydrate &", 20, 74, opt1_color)
        fb.text("Continue", 20, 88, opt1_color)
        
        # Option 2: Rehydrate & End
        opt2_color = 0xFFFF if selected_option == 1 else 0x8410
        opt2_bg = 0x18C3 if selected_option == 1 else 0x0000
        fb.fill_rect(10, 114, width - 20, 38, opt2_bg)
        fb.rect(10, 114, width - 20, 38, opt2_color)
        fb.text("Rehydrate &", 20, 120, opt2_color)
        fb.text("End Workout", 20, 134, opt2_color)
        
        # Footer instruction
        fb.line(0, 175, width, 175, 0x4208)
        fb.text("KEY: Select", (width - 11 * 8) // 2, 190, 0xFDA0) # Orange
        fb.text("M5: Confirm", (width - 11 * 8) // 2, 208, 0x8410) # Gray
        
        # Flush to screen
        swap_bytes(fb_buf, buf_size)
        set_window(0, 0, width - 1, height - 1)
        dc = pmic_lcd.dc
        cs = pmic_lcd.cs
        spi = pmic_lcd.spi
        dc.on()
        cs.off()
        spi.write(fb_buf)
        cs.on()

    draw_alarm_menu_options()
    
    while True:
        now = time.ticks_ms()
        # Read buttons
        key2_pressed = (key2_btn.value() == 0)
        key1_pressed = (btn.value() == 0)
        
        # Periodically redraw to keep the flashing header alive
        if (now // 500) % 2 != ((now - 20) // 500) % 2:
            draw_alarm_menu_options()
        
        if key2_pressed and time.ticks_diff(now, last_action_time) > 300:
            last_action_time = now
            selected_option = 1 - selected_option  # Toggle between 0 and 1
            draw_alarm_menu_options()
            # Wait for button release
            while key2_btn.value() == 0:
                time.sleep_ms(10)
                
        elif key1_pressed and time.ticks_diff(now, last_action_time) > 300:
            last_action_time = now
            # Wait for release
            while btn.value() == 0:
                time.sleep_ms(10)
            return selected_option
            
        time.sleep_ms(20)

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
    
    # Simple loop to wait for M5 Button press (low signal)
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
            
            # Check display toggle
            check_and_handle_display_toggle()
            
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

# Main execution loop supporting multiple workouts/sessions
while True:
    # Show start menu and wait for M5 Button to start
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
    countdown_seconds = None

    session_active = True
    while session_active:
        try:
            raw_samples = []
            uv_samples = []
            
            start_time = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start_time) < 1000:
                raw_samples.append(adc.read())
                uv_samples.append(adc.read_uv())
                
                # Check display toggle
                check_and_handle_display_toggle()
                # Check for KEY2 button press to open menu
                if key2_btn.value() == 0:
                    time.sleep_ms(50)  # Debounce
                    if key2_btn.value() == 0:
                        if not display_on:
                            print("[System] Turning display ON for menu...")
                            enable_lcd_power()
                            time.sleep_ms(50)
                            init_lcd()
                            bl.on()
                            display_on = True
                        
                        choice = show_interrupt_menu()
                        
                        if choice == 0:
                            # Continue logging
                            print("[System] Resuming logging...")
                            raw_samples = []
                            uv_samples = []
                            start_time = time.ticks_ms()
                        elif choice == 1:
                            # Recalibrate and restart logging from scratch
                            print("[System] Recalibrating and restarting logging...")
                            countdown_seconds = None
                            LOG_FILE = generate_log_filename()
                            print("New log file:", LOG_FILE)
                            run_calibration()
                            accum_raw_medians = []
                            accum_uv_medians = []
                            accum_sample_count = 0
                            loop_count = 0
                            raw_samples = []
                            uv_samples = []
                            start_time = time.ticks_ms()
                        elif choice == 2:
                            # Reboot device
                            print("[System] Rebooting device...")
                            import machine
                            machine.reset()
                
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
                # Sweating is detected when conductance reaches 1.5 times the baseline
                if conductance_us_1s >= 1.5 * baseline_cond_us:
                    if countdown_seconds is None:
                        countdown_seconds = 15 * 60
                        print("[System] Sweating detected (conductance {:.2f} uS >= 1.5 * baseline {:.2f} uS). Starting 15-minute countdown.".format(conductance_us_1s, baseline_cond_us))

            if countdown_seconds is not None:
                if countdown_seconds > 0:
                    countdown_seconds -= 1
                    if countdown_seconds == 0:
                        print("[System] Countdown reached 0. Alarm triggered!")
            
            # Check if alarm has triggered and handle rehydration menu
            if countdown_seconds == 0:
                if not display_on:
                    print("[System] Turning display ON for alarm menu...")
                    enable_lcd_power()
                    time.sleep_ms(50)
                    init_lcd()
                    bl.on()
                    display_on = True
                
                alarm_choice = show_alarm_menu()
                if alarm_choice == 0:
                    print("[System] Rehydrated. Continuing workout with a 30-minute periodic timer...")
                    countdown_seconds = 30 * 60  # Set to 30 minutes (1800 seconds)
                    # Reset raw/uv samples & start_time
                    raw_samples = []
                    uv_samples = []
                    start_time = time.ticks_ms()
                    continue
                elif alarm_choice == 1:
                    print("[System] Rehydrated. Ending workout...")
                    session_active = False
                    continue
                
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
                
                # Add alarm tag to the log message if the countdown has reached 0
                alarm_tag = " [ALARM]" if countdown_seconds == 0 else ""
                timer_log_str = "Off" if countdown_seconds is None else "{:02d}:{:02d}".format(countdown_seconds // 60, countdown_seconds % 60)
                log_line = "[{}]{} Raw: {:4.1f} (diff: {:+5.1f}) | Voltage: {:.2f} mV | Conductance: {} | Timer: {} | Baseline Raw: {:.1f} | Samples: {}".format(
                    timestamp, alarm_tag, raw_median_10s, raw_diff_10s, voltage_mv_10s, log_res_str, timer_log_str, baseline_raw, accum_sample_count
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
            session_active = False
            raise KeyboardInterrupt
        except Exception as e:
            print("Error during reading/display update:", e)
            time.sleep(1.0)
