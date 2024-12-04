# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
"""
cedargrove_weather_source_http.py

Transmits local and AIO+ weather conditions to AIO feeds for dashboards and
remote receivers, specifically in support of remote workshop corrosion
monitoring.

For the ESP32-S3 Feather with attached 3.2-inch TFT FeatherWing

https://github.com/adafruit/Adafruit_CircuitPython_AdafruitIO/blob/main/examples/adafruit_io_http/adafruit_io_weather.py
"""

import board
import microcontroller
import digitalio
import displayio
import os
import time
import rtc
import ssl
import supervisor
import neopixel
import adafruit_connection_manager
import wifi
import adafruit_requests
from adafruit_io.adafruit_io import IO_HTTP
import adafruit_ili9341
import adafruit_am2320  # I2C temperature/humidity sensor; indoor

# import adafruit_sht31d  # I2C temperature/humidity sensor; indoor/outdoor
import pwmio

# Temperature Converter Helpers
from cedargrove_temperaturetools.unit_converters import celsius_to_fahrenheit
from cedargrove_temperaturetools.dew_point import dew_point

"""Operating Mode Parameters
XMIT_WEATHER: True to read AIO+ Weather conditions and send to AIO feeds
              False to get conditions and display locally
XMIT_SENSOR:  True to read local sensor data and send to AIO feeds
              False to read sensor data and display locally
"""
XMIT_WEATHER = True
XMIT_SENSOR = False
SAMPLE_INTERVAL = 240  # Check sensor and AIO Weather (seconds)

# TFT Display Parameters
BRIGHTNESS = 0.25
ROTATION = 270

# fmt: off
# A couple of day/month lookup tables
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", ]
# fmt: on

## Instantiate Local Peripherals
# Instantiate the TFT Display
displayio.release_displays()  # Release display resources
try:
    display_bus = displayio.FourWire(
        board.SPI(), command=board.D10, chip_select=board.D9, reset=None
    )
    display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)
    display.rotation = ROTATION
    lite = pwmio.PWMOut(board.TX, frequency=500)
    lite.duty_cycle = int(BRIGHTNESS * 0xFFFF)
except Exception as display_error:
    display = False
    print(f"Display not connected: {display_error}")

# Instantiate the Red LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

# Initialize the NeoPixel
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=BRIGHTNESS)
pixel[0] = 0xFF00FF  # Initializing (purple)

# Instantiate the local corrosion sensor
# corrosion_sensor = adafruit_sht31d.SHT31D(board.I2C())  # outdoor sensor
corrosion_sensor = adafruit_am2320.AM2320(board.I2C())  # indoor sensor
corrosion_sensor.heater = False  # turn heater OFF


def read_local_sensor():
    """Update the temperature and humidity with current values,
    calculate dew point and corrosion index"""
    pixel[0] = 0xFFFF00  # Busy (yellow)
    busy(3)  # Wait to read temperature value
    temp_c = corrosion_sensor.temperature
    if temp_c is not None:
        temp_c = min(max(temp_c, -40), 125)  # constrain value
        temp_c = round(temp_c, 1)  # Celsius
        temp_f = round(celsius_to_fahrenheit(temp_c), 1)  # Fahrenheit
    else:
        temp_f = None
    busy(3)  # Wait to read humidity value
    humid_pct = corrosion_sensor.relative_humidity
    if humid_pct is not None:
        humid_pct = min(max(humid_pct, 0), 100)  # constrain value
        humid_pct = round(humid_pct, 1)

    # Calculate dew point values
    if None in (temp_c, humid_pct):
        dew_c = None
        dew_f = None
    else:
        dew_c, _ = dew_point(temp_c, humid_pct)
        dew_f = round(celsius_to_fahrenheit(dew_c), 1)
    pixel[0] = 0x00FF00  # Success (green)

    """Calculate corrosion index value; keep former value if temp or
    dewpoint = None. Turn on sensor heater when index = 2 (ALERT);
    heater turns off for other corrosion index conditions."""
    if None in (temp_c, dew_c):
        return
    else:
        if (temp_c <= dew_c + 2) or humid_pct >= 80:
            corrosion_index = 2  # CORROSION ALERT
            corrosion_sensor.heater = True  # turn heater ON
        elif temp_c <= dew_c + 5:
            corrosion_index = 1  # CORROSION WARNING
            corrosion_sensor.heater = False  # turn heater OFF
        else:
            corrosion_index = 0  # NORMAL
            corrosion_sensor.heater = False  # turn heater OFF
    return temp_f, humid_pct, dew_f, corrosion_index


