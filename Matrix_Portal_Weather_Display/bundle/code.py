# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
"""
cedargrove_matrixweather_display.py

Receives AIO local weather and workshop conditions.
For the Adafruit Matrix Portal S3.
"""

import time
import board
import terminalio
from adafruit_matrixportal.matrixportal import MatrixPortal
from cedargrove_palettefader.palettefader import PaletteFader
from weatherkit_to_weathmap_icon import kit_to_map_icon

# AIO Weather Receiver Parameters
SAMPLE_INTERVAL = 1200  # seconds; 20 minutes
BRIGHTNESS = 0.1

# Instantiate matrix display
mp = MatrixPortal(width=64, height=32, bit_depth=6, debug=False, rotation=90, status_neopixel=board.NEOPIXEL)

# Load splash graphic and dim per BRIGHTNESS
mp.set_background("images/background_sun_clouds.bmp", (65, 65))
bkg_normal = PaletteFader(
    mp.graphics._bg_sprite.pixel_shader,
    BRIGHTNESS,
    gamma=0.65,
    normalize=True,
)
mp.graphics._bg_sprite.pixel_shader = bkg_normal.palette
mp.graphics._bg_sprite.x = 0
mp.graphics._bg_sprite.y = 0

# Define color list for labels and dim per BRIGHTNESS
LABEL_COLORS_REF = [
    0xFFFF00,  # yellow; temperature
    0x0066FF,  # blue; description
    0x00FFFF,  # cyan; humidity
    0xFF00FF,  # purple; wind
    0x800000,  # red; progress bar
    0x008000,  # green; progress bar
]
label_colors = PaletteFader(LABEL_COLORS_REF, BRIGHTNESS, gamma=1.0, normalize=False)

# Define the temperature label
mp.add_text(
    text_font=terminalio.FONT,
    text_color=label_colors.palette[0],
    text_position=(16, 6),
    text_anchor_point=(0.5, 0.5),
    scrolling=False,
)

# Define the wind speed/direction label
mp.add_text(
    text_font=terminalio.FONT,
    text_color=label_colors.palette[2],
    text_position=(16, 45),
    text_anchor_point=(0.5, 0.5),
    scrolling=False,
)

# Define the humidity label
mp.add_text(
    text_font=terminalio.FONT,
    text_color=label_colors.palette[3],
    text_position=(16, 34),
    text_anchor_point=(0.5, 0.5),
    scrolling=False,
)

# Define the scrolling description label
mp.add_text(
    text_font=terminalio.FONT,
    text_color=label_colors.palette[1],
    text_position=(16, 55),
    text_anchor_point=(0.5, 0.5),
    scrolling=True,
)

# Define the progress bar label
mp.add_text(
    text_font=terminalio.FONT,
    text_color=label_colors.palette[3],
    text_position=(16, 61),
    text_anchor_point=(0.5, 0.5),
    scrolling=False,
)
mp.set_text(".", 4)


def get_last_value(feed_key):
    """Fetch the latest value of the AIO feed.
    :param str feed_key: The AIO feed key."""
    try:
        # print(f"throttle limit: {mp.network.io_client.get_remaining_throttle_limit()}")
        while mp.network.io_client.get_remaining_throttle_limit() <= 10:
            time.sleep(1)  # Wait until throttle limit increases
        last_value = mp.network.io_client.receive_data(feed_key)["value"]
        return last_value
    except Exception as e:
        print(f"Error fetching data from feed {feed_key}: {e}")


def update_display():
    """Fetch last values and update the display."""
    temperature = get_last_value("weather-temperature")
    temperature = f"{int(round(float(temperature), 0))} F"

    humidity = get_last_value("weather-humidity")
    humidity = f"{int(round(float(humidity), 0))}%"

    condition = get_last_value("weather-description")
    try:
        current_condition = kit_to_map_icon[condition][0]
    except:
        current_condition = "unknown"  # If condition is not in translator

    daylight = get_last_value("weather-daylight")
    if daylight == "True":
        icon_suffix = "d"
    else:
        icon_suffix = "n"

    wind_speed = get_last_value("weather-windspeed")
    wind_speed = f"{int(round(float(wind_speed), 0))}"

    wind_dir = get_last_value("weather-winddirection")

    wind_gusts = get_last_value("weather-windgusts")
    wind_gusts = f"{int(round(float(wind_gusts), 0))}"

    wind = f"{wind_dir} {wind_speed}"

    shop_temperature = get_last_value("shop.int-temperature")
    shop_temperature = f"{int(round(float(shop_temperature), 0))}"

    shop_humidity = get_last_value("shop.int-humidity")
    shop_humidity = f"{int(round(float(shop_humidity), 0))}"

    # Get the local time and provide hour-of-day for is_daytime method
    try:
        mp.network.get_local_time("America/Los_Angeles")
        display_time = f"{time.localtime().tm_hour:2d}:{time.localtime().tm_min:2d}"
        print(f"Local Time: {display_time}")
    except Exception as e:
        print(f"Error fetching local time: {e}")

    # Create icon file name
    if current_condition != "unknown":
        icon = f"index_{kit_to_map_icon[condition][2]:02d}{icon_suffix}.bmp"
    else:
        icon = "index_08d.bmp"  # Default icon if condition not in translator
    print(f"Icon filename: {icon}")

    mp.set_text(temperature, 0)
    mp.set_text(humidity, 1)
    mp.set_text(wind, 2)
    mp.set_text(f"{current_condition} Gusts:{wind_gusts} Shop:{shop_temperature}/{shop_humidity}%", 3)

    mp.set_background(f"images/{icon}", (65, 65))
    mp.graphics._bg_sprite.pixel_shader.make_transparent(0)
    icon_normal = PaletteFader(
        mp.graphics._bg_sprite.pixel_shader,
        BRIGHTNESS,
        gamma=1.0,
        normalize=True,
    )
    mp.graphics._bg_sprite.pixel_shader = icon_normal.palette
    mp.graphics._bg_sprite.x = 8
    mp.graphics._bg_sprite.y = 12

old_prog_bar_x = -1
last_weather_update = time.monotonic()
update_display()

# Main loop
while True:
    current_time = time.monotonic()

    # Update weather every SAMPLE_INTERVAL seconds
    if current_time - last_weather_update > SAMPLE_INTERVAL:
        update_display()
        last_weather_update = current_time

    prog_bar_x = int(round(32 * (current_time - last_weather_update) / SAMPLE_INTERVAL, 0))
    if prog_bar_x != old_prog_bar_x:
        if prog_bar_x > 25:
            mp._text[4]["color"] = label_colors.palette[4]
        else:
            mp._text[4]["color"] = label_colors.palette[5]
        mp._text[4]["position"] = ((prog_bar_x, 61))
        mp.set_text(".", 4)
        old_prog_bar_x = prog_bar_x

    # Sleep for 0.1 second then scroll wind and description text
    time.sleep(0.10)  # Sleep for 0.1 second
    mp.scroll()
