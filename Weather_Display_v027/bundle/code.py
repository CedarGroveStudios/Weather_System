# SPDX-FileCopyrightText: 2024, 2025 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
"""
cedargrove_weather_display_code.py

Displays AIO+ weather conditions to AIO feeds in support of remote workshop
corrosion monitoring.

For the Adafruit ESP32-S3 4Mb/2Mb Feather with attached 3.5-inch TFT FeatherWing.
"""

import board
import microcontroller
import digitalio
import gc
import os
import time
import rtc
import ssl
import supervisor
import neopixel

from adafruit_datetime import datetime
import adafruit_connection_manager
import wifi
import adafruit_requests
from adafruit_io.adafruit_io import IO_HTTP

from cedargrove_temperaturetools.unit_converters import celsius_to_fahrenheit, fahrenheit_to_celsius
from cedargrove_temperaturetools.dew_point import dew_point as dew_point_calc
from source_display_graphics import Display

# TFT Display Parameters
BRIGHTNESS = 0.50
ROTATION = 180

display = Display(rotation=ROTATION, brightness=BRIGHTNESS)

# fmt: off
# A couple of day/month lookup tables
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", ]

# Default colors
BLACK   = 0x000000
RED     = 0xFF0000
ORANGE  = 0xFF8811
YELLOW  = 0xFFFF00
GREEN   = 0x00FF00
LT_GRN  = 0x5dd82f
CYAN    = 0x00FFFF
BLUE    = 0x0000FF
LT_BLUE = 0x000044
VIOLET  = 0x9900FF
DK_VIO  = 0x110022
WHITE   = 0xFFFFFF
GRAY    = 0x444455
LCARS_LT_BLU = 0x07A2FF

# Define a few states and mode values
STARTUP = VIOLET
NORMAL  = LCARS_LT_BLU
FETCH   = YELLOW
ERROR   = RED
THROTTLE_DELAY = GREEN
# fmt: on

# Operating Mode
display.mode.text = "DISPLAY"

# Display Mode Parameters
SAMPLE_INTERVAL = 240  # Check sensor and AIO Weather (seconds)

# Internal cooling fan threshold
FAN_ON_THRESHOLD_F = 100  # Degrees Fahrenheit

# Instantiate cooling fan control (D5)
fan = digitalio.DigitalInOut(board.D5)
fan.direction = digitalio.Direction.OUTPUT
fan.value = False  # Initialize with fan off

# Instantiate the Red LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

# Initialize the NeoPixel
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=BRIGHTNESS)
pixel[0] = STARTUP  # Initializing

# Initialize Heartbeat Indicator Value
clock_tick = False


def read_cpu_temp():
    """Read the ESP32-S3 internal CPU temperature sensor and turn on
    fan if threshold is exceeded.
    Nominal operating range is -40C to 85C (-40F to 185F)."""
    cpu_temp_f = celsius_to_fahrenheit(microcontroller.cpu.temperature)
    if cpu_temp_f > FAN_ON_THRESHOLD_F:  # Turn on cooling fan if needed
        fan.value = True
    else:
        fan.value = False
    return cpu_temp_f


def wind_direction(heading):
    """Provide a one or two character string representation of a compass
    heading value. Returns '--' if heading is None.
    :param int heading: The compass heading. No default."""
    if heading is None:
        return "--"
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][
        int(((heading + 22.5) % 360) / 45)
    ]


