import time
import network
import ntptime
from machine import RTC
import pmic_lcd

def show_boot_screen(status_text, progress=None, results=None):
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
    draw_large_text = pmic_lcd.draw_large_text
    
    # 背景クリア (Sleek Dark Mode)
    fb.fill(0x0000)
    
    # 中央にロゴ（GSR MONITOR）を洗練されたスタイルで描画
    # GSR: 倍率3 (3文字 * 24px = 72px) -> x = (135 - 72) // 2 = 31
    # MONITOR: 倍率1 (7文字 * 8px = 56px) -> x = (135 - 56) // 2 = 39
    draw_large_text(fb, "GSR", 31, 50, 3, 0xFDA0)  # M5オレンジ
    fb.text("MONITOR", 39, 82, 0xFFFF)             # 白
    
    if results is None:
        # 進行中の表示
        # ステータス文字列
        msg_w = len(status_text) * 8
        msg_x = (width - msg_w) // 2
        fb.text(status_text, msg_x, 130, 0x8410)    # 控えめなグレー
        
        # 細くシンプルなプログレスバー
        if progress is not None:
            bar_w = 90
            bar_x = (width - bar_w) // 2
            bar_y = 155
            bar_h = 3
            # バーの背景
            fb.fill_rect(bar_x, bar_y, bar_w, bar_h, 0x18E3)
            # バーの進行分
            current_w = int(bar_w * progress / 100)
            if current_w > 0:
                fb.fill_rect(bar_x, bar_y, current_w, bar_h, 0xFDA0)
    else:
        # 結果表示
        y = 125
        for label, val, color in results:
            # ラベル (e.g. "[ WIFI ]")
            lbl_str = "[ {} ]".format(label)
            fb.text(lbl_str, 15, y, 0x8410)
            # 値 (e.g. "OK", "FAIL", "SKIP")
            fb.text(val, 90, y, color)
            y += 22
            
        # 画面下部に READY を表示
        fb.text("READY", 47, 185, 0x07E0) # 緑
        
    swap_bytes(fb_buf, buf_size)
    set_window(0, 0, width - 1, height - 1)
    dc.on()
    cs.off()
    spi.write(fb_buf)
    cs.on()

def connect_wifi_and_sync_time(rtc):
    import json
    
    show_boot_screen("STARTING...", progress=10)
    time.sleep_ms(300)
    
    try:
        with open("wifi_config.json", "r") as f:
            config = json.load(f)
    except Exception as e:
        print("Failed to load wifi_config.json:", e)
        results = [
            ("CONFIG", "ERROR", 0xF800)
        ]
        show_boot_screen("ERROR", results=results)
        time.sleep(2.0)
        return
        
    ssid = config.get("ssid", "")
    password = config.get("password", "")
    timezone_offset_hours = config.get("timezone_offset_hours", 0)
    
    if ssid == "YOUR_WIFI_SSID" or not ssid:
        print("SSID is not configured. Skipping WiFi/NTP sync.")
        results = [
            ("WIFI", "SKIP", 0xFDA0),
            ("TIME", "SKIP", 0xFDA0)
        ]
        show_boot_screen("READY", results=results)
        time.sleep(2.0)
        return
        
    show_boot_screen("CONNECTING...", progress=30)
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
    connected = False
    for i in range(15):
        if wlan.isconnected():
            connected = True
            break
        time.sleep(1.0)
        show_boot_screen("CONNECTING...", progress=30 + int(i * 2.3))
        
    wifi_status = "OK" if connected else "FAIL"
    wifi_color = 0x07E0 if connected else 0xF800
    
    if not connected:
        print("WiFi connection failed.")
        results = [
            ("WIFI", "FAIL", wifi_color),
            ("TIME", "FAIL", 0xF800)
        ]
        show_boot_screen("FAILED", results=results)
        wlan.active(False)
        time.sleep(2.0)
        return
        
    ip = wlan.ifconfig()[0]
    print("WiFi connected! IP:", ip)
    show_boot_screen("SYNCING...", progress=75)
    
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
            show_boot_screen("SYNCING...", progress=75 + int(attempt * 8))
            
    time_status = "OK" if sync_success else "FAIL"
    time_color = 0x07E0 if sync_success else 0xF800
    
    if sync_success:
        try:
            utc_epoch = time.time()
            local_epoch = utc_epoch + int(timezone_offset_hours * 3600)
            tm = time.localtime(local_epoch)
            rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
            print("NTP Sync Success!")
        except Exception as e:
            print("Failed to set local time:", e)
            time_status = "ERROR"
            time_color = 0xF800
            
    print("Disconnecting WiFi to save power...")
    try:
        wlan.disconnect()
        wlan.active(False)
    except Exception as e:
        print("Failed to disable WLAN interface:", e)
        
    results = [
        ("WIFI", wifi_status, wifi_color),
        ("TIME", time_status, time_color)
    ]
    show_boot_screen("READY", results=results)
    time.sleep(2.0)
