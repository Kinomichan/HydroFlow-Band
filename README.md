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

* **[main.py](file:///home/karube/GitHub/M5StickS3/main.py)**: The main entry file executed automatically upon starting the M5StickS3. It loads each module, performs WiFi/NTP synchronization, startup calibration, and runs the measurement, UI drawing, and log recording loops. It is kept lightweight to improve memory efficiency.
* **[pmic_lcd.py](file:///home/karube/GitHub/M5StickS3/pmic_lcd.py)**: A module responsible for initializing the M5StickS3's PMIC (power management), configuring the 1.14-inch LCD display (ST7789), and allocating memory for the drawing framebuffer (64,800 bytes).
* **[wifi_sync.py](file:///home/karube/GitHub/M5StickS3/wifi_sync.py)**: A module responsible for the startup WiFi connection, RTC time synchronization using NTP (Network Time Protocol), and drawing the synchronization screen HUD.
* **[gsr_reader.py](file:///home/karube/GitHub/M5StickS3/gsr_reader.py)**: Backup code containing the same contents as `main.py`.
* **[wifi_config.json](file:///home/karube/GitHub/M5StickS3/wifi_config.json)**: A JSON configuration file to configure WiFi connection details (SSID, password) and timezone offset (`timezone_offset_hours`).
* **[sync.py](file:///home/karube/GitHub/M5StickS3/sync.py)**: An automation script to write source files from the development PC to the M5StickS3 for synchronization. The newly separated `pmic_lcd.py` and `wifi_sync.py` are also automatically included in the sync targets.
* **[pull_logs.py](file:///home/karube/GitHub/M5StickS3/pull_logs.py)**: A host script to retrieve log files (`*.log`, `*.log.bak`) from the M5StickS3's internal flash memory to the PC. It saves files with automatically appended timestamps, and can also clear (erase) the logs on the device to free up storage space.

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

## 6. Startup WiFi Connection, NTP Time Sync, and Calibration

Upon M5StickS3 startup, it temporarily connects to a WiFi network to synchronize the built-in RTC using NTP (Network Time Protocol), and then performs calibration to determine the baseline value of the GSR sensor.

* **Operation Flow**:
  1. Reads connection settings from `wifi_config.json`.
  2. Connects to the configured WiFi SSID (displays connection status on the screen).
  3. Obtains the current Coordinated Universal Time (UTC) from the NTP server, and sets the RTC time taking into account the configured `timezone_offset_hours` (`9` for Japan Standard Time, `-7` for US Pacific Daylight Time, etc.).
  4. Immediately disconnects WiFi (`wlan.disconnect()`, `wlan.active(False)`) after time synchronization is complete to save power.
  5. **Start Menu Display (Standby Screen)**: Before starting calibration, it displays a start menu on the M5StickS3 screen. Even on this standby screen, it retrieves the galvanic skin conductance (uS: microsiemens) from the GSR sensor every second and displays it in real-time (connection status and measured value). Press the M5 Button to start calibration.
  6. **GSR Calibration (Baseline Determination)**: Starts a 120-second calibration phase before entering the measurement loop. The screen immediately transitions to the real-time skin conductance reading display (normal logging layout) showing a blinking calibration mark. You can skip it at any time by pressing the M5 button (Btn A) or the power button.
  7. **Main Measurement Loop**: After calibration is complete, the baseline is finalized and appended to the log, transitioning to the main measurement and screen rendering loop.
* **Note**: If the WiFi SSID or password is not configured, or is left as `YOUR_WIFI_SSID`, the WiFi connection and NTP sync are automatically skipped, and the start menu display and calibration start immediately.

---

## 7. Screen Off and Power Saving Mode (Toggle Function)

This project allows you to turn off the screen and shift the microcontroller to a power-saving state by short-pressing KEY1 (M5 button on the front of the body) or the Power Button (power button on the left side of the body).

* **Operation Specifications**:
  * **Toggle Operation**: Each press of either button toggles between "Power Saving Mode (Screen OFF)" and "Normal Mode (Screen ON)".
  * **Background Logging**: Even while the screen is off, the 1-second interval sampling of the GSR sensor and appending of logs to `gsr_readings.log` continue seamlessly in the background.
* **Power Saving Mechanisms**:
  * **LCD Backlight Off**: Turns off the backlight by setting GPIO 38 to LOW.
  * **LCD Controller Sleep**: Sends `Display Off (0x28)` and `Sleep In (0x10)` commands to the ST7789 LCD.
  * **Cutting LCD Power Rail**: Controls registers of the PMIC (PY32L020) via I2C to completely cut power supply to the LCD module itself.
  * **Reducing CPU Load**: While the screen is OFF, memory-intensive framebuffer processing and drawing transmission via the SPI bus are skipped to minimize the processing load on the ESP32-S3.
* **Power Button Customization**:
  * Normally on the M5StickS3, a short press of the power button resets the device, and a double-click causes shutdown. However, by rewriting the PMIC registers (`0x49` and `0x4A`) at startup, these hardware behaviors are disabled, allowing it to be reused as a user input button just like KEY1.
  * The physical emergency shutdown function via a long press (4 seconds or more) remains active for safety.

---

## 8. Troubleshooting

### Error: `Failed to connect. The port is currently in use`
Another program, such as the Thonny IDE, may have left a connection open to `/dev/ttyACM0`.
* **Solution**: Disconnect the serial connection in Thonny or close the IDE itself, then try again.

### Error: `Could not enter raw REPL`
This occurs with the ESP32-S3's native USB CDC when the microcontroller is frozen or unable to correctly process serial input interrupts.
* **Solution**:
  1. Press the **red physical RESET button** on the side of the M5StickS3 once.
  2. Unplug and replug the USB cable once.
  3. Ensure that serial monitors like Thonny are completely closed.
