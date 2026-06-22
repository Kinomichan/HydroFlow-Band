import time
import network
import ntptime
from machine import RTC
import pmic_lcd

def show_sync_status(title, lines, progress=None):
    fb = pmic_lcd.fb
    width = pmic_lcd.width
    height = pmic_lcd.height
    fb_buf = pmic_lcd.fb_buf
    buf_size = pmic_lcd.buf_size
    swap_bytes = pmic_lcd.swap_bytes
    set_window = pmic_lcd.set_window
    dc = pmic_lcd.dc
    cs = pmic_lcd.cs
    spi = pmic_lcd.spi
    
    fb.fill(0x0000)
    fb.line(6, 6, 16, 6, 0x07FF)
    fb.line(6, 6, 6, 16, 0x07FF)
    fb.line(width - 7, 6, width - 17, 6, 0x07FF)
    fb.line(width - 7, 6, width - 7, 16, 0x07FF)
    fb.line(6, height - 7, 16, height - 7, 0x07FF)
    fb.line(6, height - 7, 6, height - 17, 0x07FF)
    fb.line(width - 7, height - 7, width - 17, height - 7, 0x07FF)
    fb.line(width - 7, height - 7, width - 7, height - 17, 0x07FF)
    
    fb.fill_rect(8, 12, 4, 12, 0x07FF)
    fb.text(title, 16, 14, 0x07FF)
    fb.line(8, 28, width - 9, 28, 0x07FF)
    
    fb.rect(8, 36, width - 16, 128, 0x18C3)
    
    formatted_lines = []
    for line in lines:
        if line.startswith("IP: "):
            formatted_lines.append("IP:")
            formatted_lines.append(line[4:])
        elif line.startswith("SSID:"):
            formatted_lines.append("SSID:")
            formatted_lines.append(line[5:].strip())
        else:
            s = line
            while len(s) > 14:
                formatted_lines.append(s[:14])
                s = s[14:]
            if s:
                formatted_lines.append(s)
                
    y = 44
    for line in formatted_lines:
        if y > 150:
            break
        if "OK" in line or "Success" in line or "Connected" in line or "Success!" in line or "OFF" in line:
            color = 0x07E0
        elif "Failed" in line or "Failed!" in line or "Error" in line or "ERROR" in line or "FAIL" in line:
            color = 0xF800
        elif "Connecting" in line or "Syncing" in line or "Loading" in line:
            color = 0xFDA0
        else:
            color = 0xFFFF
            
        fb.text(line, 14, y, color)
        y += 14

    if progress is not None:
        prog_str = "{:d}%".format(progress)
        fb.text(prog_str, (width - len(prog_str) * 8) // 2, 175, 0x07FF)
        
        bar_x = 16
        bar_y = 190
        bar_w = width - 32
        bar_h = 8
        fb.rect(bar_x, bar_y, bar_w, bar_h, 0x3186)
        
        num_segments = 10
        seg_w = (bar_w - 4) // num_segments
        filled_segments = int(progress / 10)
        
        for i in range(num_segments):
            seg_x = bar_x + 2 + i * (seg_w + 1)
            if seg_x + seg_w > bar_x + bar_w - 2:
                break
            if i < filled_segments:
                fb.fill_rect(seg_x, bar_y + 2, seg_w - 1, bar_h - 4, 0x07FF)
            else:
                fb.fill_rect(seg_x, bar_y + 2, seg_w - 1, bar_h - 4, 0x0841)

    swap_bytes(fb_buf, buf_size)
    set_window(0, 0, width - 1, height - 1)
    dc.on()
    cs.off()
    spi.write(fb_buf)
    cs.on()

def connect_wifi_and_sync_time(rtc):
    import json
    
    show_sync_status("WIFI CONNECT", ["Loading config..."], progress=10)
    
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
        ], progress=0)
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
        ], progress=100)
        time.sleep(2.0)
        return
        
    show_sync_status("WIFI CONNECT", [
        "SSID:",
        "  " + ssid[:12] + ("..." if len(ssid) > 12 else ""),
        "Status:",
        "  Connecting..."
    ], progress=25)
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
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
        ], progress=30 + int(i * 2.5))
        
    if not connected:
        print("WiFi connection failed.")
        show_sync_status("WIFI FAIL", [
            "SSID:",
            "  " + ssid[:12] + ("..." if len(ssid) > 12 else ""),
            "Status:",
            "  Connection Failed!",
            "Proceeding..."
        ], progress=0)
        wlan.active(False)
        time.sleep(2.0)
        return
        
    ip = wlan.ifconfig()[0]
    print("WiFi connected! IP:", ip)
    show_sync_status("NTP SYNC", [
        "WiFi: Connected",
        "IP: " + ip,
        "NTP Syncing..."
    ], progress=70)
    
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
            ], progress=90)
        except Exception as e:
            print("Failed to set local time:", e)
            show_sync_status("SYNC ERROR", [
                "NTP Sync: OK",
                "Failed to set",
                "local timezone!"
            ], progress=80)
    else:
        print("NTP sync failed.")
        show_sync_status("SYNC FAIL", [
            "WiFi: Connected",
            "NTP Sync: Failed!",
            "Proceeding..."
        ], progress=75)
        
    time.sleep(1.5)
    
    print("Disconnecting WiFi to save power...")
    show_sync_status("WIFI CLOSE", [
        "Disconnecting WiFi",
        "to save power..."
    ], progress=95)
    try:
        wlan.disconnect()
        wlan.active(False)
    except Exception as e:
        print("Failed to disable WLAN interface:", e)
        
    show_sync_status("WIFI CLOSE", [
        "WiFi Interface OFF",
        "Power Saved.",
        "Starting GSR..."
    ], progress=100)
    time.sleep(1.0)
