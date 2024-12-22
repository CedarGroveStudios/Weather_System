# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
""" pyportal_mikey_weather_display.py

Receives AIO local weather conditions.

For the Adafruit PyPortal M4.
"""

import time
import board
import os
import gc
import displayio
import digitalio
import analogio
import supervisor
import adafruit_pyportal
from simpleio import map_range
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.roundrect import RoundRect

from weatherkit_to_weathmap_icon import kit_to_map_icon

# Set display brightness for startup
board.DISPLAY.brightness = 0

# AIO Weather Receiver Parameters
SAMPLE_INTERVAL = 1200  # Check conditions (seconds)
BRIGHTNESS = 0.75
SOUND = True
ICON = True

# fmt: off
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# fmt: on

# Start-up values
message = ""
clock_tick = False

# Instantiate the PyPortal
pyportal = adafruit_pyportal.PyPortal(
    status_neopixel=board.NEOPIXEL, default_bg="/pyportal_startup.bmp"
)
pyportal.set_backlight(BRIGHTNESS)

# Play storm tracker welcome audio; True disables speaker after playing
if SOUND:
    pyportal.play_file("storm_tracker.wav", wait_to_finish=True)

# Instantiate the Red LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

# Instantiate the light sensor
light_sensor = analogio.AnalogIn(board.LIGHT)

# Load the text fonts from the fonts folder
SMALL_FONT = bitmap_font.load_font("/fonts/Arial-12.bdf")
MEDIUM_FONT = bitmap_font.load_font("/fonts/Arial-16.bdf")
LARGE_FONT = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")

# The board's integral display size
WIDTH = board.DISPLAY.width  # 320 for PyPortal
HEIGHT = board.DISPLAY.height  # 240 for PyPortal

# Default colors
BLACK = 0x000000
RED = 0xFF0000
ORANGE = 0xFF8811
YELLOW = 0xFFFF00
VIOLET = 0x9900FF
PURPLE = 0xFF00FF
WHITE = 0xFFFFFF

# Define the display group
image_group = displayio.Group()
board.DISPLAY.root_group = image_group  # Load display and watch it build

### Define display graphic, label, and value areas
# Create an icon background layer; image_group[0]
icon_image = displayio.OnDiskBitmap("/icons/01d.bmp")
icon_bg = displayio.TileGrid(icon_image, pixel_shader=icon_image.pixel_shader)
image_group.append(icon_bg)

clock_day_mon_yr = Label(MEDIUM_FONT, text=" ")
clock_day_mon_yr.anchor_point = (0, 0)
clock_day_mon_yr.anchored_position = (10, 15)
clock_day_mon_yr.color = PURPLE
image_group.append(clock_day_mon_yr)

clock_digits = Label(MEDIUM_FONT, text=" ")
clock_digits.anchor_point = (1.0, 0)
clock_digits.anchored_position = (board.DISPLAY.width - 10, 15)
clock_digits.color = WHITE
image_group.append(clock_digits)

clock_tick_mask = RoundRect(310, 4, 7, 8, 1, fill=VIOLET, outline=None, stroke=0)
image_group.append(clock_tick_mask)

windspeed = Label(MEDIUM_FONT, text=" ")
windspeed.anchor_point = (0, 0)
windspeed.anchored_position = (10, 44)
windspeed.color = WHITE
image_group.append(windspeed)

windgust = Label(SMALL_FONT, text=" ")
windgust.anchor_point = (0, 0)
windgust.anchored_position = (10, 68)
windgust.color = RED
image_group.append(windgust)

sunrise = Label(SMALL_FONT, text="sunrise")
sunrise.anchor_point = (1.0, 0.0)
sunrise.anchored_position = (board.DISPLAY.width - 10, 44)
sunrise.color = YELLOW
image_group.append(sunrise)

sunset = Label(SMALL_FONT, text="sunset")
sunset.anchor_point = (1.0, 0.0)
sunset.anchored_position = (board.DISPLAY.width - 10, 60)
sunset.color = ORANGE
image_group.append(sunset)

