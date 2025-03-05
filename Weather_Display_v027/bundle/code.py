# SPDX-FileCopyrightText: 2024, 2025 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
"""
cedargrove_weather_display_v027/code.py

Displays AIO+ weather conditions to AIO feeds in support of remote workshop
corrosion monitoring.

For the Adafruit ESP32-S3 4Mb/2Mb Feather with attached 3.5-inch TFT FeatherWing.
TFT brightness sensor phototransistor is connected to board.A3. Local cooling
fan control is connected to board.A4.
"""

import board
import microcontroller
import analogio
import digitalio
import gc
import os
import time
import rtc
import ssl
import supervisor
import neopixel
from simpleio import map_range

from adafruit_datetime import datetime
import adafruit_connection_manager
import wifi
import adafruit_requests
from adafruit_io.adafruit_io import IO_HTTP

from cedargrove_temperaturetools.unit_converters import celsius_to_fahrenheit, fahrenheit_to_celsius
from cedargrove_temperaturetools.dew_point import dew_point as dew_point_calc
from source_display_graphics import Display

# TFT Display Parameters
BRIGHTNESS = 1.0
ROTATION = 180
LIGHT_SENSOR = True  # True when ALS-PT19 sensor is connected to board.A3

display = Display(rotation=ROTATION, brightness=BRIGHTNESS)

# fmt: off
# A couple of day/month lookup tables
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", ]

# Define a few state and mode colors
STARTUP = display.VIOLET
NORMAL = display.LCARS_LT_BLU
FETCH = display.YELLOW
ERROR = display.RED
THROTTLE_DELAY = display.LT_GRN
# fmt: on

# Operating Mode
display.mode.text = "DISPLAY"

# Display Mode Parameters
SAMPLE_INTERVAL = 240  # Check sensor and AIO Weather (seconds)

# Internal cooling fan threshold
FAN_ON_THRESHOLD_F = 100  # Degrees Fahrenheit

# Instantiate cooling fan control (A4)
fan = digitalio.DigitalInOut(board.A4)
fan.direction = digitalio.Direction.OUTPUT
fan.value = False  # Initialize with fan off

# Instantiate the ALS-PT19 light sensor
light_sensor = analogio.AnalogIn(board.A3)

# Instantiate the Red LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

# Initialize the NeoPixel
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=BRIGHTNESS)
pixel[0] = STARTUP  # Initializing

# Initialize Heartbeat Indicator Value and brightness history
clock_tick = False
old_brightness = BRIGHTNESS


def am_pm(hour):
    """Provide an adjusted hour and AM/PM string to create to a
    12-hour time string.
    :param int hour: The clock hour. No default."""
    if hour < 12:
        if hour == 0:
            hour = 12
        return hour, "AM"
    if hour == 12:
        return 12, "PM"
    if hour > 12:
        hour = hour - 12
    return hour, "PM"


def read_cpu_temp():
    """Read the ESP32-S3 internal CPU temperature sensor and turn on
    fan if threshold is exceeded.
    Nominal operating range is -40C to 85C (-40F to 185F)."""
    cpu_temp_f = celsius_to_fahrenheit(microcontroller.cpu.temperature)
    if cpu_temp_f > FAN_ON_THRESHOLD_F:  # Turn on cooling fan if needed
        fan.value = True
        display.fan_icon_mask.fill = None
    else:
        fan.value = False
        display.fan_icon_mask.fill = display.LCARS_LT_BLU
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


