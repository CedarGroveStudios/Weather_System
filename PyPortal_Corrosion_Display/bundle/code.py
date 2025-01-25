# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
""" pyportal_corrosion_display.py

Receives AIO corrosion conditions in support of remote workshop corrosion
monitoring.

For the Adafruit PyPortal M4
"""

import time
import board
import os
import gc
import displayio
import digitalio
import analogio
import supervisor
from simpleio import map_range
import adafruit_pyportal
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect
from adafruit_display_shapes.roundrect import RoundRect
from adafruit_display_shapes.triangle import Triangle
import adafruit_adt7410  # Integral I2C temperature sensor
from cedargrove_temperaturetools.unit_converters import celsius_to_fahrenheit

# Set display brightness for startup
board.DISPLAY.brightness = 0

# AIO Weather Receiver Parameters
SAMPLE_INTERVAL = 120  # Check corrosion conditions (seconds)
QUALITY_THRESHOLD = 8  # Quality warning when less than threshold (out of 10)
BRIGHTNESS = 0.75

# fmt: off
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# fmt: on

# Start-up values
message = ""
corrosion_index = 0
clock_tick = False

# Instantiate the PyPortal
pyportal = adafruit_pyportal.PyPortal(
    status_neopixel=board.NEOPIXEL, default_bg="/corrosion_mon_startup.bmp"
)
# pyportal = adafruit_pyportal.PyPortal(status_neopixel=board.NEOPIXEL)
pyportal.set_backlight(BRIGHTNESS)

# Instantiate the Red LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

# Instantiate the light sensor
light_sensor = analogio.AnalogIn(board.LIGHT)

# Instantiate the PCB temperature sensor
corrosion_sensor = adafruit_adt7410.ADT7410(board.I2C())
corrosion_sensor.reset = True  # Set the sensor to a known state
corrosion_sensor.high_resolution = True

# Load the text fonts from the fonts folder
FONT_1 = bitmap_font.load_font("/fonts/OpenSans-9.bdf")
FONT_2 = bitmap_font.load_font("/fonts/Arial-12.bdf")
FONT_3 = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
CLOCK_FONT = bitmap_font.load_font("/fonts/Anton-Regular-104.bdf")

# The board's integral display size
WIDTH = board.DISPLAY.width  # 320 for PyPortal
HEIGHT = board.DISPLAY.height  # 240 for PyPortal

# Default colors
BLACK = 0x000000
RED = 0xFF0000
ORANGE = 0xFF8811
YELLOW = 0xFFFF00
GREEN = 0x00FF00
LT_GRN = 0x00BB00
CYAN = 0x00FFFF
BLUE = 0x0000FF
LT_BLUE = 0x000044
VIOLET = 0x9900FF
DK_VIO = 0x110022
WHITE = 0xFFFFFF
GRAY = 0x444455
LCARS_LT_BLU = 0x1B6BA7

# Define the display group
image_group = displayio.Group()

# Background Graphics; image_group[0]
bkg_image = displayio.OnDiskBitmap("/corrosion_mon_bkg.bmp")
bkg = displayio.TileGrid(bkg_image, pixel_shader=bkg_image.pixel_shader)
image_group.append(bkg)

board.DISPLAY.root_group = image_group  # Load display

### Define display graphic, label, and value areas
# Sensor Data Area Title
title = Label(FONT_1, text="Interior", color=CYAN)
title.anchor_point = (0.5, 0.5)
title.anchored_position = (252, 26)
image_group.append(title)

# Temperature
temperature = Label(FONT_3, text=" ", color=WHITE)
temperature.x = 210
temperature.y = 48
image_group.append(temperature)

# Humidity
humidity = Label(FONT_2, text=" ", color=WHITE)
humidity.x = 210
humidity.y = 74
image_group.append(humidity)

# Dew Point
dew_point = Label(
    FONT_2,
    text=" ",
    color=WHITE,
)
dew_point.x = 210
dew_point.y = 91
image_group.append(dew_point)

# Clock Hour:Min
clock_digits = Label(CLOCK_FONT, text=" ", color=WHITE)
clock_digits.anchor_point = (0.5, 0.5)
clock_digits.anchored_position = (198, 170)
image_group.append(clock_digits)

