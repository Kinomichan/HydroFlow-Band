import gc
gc.collect()
from machine import Pin, I2C, SPI
import time
import framebuf

# PMIC and LCD Configuration
PMIC_ADDR = 0x6E
REG_POWER = 0x06
BOOST_BIT = 0x08

# Initialize internal I2C bus (for PMIC control)
try:
    internal_i2c = I2C(0, sda=Pin(47), scl=Pin(48), freq=100000)
    print("Internal I2C initialized successfully.")
except Exception as e:
    print("Failed to initialize internal I2C:", e)

def enable_grove_5v():
    for attempt in range(3):
        try:
            current_val = internal_i2c.readfrom_mem(PMIC_ADDR, REG_POWER, 1)[0]
            new_val = current_val | BOOST_BIT
            internal_i2c.writeto_mem(PMIC_ADDR, REG_POWER, bytes([new_val]))
            print("PMIC 5V Boost output enabled. (Reg 0x06 -> 0x{:02X})".format(new_val))
            return True
        except Exception as e:
            print("PMIC connection attempt {} failed: {}".format(attempt + 1, e))
            time.sleep_ms(50)
    return False

def enable_lcd_power():
    try:
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x16, 1)[0]
        val &= ~(1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x16, bytes([val]))
        
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x10, 1)[0]
        val |= (1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x10, bytes([val]))
        
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x13, 1)[0]
        val &= ~(1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x13, bytes([val]))
        
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x11, 1)[0]
        val |= (1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x11, bytes([val]))
        
        internal_i2c.writeto_mem(PMIC_ADDR, 0x09, bytes([0x00]))
        print("PMIC LCD power rail enabled.")
        return True
    except Exception as e:
        print("Failed to enable PMIC LCD power:", e)
        return False

def disable_lcd_power():
    try:
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x11, 1)[0]
        val &= ~(1 << 2)
        internal_i2c.writeto_mem(PMIC_ADDR, 0x11, bytes([val]))
        print("PMIC LCD power rail disabled.")
        return True
    except Exception as e:
        print("Failed to disable PMIC LCD power:", e)
        return False

def setup_power_button():
    try:
        val = internal_i2c.readfrom_mem(PMIC_ADDR, 0x49, 1)[0]
        val |= 0x01
        internal_i2c.writeto_mem(PMIC_ADDR, 0x49, bytes([val]))
        
        val2 = internal_i2c.readfrom_mem(PMIC_ADDR, 0x4A, 1)[0]
        val2 |= 0x01
        internal_i2c.writeto_mem(PMIC_ADDR, 0x4A, bytes([val2]))
        
        print("PMIC Power Button configured as user input.")
        return True
    except Exception as e:
        print("Failed to configure PMIC Power Button:", e)
        return False

def is_power_button_pressed():
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

setup_power_button()
time.sleep_ms(100)

bl = Pin(38, Pin.OUT)
bl.on()

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
    rst.off()
    time.sleep_ms(50)
    rst.on()
    time.sleep_ms(150)
    write_cmd(0x01)
    time.sleep_ms(150)
    write_cmd(0x11)
    time.sleep_ms(120)
    write_cmd(0x3A)
    write_data(bytes([0x55]))
    write_cmd(0x36)
    write_data(bytes([0x08]))
    write_cmd(0x21)
    write_cmd(0x13)
    time.sleep_ms(10)
    write_cmd(0x29)
    time.sleep_ms(100)

init_lcd()

width = 135
height = 240
offset_x = 52
offset_y = 40

def set_window(x0, y0, x1, y1):
    x0 += offset_x
    x1 += offset_x
    y0 += offset_y
    y1 += offset_y
    write_cmd(0x2A)
    write_data(bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
    write_cmd(0x2B)
    write_data(bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
    write_cmd(0x2C)

@micropython.viper
def swap_bytes(buf_ptr: ptr8, size: int):
    for i in range(0, size, 2):
        t = buf_ptr[i]
        buf_ptr[i] = buf_ptr[i+1]
        buf_ptr[i+1] = t

def draw_large_text(fb_target, text, x, y, scale, color):
    tw = len(text) * 8
    th = 8
    temp_buf = bytearray(tw * th // 8)
    temp_fb = framebuf.FrameBuffer(temp_buf, tw, th, framebuf.MONO_VLSB)
    temp_fb.text(text, 0, 0, 1)
    for tx in range(tw):
        for ty in range(th):
            if temp_fb.pixel(tx, ty):
                fb_target.fill_rect(x + tx * scale, y + ty * scale, scale, scale, color)

buf_size = width * height * 2
gc.collect()
fb_buf = bytearray(buf_size)
fb = framebuf.FrameBuffer(fb_buf, width, height, framebuf.RGB565)

btn = Pin(11, Pin.IN, Pin.PULL_UP)