def get_last_value(feed_key):
    """Fetch the latest value of the AIO feed.
    :param str feed_key: The AIO feed key."""
    pixel[0] = FETCH
    display.wifi_icon_mask.fill = None
    try:
        # print(f"throttle limit: {io.get_remaining_throttle_limit()}")
        while io.get_remaining_throttle_limit() <= 10:
            pixel[0] = THROTTLE_DELAY
            time.sleep(1)  # Wait until throttle limit increases
        pixel[0] = FETCH
        last_value = io.receive_data(feed_key)["value"]
    except Exception as aio_feed_error:
        pixel[0] = ERROR
        display.image_group = None
        print(f"FAIL: <- {feed}")
        print(f"  {str(aio_feed_error)}")
        print("  MCU will soft reset in 30 seconds.")
        busy(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive
    display.wifi_icon_mask.fill = LCARS_LT_BLU
    pixel[0] = NORMAL  # Success
    return last_value


def busy(delay):
    """An alternative 'time.sleep' function that blinks the LED once per second.
    Time display is updated from localtime each second. A blocking method.
    :param float delay: The time delay in seconds. No default."""
    global clock_tick
    for blinks in range(int(round(delay, 0))):
        start = time.monotonic()
        if clock_tick:
            display.clock_tick_mask.fill = YELLOW
            led.value = True
        else:
            display.clock_tick_mask.fill = None
            led.value = False
        clock_tick = not clock_tick

        if time.localtime().tm_hour > 12:
            hour = time.localtime().tm_hour - 12
        else:
            hour = time.localtime().tm_hour
        if hour == 0:
            hour = 12

        local_time = f"{hour:2d}:{time.localtime().tm_min:02d}"
        display.clock_digits.text = local_time

        display.pcb_temp.text = f"{gc.mem_free()/10**6:.3f} Mb  {read_cpu_temp():.0f}°  {SAMPLE_INTERVAL - blinks}"

        delay = max((1 - (time.monotonic() - start)), 0)
        time.sleep(delay)


def update_local_time():
    pixel[0] = FETCH  # Busy
    display.clock_icon_mask.fill = None
    display.wifi_icon_mask.fill = None
    try:
        rtc.RTC().datetime = time.struct_time(io.receive_time(os.getenv("TIMEZONE")))
    except Exception as time_error:
        print(f"  FAIL: Reverting to local time: {time_error}")

    if time.localtime().tm_hour > 12:
        hour = time.localtime().tm_hour - 12
    else:
        hour = time.localtime().tm_hour
    if hour == 0:
        hour = 12

    local_time = f"{hour:2d}:{time.localtime().tm_min:02d}"
    display.clock_digits.text = local_time

    wday = time.localtime().tm_wday
    month = time.localtime().tm_mon
    day = time.localtime().tm_mday
    year = time.localtime().tm_year
    display.clock_day_mon_yr.text = (
        f"{WEEKDAY[wday]}  {MONTH[month - 1]} {day:02d}, {year:04d}"
    )
    # print(display.clock_day_mon_yr.text)
    print(
        f"Time: {local_time} {WEEKDAY[wday]}  {MONTH[month - 1]} {day:02d}, {year:04d}"
    )
    display.clock_icon_mask.fill = LCARS_LT_BLU
    display.wifi_icon_mask.fill = LCARS_LT_BLU
    pixel[0] = NORMAL  # Normal


# Connect to Wi-Fi
pixel[0] = FETCH  # Busy
display.wifi_icon_mask.fill = None
try:
    # Connect to Wi-Fi access point
    print(f"Connect to {os.getenv('CIRCUITPY_WIFI_SSID')}")
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD")
    )
    print("  CONNECTED to WiFi")
except Exception as wifi_access_error:
    pixel[0] = ERROR  # Error
    display.image_group = None
    print(f"  FAIL: WiFi connect \n    Error: {wifi_access_error}")
    print("    MCU will soft reset in 30 seconds.")
    busy(30)
    supervisor.reload()  # soft reset: keeps the terminal session alive
display.wifi_icon_mask.fill = LCARS_LT_BLU
pixel[0] = NORMAL  # Success

# Initialize the weather_table and history variables
weather_table = None
weather_table_old = None

# Initialize a socket pool and requests session
pixel[0] = FETCH  # Busy
display.wifi_icon_mask.fill = None
print("Connecting to the AIO HTTP service")
try:
    pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())
    io = IO_HTTP(os.getenv("AIO_USERNAME"), os.getenv("AIO_KEY"), requests)