# Weekday, Month, Date, Year
clock_day_mon_yr = Label(FONT_1, text=" ", color=WHITE)
clock_day_mon_yr.anchor_point = (0.5, 0.5)
clock_day_mon_yr.anchored_position = (198, 231)
image_group.append(clock_day_mon_yr)

# Project Message Area
display_message = Label(FONT_1, text=" ", color=YELLOW)
display_message.anchor_point = (0.5, 0.5)
display_message.anchored_position = (158, 106)
image_group.append(display_message)

# Clock Activity Icon Mask
clock_tick_mask = RoundRect(305, 227, 7, 8, 1, fill=VIOLET, outline=None, stroke=0)
image_group.append(clock_tick_mask)

# Corrosion Status Icon and Text
status_icon = Triangle(155, 38, 185, 90, 125, 90, fill=LCARS_LT_BLU, outline=None)
image_group.append(status_icon)

status = Label(FONT_3, text=" ", color=None)
status.anchor_point = (0.5, 0.5)
status.anchored_position = (157, 68)
image_group.append(status)

# Temp/Humid Sensor Icon Mask
sensor_icon_mask = Rect(4, 54, 41, 56, fill=LCARS_LT_BLU, outline=None, stroke=0)
image_group.append(sensor_icon_mask)

# Sensor Heater Icon Mask
heater_icon_mask = Rect(4, 110, 41, 8, fill=LCARS_LT_BLU, outline=None, stroke=0)
image_group.append(heater_icon_mask)

# Clock Icon Mask
clock_icon_mask = Rect(45, 54, 34, 56, fill=LCARS_LT_BLU, outline=None, stroke=0)
image_group.append(clock_icon_mask)

# SD Icon Mask
sd_icon_mask = Rect(4, 156, 72, 31, fill=LCARS_LT_BLU, outline=None, stroke=0)
image_group.append(sd_icon_mask)

# Network Icon Mask
wifi_icon_mask = Rect(4, 188, 72, 30, fill=LCARS_LT_BLU, outline=None, stroke=0)
image_group.append(wifi_icon_mask)

# PCB Temperature
pcb_temp = Label(FONT_1, text="°", color=CYAN)
pcb_temp.anchor_point = (0.5, 0.5)
pcb_temp.anchored_position = (40, 231)
image_group.append(pcb_temp)

gc.collect()