description = Label(LARGE_FONT, text=" ")
description.anchor_point = (0, 0)
description.anchored_position = (10, 180)
description.color = WHITE
image_group.append(description)

long_desc = Label(SMALL_FONT, text=" ")
long_desc.anchor_point = (0, 0)
long_desc.anchored_position = (10, 215)
long_desc.color = WHITE
image_group.append(long_desc)

temperature = Label(LARGE_FONT, text=" ")
temperature.anchor_point = (1.0, 0)
temperature.anchored_position = (board.DISPLAY.width - 10, 180)
temperature.color = WHITE
image_group.append(temperature)

humidity = Label(SMALL_FONT, text=" ")
humidity.anchor_point = (1.0, 0)
humidity.anchored_position = (board.DISPLAY.width - 10, 215)
humidity.color = PURPLE
image_group.append(humidity)

# Project Message Area
display_message = Label(SMALL_FONT, text=" ", color=YELLOW)
display_message.anchor_point = (0.5, 0.5)
display_message.anchored_position = (board.DISPLAY.width // 2, 231)
image_group.append(display_message)

gc.collect()


def get_last_value(feed_key):
    """Fetch the latest value of the AIO feed.
    :param str feed_key: The AIO feed key."""
    try:
        # print(f"throttle limit: {pyportal.network.io_client.get_remaining_throttle_limit()}")
        while pyportal.network.io_client.get_remaining_throttle_limit() <= 10:
            time.sleep(1)  # Wait until throttle limit increases
        # time.sleep(1)  # Wait after throttle check query to retrieve feed
        last_value = pyportal.network.io_client.receive_data(feed_key)["value"]
        return last_value
    except Exception as e:
        # 372, 376 in adafruit_esp32spi._wait_spi_char
        print(f"Error fetching data from feed {feed_key}: {e}")
        print("  MCU will soft reset in 30 seconds.")
        time.sleep(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive


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
    gc.collect()

    # Get the local time and provide hour-of-day for is_daytime method
    try:
        pyportal.network.get_local_time(os.getenv("TIMEZONE"))
    except Exception as e:
        print(f"Error fetching local time: {e}")

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

    # Get weather conditions from client AIO feeds
    wind_dir = get_last_value("weather-winddirection")
    windspeed.text = f"{wind_dir} {float(get_last_value("weather-windspeed")):.0f} MPH"
    windgust.text = f"{float(get_last_value("weather-windgusts")):.0f} MPH Gusts"

    # get sunrise and sunset and daylight here

    daylight = get_last_value("weather-daylight")

    description.text = get_last_value("weather-description")
    long_desc.text = kit_to_map_icon[description.text][0]

    # Create icon filename
    if daylight == "True":
        icon_suffix = "d"
    else:
        icon_suffix = "n"
    icon_file = f"/icons/{kit_to_map_icon[description.text][1]}{icon_suffix}.bmp"
    print(f"Icon filename: {icon_file}")

    if ICON:
        image_group.pop(0)
        icon_image = displayio.OnDiskBitmap(icon_file)
        icon_bg = displayio.TileGrid(icon_image, pixel_shader=icon_image.pixel_shader)
        image_group.insert(0, icon_bg)

    temperature.text = f"{float(get_last_value("weather-temperature")):.0f}°"
    humidity.text = f"{float(get_last_value("weather-humidity")):.0f}% RH"

    gc.collect()

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


last_weather_update = time.monotonic()
alert("INITIALIZING")
update_display()  # Fetch initial data from AIO
alert("READY")

### Main loop ###
while True:
    current_time = time.monotonic()

    # Update weather every SAMPLE_INTERVAL seconds
    if current_time - last_weather_update > SAMPLE_INTERVAL:
        alert("UPDATING CONDITIONS")
        update_display()
        last_weather_update = current_time
        alert("READY")

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
    time.sleep(1)