# Function to print CPU temperature (ESP32-S3 has built-in temperature sensor)
def cpu_temp():
    """Read the ESP32-S3 internal CPU temperature sensor.
    Nominal operating range is -40C to 85C (-40F to 185F)."""
    return celsius_to_fahrenheit(microcontroller.cpu.temperature)


def display_brightness(brightness=1.0):
    """Set the TFT display brightness.
    :param float brightness: The display brightness.
      Defaults to full intensity (1.0)."""
    lite.duty_cycle = int(brightness * 0xFFFF)


def wind_direction(heading):
    """Provide a one or two character string representation of a compass
    heading value. Returns '--' if heading is None.
    :param int heading: The compass heading. No default."""
    if heading is None:
        return "--"
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][
        int(((heading + 22.5) % 360) / 45)
    ]


def publish_to_aio(value, feed, xmit=True):
    """Publish a value to an AIO feed, while monitoring checking the throttle
    transaction rate. A blocking method.
    :param union(int, float, str) value: The value to publish.
    :param str feed: The name of the AIO feed.
    :param bool xmit: True to enable transmitting to AIO. False for local display only.
    """
    pixel[0] = 0xFFFF00  # Busy (yellow)
    if value is not None:
        if xmit:
            try:
                while io.get_remaining_throttle_limit() <= 10:
                    time.sleep(1)  # Wait until throttle limit increases
                io.send_data(feed, value)
                pixel[0] = 0x00FF00  # Success (green)
                print(f"SEND '{value}' -> {feed}")
            except Exception as aio_publish_error:
                pixel[0] = 0xFF0000  # Error (red)
                print(f"FAIL: '{value}' -> {feed}")
                print(f"  {str(aio_publish_error)}")
                print("  MCU will soft reset in 30 seconds.")
                busy(30)
                supervisor.reload()  # soft reset: keeps the terminal session alive
        else:
            print(f"DISP '{value}' {feed}")
            pixel[0] = 0x00FF00  # Success (green)
    else:
        print(f"FAIL: '{value}' for {feed}")


def busy(delay):
    """An alternative 'time.sleep' function that blinks the LED once per second.
    A blocking method.
    :param float delay: The time delay in seconds. No default."""
    # neo_color = pixel[0]
    for blinks in range(int(round(delay, 0))):
        led.value = True
        # pixel[0] = 0x808080
        time.sleep(0.05)
        led.value = False
        # pixel[0] = neo_color
        time.sleep(0.95)


def update_local_time():
    pixel[0] = 0xFFFF00  # Busy (yellow)
    try:
        rtc.RTC().datetime = time.struct_time(io.receive_time(os.getenv("TIMEZONE")))
    except Exception as time_error:
        print(f"  FAIL: Reverting to local time: {time_error}")

    local_time = f"{time.localtime().tm_hour:2d}:{time.localtime().tm_min:02d}"
    wday = time.localtime().tm_wday
    month = time.localtime().tm_mon
    day = time.localtime().tm_mday
    year = time.localtime().tm_year
    print(
        f"Time: {local_time} {WEEKDAY[wday]}  {MONTH[month - 1]} {day:02d}, {year:04d}"
    )
    pixel[0] = 0x00FFFF  # Normal (green)


# Connect to Wi-Fi
try:
    # Connect to Wi-Fi access point
    print(f"Connect to {os.getenv('CIRCUITPY_WIFI_SSID')}")
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD")
    )
    pixel[0] = 0x00FF00  # Success (green)
    print("  CONNECTED to WiFi")
except Exception as wifi_access_error:
    pixel[0] = 0xFF0000  # Error (red)
    print(f"  FAIL: WiFi connect \n    Error: {wifi_access_error}")
    print("    MCU will soft reset in 30 seconds.")
    busy(30)
    supervisor.reload()  # soft reset: keeps the terminal session alive

# Initialize the weather_table and history variables
weather_table = None
weather_table_old = None

# Create an instance of the Adafruit IO HTTP client
# https://docs.circuitpython.org/projects/adafruitio/en/stable/api.html
pixel[0] = 0xFFFF00  # Busy (yellow)
print("Connecting to the AIO HTTP service")
# Initialize a socket pool and requests session
try:
    pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())
    io = IO_HTTP(os.getenv("AIO_USERNAME"), os.getenv("AIO_KEY"), requests)