def get_last_value(feed_key):
    """Fetch the latest value of the AIO feed.
    :param str feed_key: The AIO feed key."""
    wifi_icon_mask.fill = None
    try:
        # print(f"throttle limit: {pyportal.network.io_client.get_remaining_throttle_limit()}")
        while pyportal.network.io_client.get_remaining_throttle_limit() <= 10:
            time.sleep(1)  # Wait until throttle limit increases
        last_value = pyportal.network.io_client.receive_data(feed_key)["value"]
        wifi_icon_mask.fill = LCARS_LT_BLU
        return last_value
    except Exception as e:
        # Persistent PyPortal hardware issue: 372, 376 in adafruit_esp32spi._wait_spi_char
        print(f"Error fetching data from feed {feed_key}: {e}")
        print("  MCU will soft reset in 30 seconds.")
        time.sleep(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive
    wifi_icon_mask.fill = LCARS_LT_BLU


def toggle_clock_tick():
    global clock_tick
    if clock_tick:
        clock_tick_mask.fill = RED
        led.value = True
    else:
        clock_tick_mask.fill = None
        led.value = False
    clock_tick = not clock_tick
    return


def update_display():
    """Fetch last values and update the display."""
    # Get the local time and provide hour-of-day for is_daytime method
    clock_icon_mask.fill = None
    wifi_icon_mask.fill = None
    try:
        pyportal.network.get_local_time(os.getenv("TIMEZONE"))
    except Exception as e:
        print(f"Error fetching local time: {e}")

    wifi_icon_mask.fill = LCARS_LT_BLU

    if time.localtime().tm_hour > 12:
        hour = time.localtime().tm_hour - 12
    else:
        hour = time.localtime().tm_hour
    if hour == 0:
        hour = 12

    display_time = f"{hour:2d}:{time.localtime().tm_min:02d}"
    clock_digits.text = display_time
    print(f"Local Time: {display_time}")

    wday = time.localtime().tm_wday
    month = time.localtime().tm_mon
    day = time.localtime().tm_mday
    year = time.localtime().tm_year
    clock_day_mon_yr.text = f"{WEEKDAY[wday]}  {MONTH[month - 1]} {day:02d}, {year:04d}"

    clock_icon_mask.fill = LCARS_LT_BLU

    # Get the workshop sensor data and update the display
    sensor_icon_mask.fill = None

    pcb_temp.text = f"{read_pcb_temperature():.1f}°"
    temperature.text = f"{float(get_last_value("shop.int-temperature")):.1f}°"
    humidity.text = f"{float(get_last_value("shop.int-humidity")):.0f}%"
    dew_point.text = f"{float(get_last_value("shop.int-dewpoint")):.1f}° Dew"

    # Display the corrosion status. Default is no corrosion potential (0 = GREEN).
    corrosion_index = float(get_last_value("shop.int-corrosion-index"))
    if corrosion_index == 0:
        status_icon.fill = LT_GRN
        status.color = None
        alert("NORMAL")
        heater_icon_mask.fill = LCARS_LT_BLU
        sensor_icon_mask.fill = LCARS_LT_BLU
    elif corrosion_index == 1:
        status_icon.fill = YELLOW
        status.color = RED
        alert("CORROSION WARNING")
        heater_icon_mask.fill = LCARS_LT_BLU
        sensor_icon_mask.fill = LCARS_LT_BLU
    elif corrosion_index == 2:
        status_icon.fill = RED
        status.color = BLACK
        alert("CORROSION ALERT")
        heater_icon_mask.fill = None
        sensor_icon_mask.fill = None

    wifi_icon_mask.fill = LCARS_LT_BLU


def alert(text=""):
    # Place alert message in clock message area. Default is the previous message.
    msg_text = text[:20]
    if msg_text == "" or msg_text is None:
        msg_text = ""
        display_message.text = msg_text
    else:
        print("ALERT: " + msg_text)
        display_message.color = RED
        display_message.text = msg_text
        time.sleep(0.1)
        display_message.color = YELLOW
        time.sleep(0.1)
        display_message.color = RED
        time.sleep(0.1)
        display_message.color = YELLOW
        time.sleep(0.5)
        display_message.color = None
    return


def adjust_brightness():
    """Acquire the current lux light sensor value and gradually adjust
    display brightness. Full-scale raw light sensor value (65535)
    is approximately 1100 Lux."""
    raw = 0
    for i in range(2000):
        raw = raw + light_sensor.value
    target_bright = round(map_range(raw / 2000 / 65535 * 1100, 11, 20, 0.01, BRIGHTNESS), 3)
    new_bright = board.DISPLAY.brightness + ((target_bright - board.DISPLAY.brightness) / 5)
    pyportal.set_backlight(round(new_bright, 3))


def read_pcb_temperature():
        """Read the current PCB temperature value in degrees F"""
        return round(celsius_to_fahrenheit(corrosion_sensor.temperature), 1)


last_weather_update = time.monotonic()

# Set Initial Quality Value
quality = 10
watchdog = get_last_value("system-watchdog")
previous_watchdog = watchdog

update_display()  # Fetch initial data from AIO


### Main Loop ###
while True:
    current_time = time.monotonic()

    # Update weather every SAMPLE_INTERVAL seconds
    if current_time - last_weather_update > SAMPLE_INTERVAL:

        # Test for feed quality
        watchdog = get_last_value("system-watchdog")
        if watchdog == previous_watchdog:
            quality -= 1
            if quality < 0: quality = 0
            if quality < QUALITY_THRESHOLD:
                temperature.color = RED
                humidity.color = RED
                dew_point.color = RED
                alert(f"QUAL WARNING : {quality}/10")
        else:
            previous_watchdog = watchdog
            quality = 10
            temperature.color = WHITE
            humidity.color = WHITE
            dew_point.color = WHITE
            alert(f"QUAL NORMAL : {quality}/10")

        last_weather_update = current_time

        update_display()

    # Update time every second
    toggle_clock_tick()
    if time.localtime().tm_hour > 12:
        hour = time.localtime().tm_hour - 12
    else:
        hour = time.localtime().tm_hour
    if hour == 0:
        hour = 12

    display_time = f"{hour:2d}:{time.localtime().tm_min:02d}"
    clock_digits.text = display_time

    adjust_brightness()
    time.sleep(0.682)  # To adjust for 1.0 sec per loop