except Exception as aio_client_error:
    pixel[0] = ERROR  # Error
    display.image_group = None
    print(f"  FAIL: AIO HTTP client connect \n    Error: {aio_client_error}")
    print("    MCU will soft reset in 30 seconds.")
    busy(30)
    supervisor.reload()  # soft reset: keeps the terminal session alive
display.wifi_icon_mask.fill = LCARS_LT_BLU
pixel[0] = NORMAL  # Normal

### PRIMARY LOOP ###
while True:
    print("=" * 35)
    update_local_time()
    print(
        f"Throttle Remain/Limit: {io.get_remaining_throttle_limit()}/{io.get_throttle_limit()}"
    )
    print("-" * 35)

    # Read the local temperature and humidity sensor
    print("Workshop Conditions")
    """Read the workshop sensor's temperature and humidity, calculate
    dew point and corrosion index, and display results."""
    pixel[0] = FETCH  # Busy
    display.sensor_icon_mask.fill = None

    # Get the sensor temperature from AIO feed
    display.temp_mask.fill = BLACK
    display.dew_pt_mask.fill = BLACK
    temp_f = float(get_last_value("shop.int-temperature"))
    temp_c = round(fahrenheit_to_celsius(temp_f), 1)  # Celsius
    display.temperature.text = f"{temp_f:.0f}°"
    print(f"  Temp  {display.temperature.text}")
    display.temp_mask.fill = None

    # Get the sensor humidity from AIO feed
    display.humid_mask.fill = BLACK
    humid_pct = float(get_last_value("shop.int-humidity"))
    display.humidity.text = f"{humid_pct:.0f}%"
    print(f"  Humid {display.humidity.text}")
    display.humid_mask.fill = None

    # Display dew point
    if None in (temp_c, humid_pct):
        dew_c = None
        dew_f = None
    else:
        dew_c, _ = dew_point_calc(temp_c, humid_pct)
        dew_f = round(celsius_to_fahrenheit(dew_c), 1)
    display.dew_point.text = f"{dew_f:.0f}°"
    print(f"  Dew   {display.dew_point.text}")
    display.dew_pt_mask.fill = None

    display.sensor_icon_mask.fill = LCARS_LT_BLU
    pixel[0] = NORMAL  # Success

    # Calculate and display corrosion index value.
    #   Turn on sensor heater when index = 2 (ALERT);
    #   heater turns off for other corrosion index conditions.
    if (temp_c <= dew_c + 2) or humid_pct >= 80:
        corrosion_index = 2  # CORROSION ALERT
        display.status_icon.fill = RED
        display.status.color = BLACK
        display.status.text = "ALERT"
        display.alert("CORROSION ALERT")

    elif temp_c <= dew_c + 5:
        corrosion_index = 1  # CORROSION WARNING
        display.status_icon.fill = YELLOW
        display.status.color = RED
        display.status.text = "WARN"
        display.alert("CORROSION WARNING")

    else:
        corrosion_index = 0  # NORMAL
        display.status_icon.fill = LT_GRN
        display.status.color = BLACK
        display.status.text = "OK"
        display.alert("NORMAL")

    display.sensor_icon_mask.fill = LCARS_LT_BLU

    print("-" * 35)

    # Receive and update the conditions from AIO+ Weather
    pixel[0] = FETCH  # AIO+ Weather fetch in progress (yellow)
    display.wifi_icon_mask.fill = None
    try:
        while io.get_remaining_throttle_limit() <= 10:
            pixel[0] = THROTTLE_DELAY
            time.sleep(1)  # Wait until throttle limit increases
        pixel[0] = FETCH
        weather_table = io.receive_weather(os.getenv("WEATHER_TOPIC_KEY"))
    except Exception as receive_weather_error:
        pixel[0] = ERROR  # Error (red)
        display.image_group = None
        print(f"FAIL: receive weather from AIO+ \n  {str(receive_weather_error)}")
        print("  MCU will soft reset in 30 seconds.")
        busy(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive

    # print(weather_table)  # This is a very large json table
    # print("... weather table received ...")
    display.wifi_icon_mask.fill = LCARS_LT_BLU
    pixel[0] = NORMAL  # Success

    if weather_table:
        forecast_table = weather_table["forecast_days_1"]  # for sunrise/sunset
        weather_table = weather_table["current"]  # extract a subset and reduce size
        if weather_table != weather_table_old:
            print("Exterior Conditions")
            display.dew_pt_mask.fill = BLACK
            display.temp_mask.fill = BLACK
            display.humid_mask.fill = BLACK
            display.wind_mask.fill = BLACK
            display.gusts_mask.fill = BLACK
            
            table_desc = weather_table["conditionCode"]
            print(f"  {table_desc}")

            table_temp = f"{celsius_to_fahrenheit(weather_table['temperature']):.0f}"
            display.ext_temp.text = f"{table_temp}°"
            print(f"  Temp  {display.ext_temp.text}")

            table_humid = f"{float(weather_table['humidity']) * 100:.0f}"
            display.ext_humid.text = f"{table_humid}%"
            print(f"  Humid {display.ext_humid.text}")

            table_dew_point = f"{weather_table['temperatureDewPoint']:.0f}"
            display.ext_dew.text = (
            f"{celsius_to_fahrenheit(float(table_dew_point)):.0f}°")
            print(f"  Dew   {display.ext_dew.text}")
            display.dew_pt_mask.fill = None
            display.temp_mask.fill = None
            display.humid_mask.fill = None

            table_wind_speed = f"{weather_table['windSpeed'] * 0.6214:.0f}"
            table_wind_dir = wind_direction(weather_table["windDirection"])
            display.ext_wind.text = f"{table_wind_dir} {table_wind_speed}"
            print(f"  Wind  {display.ext_wind.text} MPH")
            display.wind_mask.fill = None

            table_wind_gusts = f"{weather_table['windGust'] * 0.6214:.0f}"
            display.ext_gusts.text = table_wind_gusts
            print(f"  Gusts {display.ext_gusts.text} MPH")
            display.gusts_mask.fill = None

            table_timestamp = weather_table["metadata"]["readTime"]
            table_daylight = weather_table["daylight"]

            display.display_icon(table_desc, table_daylight)
            display.ext_desc.text = table_desc

            table_sunrise = datetime.fromisoformat(forecast_table["sunrise"]).timetuple()
            sunrise_hr = table_sunrise.tm_hour + os.getenv("TIMEZONE_OFFSET")
            if sunrise_hr < 0:
                sunrise_hr = sunrise_hr + 24
            if sunrise_hr > 12:
                sunrise_hr = sunrise_hr - 12
            if sunrise_hr == 0:
                sunrise_hr = 12
            display.ext_sunrise.text = (
                f"rise {sunrise_hr:02d}:{table_sunrise.tm_min:02d}"
            )

            table_sunset = datetime.fromisoformat(forecast_table["sunset"]).timetuple()
            sunset_hr = table_sunset.tm_hour + os.getenv("TIMEZONE_OFFSET")
            if sunset_hr < 0:
                sunset_hr = sunset_hr + 24
            if sunset_hr > 12:
                sunset_hr = sunset_hr - 12
            if sunset_hr == 0:
                sunset_hr = 12
            display.ext_sunset.text = f"set  {sunset_hr:02d}:{table_sunset.tm_min:02d}"

            weather_table_old = weather_table  # to watch for changes
        else:
            print("... waiting for new weather conditions")

        print("-" * 35)
        print(f"NOTE Cooling fan state: {fan.value}  CPU: {read_cpu_temp():.0f}°")
        print("...")
        busy(SAMPLE_INTERVAL)  # Wait before checking sensor and AIO Weather
    else:
        w_topic_desc = os.getenv("WEATHER_TOPIC_DESC")
        print(f"  ... waiting for conditions from {w_topic_desc}")
        busy(10)  # Step up query rate when first starting