except Exception as aio_client_error:
    pixel[0] = 0xFF0000  # Error (red)
    print(f"  FAIL: AIO HTTP client connect \n    Error: {aio_client_error}")
    print("    MCU will soft reset in 30 seconds.")
    busy(30)
    supervisor.reload()  # soft reset: keeps the terminal session alive
pixel[0] = 0x00FFFF  # Normal (green)

### PRIMARY LOOP ###
while True:
    print("=" * 35)
    update_local_time()
    print(
        f"Throttle Remain/Limit: {io.get_remaining_throttle_limit()}/{io.get_throttle_limit()}"
    )
    print("-" * 35)

    # Read the local temperature and humidity sensor
    sens_temp, sens_humid, sens_dew_pt, sens_index = read_local_sensor()
    sens_heat = corrosion_sensor.heater

    # Publish local sensor data
    publish_to_aio(sens_temp, "shop.int-temperature", xmit=XMIT_SENSOR)
    publish_to_aio(sens_humid, "shop.int-humidity", xmit=XMIT_SENSOR)
    publish_to_aio(sens_dew_pt, "shop.int-dewpoint", xmit=XMIT_SENSOR)
    publish_to_aio(sens_index, "shop.int-corrosion-index", xmit=XMIT_SENSOR)
    publish_to_aio(str(sens_heat), "shop.int-sensor-heater-on", xmit=XMIT_SENSOR)
    publish_to_aio(f"{cpu_temp():.2f}", "shop.int-pcb-temperature", xmit=XMIT_SENSOR)
    print("-" * 35)

    # Receive and update the conditions from AIO+ Weather
    try:
        pixel[0] = 0xFFFF00  # AIO+ Weather fetch in progress (yellow)
        while io.get_remaining_throttle_limit() <= 2:
            time.sleep(1)  # Wait until throttle limit increases
        weather_table = io.receive_weather(os.getenv("WEATHER_TOPIC_KEY"))
        # print(weather_table)  # This is a very large json table
        pixel[0] = 0x00FF00  # Success (green)
    except Exception as receive_weather_error:
        pixel[0] = 0xFF0000  # Error (red)
        print(f"FAIL: receive weather from AIO+ \n  {str(receive_weather_error)}")
        print("  MCU will soft reset in 30 seconds.")
        busy(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive

    if weather_table:
        if weather_table != weather_table_old:
            table_desc = weather_table["current"]["conditionCode"]
            table_temp = (
                f"{celsius_to_fahrenheit(weather_table['current']['temperature']):.1f}"
            )
            table_humid = f"{weather_table['current']['humidity'] * 100:.1f}"
            table_wind_speed = f"{weather_table['current']['windSpeed'] * 0.6214:.1f}"
            table_wind_dir = wind_direction(weather_table["current"]["windDirection"])
            table_wind_gusts = f"{weather_table['current']['windGust'] * 0.6214:.1f}"
            table_timestamp = weather_table["current"]["metadata"]["readTime"]
            table_daylight = weather_table["current"]["daylight"]

            # Publish table data
            publish_to_aio(
                int(round(time.monotonic() / 60, 0)),
                "system-watchdog",
                xmit=XMIT_WEATHER,
            )
            publish_to_aio(table_desc, "weather-description", xmit=XMIT_WEATHER)
            publish_to_aio(table_humid, "weather-humidity", xmit=XMIT_WEATHER)
            publish_to_aio(table_temp, "weather-temperature", xmit=XMIT_WEATHER)
            publish_to_aio(table_wind_dir, "weather-winddirection", xmit=XMIT_WEATHER)
            publish_to_aio(table_wind_gusts, "weather-windgusts", xmit=XMIT_WEATHER)
            publish_to_aio(table_wind_speed, "weather-windspeed", xmit=XMIT_WEATHER)
            publish_to_aio(str(table_daylight), "weather-daylight", xmit=XMIT_WEATHER)

            weather_table_old = weather_table  # to watch for changes
        else:
            print("... waiting for new weather conditions")

        print("-" * 35)
        print("...")
        busy(SAMPLE_INTERVAL)  # Wait before checking sensor and AIO Weather
    else:
        w_topic_desc = os.getenv("WEATHER_TOPIC_DESC")
        print(f"  ... waiting for conditions from {w_topic_desc}")
        busy(10)  # Step up query rate when first starting