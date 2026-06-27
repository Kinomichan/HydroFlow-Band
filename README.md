# M5StickS3 / Grove GSR Sensor Reader

This is a MicroPython project for connecting the M5StickS3 and Seeed Studio Grove GSR (Galvanic Skin Response) sensor, measuring skin resistance, visualizing it on the built-in display in real-time, and recording and managing logs.

---

## 1. Connection Specifications

Connect the GSR sensor to the Grove port (Port A) of the M5StickS3.

* **Analog Signal (SIG)**: Connected to **GPIO 10** (SCL / Yellow wire / ADC channel) of the M5StickS3.
* **Power (5V VCC)**: To power the Grove sensor, the 5V boost circuit (5V Boost) is enabled and power is supplied via the internal I2C (SDA: GPIO 47, SCL: GPIO 48) connection to the internal PMIC (PY32L020).
* **LCD Display**: Enables the LCD power rail through the control of the internal PMIC (GPIO 2) and draws the real-time UI on the 1.14-inch ST7789 LCD screen using hardware SPI (SCLK: 40, MOSI: 39, CS: 41, DC: 45, RST: 21). The backlight is controlled by PWM on GPIO 38.

---

## 2. File Structure

* **[main.py](file:///home/karube/GitHub/HydroFlow-Band/main.py)**: The main entry file executed automatically upon starting the M5StickS3. It loads each module, performs WiFi/NTP synchronization, startup calibration, and runs the measurement, UI drawing, and log recording loops. It is kept lightweight to improve memory efficiency.
* **[pmic_lcd.py](file:///home/karube/GitHub/HydroFlow-Band/pmic_lcd.py)**: A module responsible for initializing the M5StickS3's PMIC (power management), configuring the 1.14-inch LCD display (ST7789), and allocating memory for the drawing framebuffer (64,800 bytes).
* **[wifi_sync.py](file:///home/karube/GitHub/HydroFlow-Band/wifi_sync.py)**: A module responsible for the startup WiFi connection, RTC time synchronization using NTP (Network Time Protocol), and drawing the synchronization screen HUD.
* **[gsr_reader.py](file:///home/karube/GitHub/HydroFlow-Band/gsr_reader.py)**: Backup code containing the same contents as `main.py`.
* **[wifi_config.json](file:///home/karube/GitHub/HydroFlow-Band/wifi_config.json)**: A JSON configuration file to configure WiFi connection details (SSID, password) and timezone offset (`timezone_offset_hours`).
* **[sync.py](file:///home/karube/GitHub/HydroFlow-Band/sync.py)**: An automation script to write source files from the development PC to the M5StickS3 for synchronization. The newly separated `pmic_lcd.py` and `wifi_sync.py` are also automatically included in the sync targets.
* **[pull_logs.py](file:///home/karube/GitHub/HydroFlow-Band/pull_logs.py)**: A host script to retrieve log files (`*.log`, `*.log.bak`) from the M5StickS3's internal flash memory to the PC. It saves files with automatically appended timestamps.
* **[clear_logs.py](file:///home/karube/GitHub/HydroFlow-Band/clear_logs.py)**: A host script to delete all log files (`*.log`, `*.log.bak`) from the M5StickS3's internal flash memory to free up storage space.
* **[test_alarm.py](file:///home/karube/GitHub/HydroFlow-Band/test_alarm.py)**: A standalone test script to render and test the Alarm Rehydration Menu layout and button controls on the physical M5StickS3 screen.
* **[LICENSE](file:///home/karube/GitHub/HydroFlow-Band/LICENSE)**: The MIT License file containing the terms and conditions for using and distributing this project.

---

## 3. Environment Setup

This project communicates with the M5StickS3 using the `mpremote` library within a Python virtual environment (`.venv`).

```bash
# Create a virtual environment (if not already created)
python3 -m venv .venv

# Install dependent packages (mpremote, pyserial)
.venv/bin/python -m pip install mpremote
```

---

## 4. Usage of Synchronization Script (sync.py)

Writes the local source code to the M5StickS3 and automatically reboots it. Unnecessary files/directories such as `.git`, `.venv`, `pull_logs.py`, and `downloaded_logs/` are automatically excluded.

### Basic Writing (Add/Overwrite local files)
```bash
./sync.py
```
*(After the list of files to sync is displayed, a confirmation prompt `y/N` will be shown.)*

### Safe Cleanup Synchronization (Delete remote files that do not exist locally)
Deletes files on the M5StickS3 that have been deleted locally and synchronizes. Log files (`*.log`, `*.bak`) and the system file `boot.py` on the device are automatically protected from deletion.
```bash
./sync.py -c
```

### Complete Mirroring Synchronization (Full sync including logs)
Completely matches the device state with the local directory state. All files, including `.log` and `.bak` files that do not exist locally, are deleted from the device (only `boot.py` is protected).
```bash
./sync.py -m
```

### Options List
```bash
./sync.py [-h] [-p PORT] [-y] [-c] [-m]
```
* `-h, --help`: Show help.
* `-p, --port`: Specify the serial port (Default: `/dev/ttyACM0`).
* `-y, --yes`: Skip the confirmation prompt before execution.
* `-c, --clean`: Enable safe cleanup synchronization.
* `-m, --mirror-all`: Enable complete mirroring synchronization including log files.

---

## 5. Usage of Log Retrieval Script (pull_logs.py)

Safely copies the measurement log files (`*.log`, `*.log.bak`) accumulated in the M5StickS3's internal flash memory to the PC.

### Basic Retrieval (Save to PC, keep on device)
```bash
./pull_logs.py
```
Saves the device's logs under the `downloaded_logs/` directory with a unique filename containing a timestamp of the current date and time (e.g., `gsr_readings_YYYYMMDD_hhmmss.log`) to prevent overwriting.

### Retrieve and Clear (Free up storage space on the device)
```bash
./pull_logs.py -c
```
After downloading is complete, deletes the logs on the device to free up the microcontroller's flash capacity. You can skip the confirmation prompt by using the `-y` option together.

---

## 6. Usage of Log Deletion Script (clear_logs.py)

Deletes all log files (`*.log`, `*.log.bak`) stored in the M5StickS3's internal flash memory to free up space.

### Basic Deletion (Prompts for confirmation)
```bash
./clear_logs.py
```
*(Scans the device, lists all found logs, and prompts `y/N` before deleting them.)*

### Force Deletion (Skip confirmation prompt)
```bash
./clear_logs.py -y
```

### Options List
```bash
./clear_logs.py [-h] [-p PORT] [-y]
```
* `-h, --help`: Show help.
* `-p, --port`: Specify the serial port (Default: `/dev/ttyACM0`).
* `-y, --yes`: Skip confirmation prompt.

---

## 7. Startup WiFi Connection, NTP Time Sync, and Calibration

Upon M5StickS3 startup, it temporarily connects to a WiFi network to synchronize the built-in RTC using NTP (Network Time Protocol), and then performs calibration to determine the baseline value of the GSR sensor.

* **Operation Flow**:
  1. Reads connection settings from `wifi_config.json`.
  2. Connects to the configured WiFi SSID (displays connection status on the screen).
  3. Obtains the current Coordinated Universal Time (UTC) from the NTP server, and sets the RTC time taking into account the configured `timezone_offset_hours` (`9` for Japan Standard Time, `-7` for US Pacific Daylight Time, etc.).
  4. Immediately disconnects WiFi (`wlan.disconnect()`, `wlan.active(False)`) after time synchronization is complete to save power.
  5. **Start Menu Display (Standby Screen)**: Before starting calibration, it displays a start menu on the M5StickS3 screen. Even on this standby screen, it retrieves the galvanic skin conductance (uS: microsiemens) from the GSR sensor every second and displays it in real-time (connection status and measured value). Press the M5 Button to start logging.
  6. **GSR Calibration (Baseline Determination)**: Starts a 60-second calibration phase before entering the measurement loop. The screen immediately transitions to the real-time skin conductance reading display (normal logging layout) showing a blinking calibration mark. You can skip it at any time by pressing the M5 button (Btn A) or the power button.
  7. **Main Measurement Loop**: After calibration is complete, the baseline is finalized and appended to the log, transitioning to the main measurement and screen rendering loop.
* **Note**: If the WiFi SSID or password is not configured, or is left as `YOUR_WIFI_SSID`, the WiFi connection and NTP sync are automatically skipped, and the start menu display and calibration start immediately.

---

## 8. Screen Off and Power Saving Mode (Toggle Function)

This project allows you to turn off the screen and shift the microcontroller to a power-saving state by short-pressing the **BOOT** button (GPIO 0) or the **Power Button** (power button on the left side of the body).

* **Operation Specifications**:
  * **Toggle Operation**: Each press of either button toggles between "Power Saving Mode (Screen OFF)" and "Normal Mode (Screen ON)".
  * **Background Logging**: Even while the screen is off, the 1-second interval sampling of the GSR sensor and appending of logs to `gsr_readings.log` continue seamlessly in the background.
* **Power Saving Mechanisms**:
  * **LCD Backlight Off**: Turns off the backlight by setting GPIO 38 to LOW.
  * **LCD Controller Sleep**: Sends `Display Off (0x28)` and `Sleep In (0x10)` commands to the ST7789 LCD.
  * **Cutting LCD Power Rail**: Controls registers of the PMIC (PY32L020) via I2C to completely cut power supply to the LCD module itself.
  * **Reducing CPU Load**: While the screen is OFF, memory-intensive framebuffer processing and drawing transmission via the SPI bus are skipped to minimize the processing load on the ESP32-S3.
* **Power Button Customization**:
  * Normally on the M5StickS3, a short press of the power button resets the device, and a double-click causes shutdown. However, by rewriting the PMIC registers (`0x49` and `0x4A`) at startup, these hardware behaviors are disabled, allowing it to be reused as a user input button just like the M5 Button.
  * The physical emergency shutdown function via a long press (4 seconds or more) remains active for safety.

---

## 9. Measurement Enhancements (Median Filter & Sweat Detection/Countdown)

This project features two significant enhancements to improve data reliability and utility:

### Median Filtering for Noise Reduction
Due to hardware factors like power supply ripples from the 5V PMIC boost, WiFi transmission bursts, and dry electrode contact fluctuations, the analog readings are prone to spike noise. 
* To filter these spikes, a **Median Filter** (`get_median_in_place`) is applied.
* **Calibration**: Takes the median of each 20-sample update window (approx. 200 ms) to compute a robust baseline.
* **1-Second Real-Time Display**: Collects raw/voltage samples for 1 second (~100 samples), computes their median, and calculates the skin conductance displayed on the screen.
* **10-Second Log**: Collects the 1-second medians over 10 seconds and takes the median of those 10 values to write to the log. This double-layer filtering ensures extremely stable logged values.

### Sweat Detection and Countdown
To monitor sweat activity, a **Sweat Detection and Countdown** system is integrated.
* **Detection**: Sweating is detected if the current skin conductance reaches 1.5 times the established baseline conductance (`conductance_us_1s >= 1.5 * baseline_cond_us`).
* **Display (Premium Redesign)**: To maximize readability during workouts, the traditional real-time clock and date display have been replaced with a dedicated, large countdown timer in the footer.
  * **Standby State**: Displays `STANDBY` in a medium font size before sweating is detected.
  * **Countdown State**: Displays the remaining time (e.g. `15:00` or `30:00`) in a large font size (`scale=3`). The UI dynamically changes colors and labels based on remaining time:
    * *Normal (Time > 3 min)*: Cyan text with a `COUNTDOWN` label.
    * *Warning (3 min >= Time > 1 min)*: Orange text with a `HURRY UP` label.
    * *Critical (Time <= 1 min)*: Red text with a `REHYDRATE NOW` label.
  * **Alarm State (Time = 00:00)**: Triggers a prominent visual alert. In addition to a flashing red border and a flashing `"!!! ALARM !!!"` header, the entire footer background flashes red/black and the timer text flashes red/white.
* **Modernized UI elements**:
  * **Connection HUD**: The connection status bar is updated to a modern panel with a dark gray border and a dedicated LED-like status dot (green for connected, red for no contact).
  * **Spacing**: Redundant small timer labels were removed, and the vertical padding for the baseline and difference conductance values was optimized to prevent a cramped look.
* **Logging**: Appended to the 10-second interval log files as `Timer: MM:SS` (or `Timer: Off`). If the countdown has reached `00:00`, an `[ALARM]` tag is appended right after the timestamp (e.g., `[YYYY-MM-DD hh:mm:ss] [ALARM] Raw: ...`).
* **Testing the Countdown Display**:
  * You can test the 15-minute countdown and its visual transitions instantly on the device using the `test_countdown.py` script:
    ```bash
    # Synchronize the files to the device
    ./sync.py
    
    # Run the countdown test script using mpremote
    .venv/bin/python -m mpremote run test_countdown.py
    ```
  * During the test, you can hold the **M5 Button** (Front) to **fast-forward** (x30 speed) or hold the **KEY Button** (Side) to **pause** the countdown.

---

## 10. System Interrupt Menu (Re-calibration & Logging Control)

This project features a system interrupt menu that can be accessed during logging. This allows you to pause the logging sequence, continue, or reset and recalibrate the system.

* **Triggering the Menu**:
  * Press the **KEY Button** (GPIO 12) during logging to interrupt the operation and open the menu. If the display was turned off (power saving mode), it will be turned back on automatically.
* **Menu Options**:
  1. **Continue**: Resume the logging session seamlessly without losing any previous data or resetting the countdown.
  2. **Recalibrate**: Clear all accumulators, reset the countdown timer to `None` (`Off`), generate a new log file name, perform the 60-second calibration process again, and start a fresh logging session.
  3. **Reboot**: Perform a hardware reset (`machine.reset()`) to reboot the M5StickS3 device.
* **Menu Controls**:
  * **Select/Cycle Options**: Press the **KEY Button**.
  * **Confirm/Execute Selection**: Press the **M5 Button** (Front).

---

## 11. Alarm Rehydration Menu

When the countdown timer reaches `00:00` and the alarm triggers, the system automatically turns on the screen (if off) and presents the **Alarm Rehydration Menu**. This menu blocks further logging operations until the user confirms they have rehydrated.

* **Menu Options**:
  1. **Rehydrate & Continue**: Reset the countdown timer to **30 minutes** (`30:00`) and resume the current logging session. This initiates a periodic timer that will alert you to rehydrate and check whether to continue every 30 minutes thereafter.
  2. **Rehydrate & End Workout**: End the current logging session, close the log file, and return the system to the standby **START MENU** to prepare for a new session.
* **Menu Controls**:
  * **Select/Cycle Options**: Press the **KEY Button**.
  * **Confirm/Execute Selection**: Press the **M5 Button** (Front).
* **Testing the Alarm Screen**:
  * You can test this screen instantly on the device by syncing and running the `test_alarm.py` script:
    ```bash
    # Synchronize the files to the device
    ./sync.py
    
    # Run the test script using mpremote
    .venv/bin/python -m mpremote run test_alarm.py
    ```

---

## 12. Troubleshooting

### Error: `Failed to connect. The port is currently in use`
Another program, such as the Thonny IDE, may have left a connection open to `/dev/ttyACM0`.
* **Solution**: Disconnect the serial connection in Thonny or close the IDE itself, then try again.

### Error: `Could not enter raw REPL`
This occurs with the ESP32-S3's native USB CDC when the microcontroller is frozen or unable to correctly process serial input interrupts.
* **Solution**:
  1. Press the **red physical RESET button** on the side of the M5StickS3 once.
  2. Unplug and replug the USB cable once.
  3. Ensure that serial monitors like Thonny are completely closed.

---

## 13. License

This project is licensed under the MIT License. See the [LICENSE](file:///home/karube/GitHub/HydroFlow-Band/LICENSE) file for the full license text.
