import pmic_lcd
import time
from machine import Pin

# Unpack LCD and PMIC variables/functions from pmic_lcd
fb = pmic_lcd.fb
fb_buf = pmic_lcd.fb_buf
bl = pmic_lcd.bl
btn = pmic_lcd.btn
draw_large_text = pmic_lcd.draw_large_text
swap_bytes = pmic_lcd.swap_bytes
set_window = pmic_lcd.set_window
width = pmic_lcd.width
height = pmic_lcd.height
buf_size = pmic_lcd.buf_size
enable_lcd_power = pmic_lcd.enable_lcd_power
disable_lcd_power = pmic_lcd.disable_lcd_power
init_lcd = pmic_lcd.init_lcd

# Initialize control buttons
boot_btn = Pin(0, Pin.IN, Pin.PULL_UP)
key2_btn = Pin(12, Pin.IN, Pin.PULL_UP)

# Dummy conductance values for display testing
baseline_cond_us = 5.00
conductance_us = 6.20

# 15 minutes in seconds (900 seconds)
countdown_seconds = 15 * 60

def draw_screen(connected, conductance, countdown_sec):
    fb.fill(0x0000)
    
    # 1. Header: GSR Monitor title (flashes red/dark red if countdown reaches 0)
    if countdown_sec == 0:
        if (time.ticks_ms() // 500) % 2 == 0:
            fb.fill_rect(0, 0, width, 24, 0xF800)  # Bright Red
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 8, 0xFFFF)
        else:
            fb.fill_rect(0, 0, width, 24, 0x7800)  # Dark Red
            fb.text("!!! ALARM !!!", (width - 13 * 8) // 2, 8, 0xFFFF)
    else:
        fb.fill_rect(0, 0, width, 24, 0x18C3)  # Clean dark gray/blue
        fb.text("GSR MONITOR", 23, 8, 0xFDA0)  # Orange
    fb.line(0, 24, width, 24, 0xC618)
    
    # 2. Connection Status (Modern dot indicator style)
    fb.fill_rect(8, 28, width - 16, 18, 0x0841) # Dark gray background
    fb.rect(8, 28, width - 16, 18, 0x18C3)      # Border
    if connected:
        fb.fill_rect(25, 34, 6, 6, 0x07E0) # Green dot
        fb.text("CONNECTED", 37, 33, 0xFFFF)
    else:
        fb.fill_rect(21, 34, 6, 6, 0xF800) # Red dot
        fb.text("NO CONTACT", 33, 33, 0xF800)
        
    # 3. Skin Conductance Panel
    fb.text("CONDUCTANCE", (width - 11 * 8) // 2, 53, 0x5AEB) # Stylish blue-gray
    val_str = "{:.2f}".format(conductance) if connected else "---"
    val_w = len(val_str) * 8 * 3
    draw_large_text(fb, val_str, (width - val_w) // 2, 67, 3, 0xFFFF)
    fb.text("uS", (width - 2 * 8) // 2, 95, 0xFFE0)
    
    # Subtle divider
    fb.line(10, 112, width - 10, 112, 0x3186)
    
    # 4. Baseline and Difference displays (Re-spaced)
    base_txt = "Base: {:.2f} uS".format(baseline_cond_us)
    fb.text(base_txt, (width - len(base_txt) * 8) // 2, 126, 0x8410)
    
    cond_diff = conductance - baseline_cond_us
    cond_diff_str = "{:+.2f} uS".format(cond_diff)
    diff_txt = "Diff: {}".format(cond_diff_str)
    fb.text(diff_txt, (width - len(diff_txt) * 8) // 2, 146, 0xFD20 if cond_diff > 0 else 0x07E0)
        
    # 5. Footer: Countdown Timer Display
    footer_bg = 0x10A2 # Default dark gray-blue background
    
    if countdown_sec == 0:
        # Alarm flashing background
        if (time.ticks_ms() // 250) % 2 == 0:
            footer_bg = 0x7800 # Dark Red
        else:
            footer_bg = 0x0000 # Black
            
    fb.fill_rect(0, 175, width, 65, footer_bg)
    fb.line(0, 175, width, 175, 0x3186) # Divider line
    
    if countdown_sec is None:
        fb.text("TIMER", (width - 5 * 8) // 2, 182, 0x8410)
        draw_large_text(fb, "STANDBY", (width - 7 * 8 * 2) // 2, 198, 2, 0x5AEB)
    elif countdown_sec > 0:
        mins = countdown_sec // 60
        secs = countdown_sec % 60
        timer_str = "{:02d}:{:02d}".format(mins, secs)
        
        # Determine color based on remaining time
        if countdown_sec <= 60: # 1 minute or less
            timer_color = 0xF800 # Red
            fb.text("REHYDRATE NOW", (width - 13 * 8) // 2, 182, 0xF800)
        elif countdown_sec <= 180: # 3 minutes or less
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
    if countdown_sec == 0:
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

# Initialize display power
print("[Test] Enabling LCD power...")
enable_lcd_power()
time.sleep_ms(50)
init_lcd()
bl.on()

print("\n=== 15-Minute Countdown Test Program ===")
print("  - M5 Button (Front): Hold to FAST FORWARD (x30 speed)")
print("  - KEY Button (Side): Hold to PAUSE")
print("  - Ctrl+C to terminate test\n")

last_time = time.ticks_ms()

try:
    while True:
        current_time = time.ticks_ms()
        # Update display every 100ms for smooth animations/flashing
        draw_screen(True, conductance_us, countdown_seconds)
        
        # Check buttons
        key1_pressed = (btn.value() == 0)      # M5 Button (Front)
        key2_pressed = (key2_btn.value() == 0) # KEY Button (Side)
        
        # Decrement countdown
        if time.ticks_diff(current_time, last_time) >= 1000:
            last_time = current_time
            if countdown_seconds > 0:
                if key2_pressed:
                    # Paused
                    print("[Status] Paused at {:02d}:{:02d}".format(countdown_seconds // 60, countdown_seconds % 60))
                elif key1_pressed:
                    # Fast Forward: decreases 30 seconds per second
                    countdown_seconds = max(0, countdown_seconds - 30)
                    print("[Status] Fast Forwarding... {:02d}:{:02d}".format(countdown_seconds // 60, countdown_seconds % 60))
                else:
                    # Normal countdown
                    countdown_seconds -= 1
                    print("[Status] Countdown: {:02d}:{:02d}".format(countdown_seconds // 60, countdown_seconds % 60))
            else:
                print("[Status] ALARM TRIGGERED!")
                
        time.sleep_ms(100)

except KeyboardInterrupt:
    print("\n[Test] Terminated by user. Turning display OFF...")
    bl.off()
    try:
        pmic_lcd.write_cmd(0x28)
        pmic_lcd.write_cmd(0x10)
    except Exception:
        pass
    disable_lcd_power()
    print("[Test] Done.")