def get_last_value(feed_key, json=False):
    """Fetch the latest value of the AIO feed.
    :param str feed_key: The AIO feed key.
    :param bool json: Return json string rather than feed["value"]."""
    pixel[0] = FETCH
    display.wifi_icon_mask.fill = None
    try:
        # print(f"throttle limit: {io.get_remaining_throttle_limit()}")
        while io.get_remaining_throttle_limit() <= 10:
            pixel[0] = THROTTLE_DELAY
            time.sleep(1)  # Wait until throttle limit increases
        pixel[0] = FETCH
        if json:
            last_value = io.receive_data(feed_key)
        else:
            last_value = io.receive_data(feed_key)["value"]
    except Exception as aio_feed_error:
        pixel[0] = ERROR
        display.image_group = None
        print(f"FAIL: <- {feed}")
        print(f"  {str(aio_feed_error)}")
        print("  MCU will soft reset in 30 seconds.")
        busy(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive
    display.wifi_icon_mask.fill = display.LCARS_LT_BLU
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
            display.clock_tick_mask.fill = display.YELLOW
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

        display.pcb_temp.text = f"{gc.mem_free() / 10 ** 6:.3f} Mb  {read_cpu_temp():.0f}°  {SAMPLE_INTERVAL - blinks}"

        # Watch for and adjust to ambient light changes
        adjust_brightness()

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

    hour, _ = am_pm(time.localtime().tm_hour)
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
    display.clock_icon_mask.fill = display.LCARS_LT_BLU
    display.wifi_icon_mask.fill = display.LCARS_LT_BLU
    pixel[0] = NORMAL  # Normal


def adjust_brightness():
    """Acquire the ALS-PT19 light sensor value and gradually adjust display
    brightness based on ambient light. The display brightness ranges from 0.05
    to BRIGHTNESS when the ambient light level falls between 5 and 200 lux.
    Full-scale raw light sensor value (65535) is approximately 1500 Lux."""
    global old_brightness
    if not LIGHT_SENSOR:
        return
    raw = 0
    for i in range(2000):
        raw = raw + light_sensor.value

    target_brightness = round(
        map_range(raw / 2000 / 65535 * 1500, 5, 200, 0.3, BRIGHTNESS), 3
    )
    new_brightness = round(
        old_brightness + ((target_brightness - old_brightness) / 5), 3
    )
    display.brightness = new_brightness
    pixel.brightness = new_brightness
    old_brightness = new_brightness


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
display.wifi_icon_mask.fill = display.LCARS_LT_BLU
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
display.wifi_icon_mask.fill = display.LCARS_LT_BLU
pixel[0] = NORMAL  # Normal

# ### PRIMARY LOOP ###
while True:
    print("=" * 35)

    # Update local time display and monitor AIO throttle limit
    update_local_time()
    print(
        f"Throttle Remain/Limit: {io.get_remaining_throttle_limit()}/{io.get_throttle_limit()}"
    )
    print("-" * 35)

    # Check AIO Feed Quality
    q_json = get_last_value("system-watchdog", json=True)
    created_at_ts = (datetime.fromisoformat(q_json["created_at"]).timestamp()) + (
                os.getenv("TIMEZONE_OFFSET") * 60 * 60)
    # print((0, (time.time() - created_at_ts) / 60))  # plot created time delta

    if time.time() - created_at_ts > 10 * 60:
        # If created time is > 10 min in the past, we have a quality issue
        print("WARNING: Source Quality Issue; check Weather Source device")
        display.quality_icon_mask.fill = None
        display.alert("QUALITY WARN")
    else:
        print("INFO: Source Quality is OK")
        display.quality_icon_mask.fill = display.LCARS_LT_BLU
        display.alert("QUALITY OK")

    # Read the local temperature and humidity sensor
    print("Workshop Conditions")
    """Read the workshop sensor's temperature and humidity, calculate
    dew point and corrosion index, and display results."""
    pixel[0] = FETCH  # Busy
    display.sensor_icon_mask.fill = None

    # Get the sensor temperature from AIO feed
    display.temp_mask.fill = display.BLACK
    display.dew_pt_mask.fill = display.BLACK
    temp_f = float(get_last_value("shop.int-temperature"))
    temp_c = round(fahrenheit_to_celsius(temp_f), 1)  # Celsius
    display.temperature.text = f"{temp_f:.0f}°"
    print(f"  Temp  {display.temperature.text}")
    display.temp_mask.fill = None

    # Get the sensor humidity from AIO feed
    display.humid_mask.fill = display.BLACK
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

    display.sensor_icon_mask.fill = display.LCARS_LT_BLU
    pixel[0] = NORMAL  # Success

    # Calculate and display corrosion index value.
    #   Turn on sensor heater when index = 2 (ALERT);
    #   heater turns off for other corrosion index conditions.
    if (temp_c <= dew_c + 2) or humid_pct >= 80:
        corrosion_index = 2  # CORROSION ALERT
        display.status_icon.fill = display.RED
        display.status.color = display.BLACK
        display.status.text = "ALERT"
        display.alert("CORROSION ALERT")

    elif temp_c <= dew_c + 5:
        corrosion_index = 1  # CORROSION WARNING
        display.status_icon.fill = display.YELLOW
        display.status.color = display.RED
        display.status.text = "WARN"
        display.alert("CORROSION WARNING")

    else:
        corrosion_index = 0  # NORMAL
        display.status_icon.fill = display.LT_GRN
        display.status.color = display.BLACK
        display.status.text = "OK"
        display.alert("NORMAL")

    display.sensor_icon_mask.fill = display.LCARS_LT_BLU

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
    display.wifi_icon_mask.fill = display.LCARS_LT_BLU
    pixel[0] = NORMAL  # Success

    if weather_table:
        forecast_table = weather_table["forecast_days_1"]  # for sunrise/sunset
        weather_table = weather_table["current"]  # extract a subset and reduce size
        if weather_table != weather_table_old:
            table_timestamp = weather_table["metadata"]["readTime"]
            table_daylight = weather_table["daylight"]
            display.select_palette(table_daylight)

            print("Exterior Conditions")
            display.dew_pt_mask.fill = display.BLACK
            display.temp_mask.fill = display.BLACK
            display.humid_mask.fill = display.BLACK
            display.wind_mask.fill = display.BLACK
            display.gusts_mask.fill = display.BLACK

            table_desc = weather_table["conditionCode"]
            print(f"  {table_desc}")
            display.display_icon(table_desc, table_daylight)
            display.ext_desc.text = table_desc

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

            sunrise_ts = (datetime.fromisoformat(forecast_table["sunrise"]).timestamp()) + (
                        os.getenv("TIMEZONE_OFFSET") * 60 * 60)
            sunrise_tt = datetime.fromtimestamp(sunrise_ts).timetuple()
            sunrise_hr, ampm = am_pm(sunrise_tt.tm_hour)
            display.ext_sunrise.text = (f"rise {sunrise_hr:2d}:{sunrise_tt.tm_min:02d}{ampm[0].lower()}")

            sunset_ts = (datetime.fromisoformat(forecast_table["sunset"]).timestamp()) + (
                        os.getenv("TIMEZONE_OFFSET") * 60 * 60)
            sunset_tt = datetime.fromtimestamp(sunset_ts).timetuple()
            sunset_hr, ampm = am_pm(sunset_tt.tm_hour)
            display.ext_sunset.text = (f"set {sunset_hr:2d}:{sunset_tt.tm_min:02d}{ampm[0].lower()}")

            weather_table_old = weather_table  # to watch for changes
        else:
            print("... waiting for new weather conditions")

        print("-" * 35)
        print(f"NOTE CPU: {read_cpu_temp():.0f}°    Cooling fan state: {fan.value}")
        print("...")
        busy(SAMPLE_INTERVAL)  # Wait before checking sensor and AIO Weather
    else:
        w_topic_desc = os.getenv("WEATHER_TOPIC_DESC")
        print(f"  ... waiting for conditions from {w_topic_desc}")
        busy(10)  # Step up query rate when first starting
