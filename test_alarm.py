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
        fb.text("KEY2: Select", (width - 12 * 8) // 2, 190, 0xFDA0) # Orange
        fb.text("KEY1: Confirm", (width - 13 * 8) // 2, 208, 0x8410) # Gray
        
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

# Initialize display power
print("[Test] Enabling LCD power...")
enable_lcd_power()
time.sleep_ms(50)
init_lcd()
bl.on()

print("[Test] Starting alarm menu test. Press KEY2 to cycle, KEY1 to select.")
choice = show_alarm_menu()

if choice == 0:
    print("[Test] Result: Selected 'Rehydrate & Continue' (Option 0)")
elif choice == 1:
    print("[Test] Result: Selected 'Rehydrate & End Workout' (Option 1)")

# Turn off display to indicate finished
print("[Test] Testing finished. Turning display OFF in 2 seconds...")
time.sleep(2.0)
bl.off()
try:
    pmic_lcd.write_cmd(0x28)
    pmic_lcd.write_cmd(0x10)
except Exception:
    pass
disable_lcd_power()
print("[Test] Done.")
