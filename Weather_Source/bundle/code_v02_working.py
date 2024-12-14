# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
"""
cedargrove_weather_source_http.py WORKING VERSION

Transmits local and AIO+ weather conditions to AIO feeds for dashboards and
remote receivers, specifically in support of remote workshop corrosion
monitoring.

For the ESP32-S2 FeatherS2 with attached 3.2-inch TFT FeatherWing

https://github.com/adafruit/Adafruit_CircuitPython_AdafruitIO/blob/main/examples/adafruit_io_http/adafruit_io_weather.py
"""

import board
import microcontroller
import digitalio
import displayio
import gc
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

from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect
from adafruit_display_shapes.roundrect import RoundRect
from adafruit_display_shapes.triangle import Triangle

# import adafruit_ili9341  # 2.4" TFT FeatherWing
import adafruit_hx8357  # 3.5" TFT FeatherWing
import adafruit_am2320  # I2C temperature/humidity sensor; indoor
# import adafruit_sht31d  # I2C temperature/humidity sensor; indoor/outdoor
import pwmio

# Temperature Converter Helpers
from cedargrove_temperaturetools.unit_converters import celsius_to_fahrenheit
from cedargrove_temperaturetools.dew_point import dew_point as dew_point_calc

"""Operating Mode Parameters
XMIT_WEATHER: True to read AIO+ Weather conditions and send to AIO feeds
              False to get conditions and display locally
XMIT_SENSOR:  True to read local sensor data and send to AIO feeds
              False to read sensor data and display locally
"""
XMIT_WEATHER = False
XMIT_SENSOR = False
SAMPLE_INTERVAL = 240  # Check sensor and AIO Weather (seconds)

# TFT Display Parameters
BRIGHTNESS = 0.50
ROTATION = 180

# Cooling fan threshold
FAN_ON_TRESHOLD_F = 100  # Degrees Farenheit

# fmt: off
# A couple of day/month lookup tables
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", ]
# fmt: on

## Instantiate Local Peripherals
"""# Instantiate the 2.4" TFT FeatherWing Display
displayio.release_displays()  # Release display resources
display_bus = displayio.FourWire(
    board.SPI(), command=board.D10, chip_select=board.D9, reset=None
)
display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)"""

# Instantiate the 3.5" TFT FeatherWing Display
displayio.release_displays()  # Release display resources
display_bus = displayio.FourWire(
    board.SPI(), command=board.D6, chip_select=board.D5, reset=None
)
display = adafruit_hx8357.HX8357(display_bus, width=480, height=320)
display.rotation = ROTATION

# The board's integral display size
WIDTH = display.width
HEIGHT = display.height

lite = pwmio.PWMOut(board.TX, frequency=500)
lite.duty_cycle = int(BRIGHTNESS * 0xFFFF)

# Split the screen
# supervisor.reset_terminal(WIDTH//2, HEIGHT)

# Load the text fonts from the fonts folder
FONT_1 = bitmap_font.load_font("/fonts/OpenSans-9.bdf")
FONT_2 = bitmap_font.load_font("/fonts/Arial-12.bdf")
FONT_3 = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
CLOCK_FONT = bitmap_font.load_font("/fonts/Anton-Regular-104.bdf")
TEST_FONT_1 = bitmap_font.load_font("/fonts/Helvetica-Bold-36.bdf")

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

# Start-up values
message = ""
corrosion_index = 0
clock_tick = False

# Define the display group
image_group = displayio.Group()

# Background Graphics; image_group[0]
bkg_image = displayio.OnDiskBitmap("/corrosion_mon_bkg.bmp")
bkg = displayio.TileGrid(bkg_image, pixel_shader=bkg_image.pixel_shader)
image_group.append(bkg)

display.root_group = image_group  # Load display

### Define display graphic, label, and value areas
# Interior Sensor Data Area Title
title_1 = Label(FONT_1, text="Interior", color=CYAN)
title_1.anchor_point = (0.5, 0.5)
title_1.anchored_position = (252, 26)
image_group.append(title_1)

# Temperature
temperature = Label(TEST_FONT_1, text=" ", color=WHITE)
temperature.x = 210
temperature.y = 50
image_group.append(temperature)

# Humidity
humidity = Label(TEST_FONT_1, text=" ", color=WHITE)
humidity.x = 210
humidity.y = 85
image_group.append(humidity)

# Dew Point
dew_point = Label(FONT_2, text=" ", color=WHITE)
dew_point.x = 210
dew_point.y = 110
image_group.append(dew_point)


# Exterior Sensor Data Area Title
title_2 = Label(FONT_1, text="Exterior", color=CYAN)
title_2.anchor_point = (0.5, 0.5)
title_2.anchored_position = (410, 26)
image_group.append(title_2)

# Exterior Temperature
ext_temp = Label(TEST_FONT_1, text=" ", color=WHITE)
ext_temp.x = 368
ext_temp.y = 50
image_group.append(ext_temp)

# Exterior Humidity
ext_humid = Label(TEST_FONT_1, text=" ", color=WHITE)
ext_humid.x = 368
ext_humid.y = 85
image_group.append(ext_humid)

# Exterior Dew Point
ext_dew = Label(FONT_2, text=" ", color=WHITE)
ext_dew.x = 368
ext_dew.y = 110
image_group.append(ext_dew)


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


pcb_temp.text = f"{gc.mem_free()/10**6:.3f} Mb"

"""# Instantiate cooling fan control (D5)
fan = digitalio.DigitalInOut(board.D5)  # D4 Stemma 3-pin connector
fan.direction = digitalio.Direction.OUTPUT
fan.value = False  # Initialize with fan off"""

# Instantiate the Red LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

"""# Initialize the NeoPixel
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=BRIGHTNESS)
pixel[0] = 0xFF00FF  # Initializing (purple)"""

"""# Instantiate the local corrosion sensor
# corrosion_sensor = adafruit_sht31d.SHT31D(board.I2C())  # outdoor sensor
corrosion_sensor = adafruit_am2320.AM2320(board.I2C())  # indoor sensor
corrosion_sensor.heater = False  # turn heater OFF"""


def read_local_sensor():
    """Update the temperature and humidity with current values,
    calculate dew point and corrosion index"""
    #pixel[0] = 0xFFFF00  # Busy (yellow)
    """busy(3)  # Wait to read temperature value
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
        humid_pct = round(humid_pct, 1)"""

    temp_c = 0
    temp_f = 32
    humid_pct = 44

    # Calculate dew point values
    if None in (temp_c, humid_pct):
        dew_c = None
        dew_f = None
    else:
        dew_c, _ = dew_point_calc(temp_c, humid_pct)
        dew_f = round(celsius_to_fahrenheit(dew_c), 1)
    #pixel[0] = 0x00FF00  # Success (green)

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
            #corrosion_sensor.heater = False  # turn heater OFF
        else:
            corrosion_index = 0  # NORMAL
            #corrosion_sensor.heater = False  # turn heater OFF
    return temp_f, humid_pct, dew_f, corrosion_index


def read_cpu_temp():
    """Read the ESP32-S3 internal CPU temperature sensor and turn on
    fan if threshold is exceeded.
    Nominal operating range is -40C to 85C (-40F to 185F)."""
    cpu_temp_f = celsius_to_fahrenheit(microcontroller.cpu.temperature)
    """if cpu_temp_f > FAN_ON_TRESHOLD_F:  # Turn on cooling fan if needed
        fan.value = True
    else:
        fan.value = False"""
    return cpu_temp_f


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
    #pixel[0] = 0xFFFF00  # Busy (yellow)
    if value is not None:
        if xmit:
            try:
                while io.get_remaining_throttle_limit() <= 10:
                    time.sleep(1)  # Wait until throttle limit increases
                io.send_data(feed, value)
                #pixel[0] = 0x00FF00  # Success (green)
                print(f"SEND '{value}' -> {feed}")
            except Exception as aio_publish_error:
                #pixel[0] = 0xFF0000  # Error (red)
                print(f"FAIL: '{value}' -> {feed}")
                print(f"  {str(aio_publish_error)}")
                print("  MCU will soft reset in 30 seconds.")
                busy(30)
                supervisor.reload()  # soft reset: keeps the terminal session alive
        else:
            print(f"DISP '{value}' {feed}")
            #pixel[0] = 0x00FF00  # Success (green)
    else:
        print(f"FAIL: '{value}' for {feed}")


def busy(delay):
    """An alternative 'time.sleep' function that blinks the LED once per second.
    Time display is updated from localtime each second. A blocking method.
    :param float delay: The time delay in seconds. No default."""
    global clock_tick
    # neo_color = pixel[0]
    for blinks in range(int(round(delay, 0))):
        start = time.monotonic()
        if clock_tick:
            clock_tick_mask.fill = RED
            led.value = True
            # pixel[0] = 0x808080
        else:
            clock_tick_mask.fill = None
            led.value = False
            # pixel[0] = neo_color
        clock_tick = not clock_tick

        if time.localtime().tm_hour > 12:
            hour = time.localtime().tm_hour - 12
        else:
            hour = time.localtime().tm_hour
        if hour == 0:
            hour = 12

        local_time = f"{hour:2d}:{time.localtime().tm_min:02d}"
        clock_digits.text = local_time

        pcb_temp.text = f"{gc.mem_free()/10**6:.3f} Mb"

        delay = max((1 - (time.monotonic() - start)), 0)
        time.sleep(delay)


def update_local_time():
    #pixel[0] = 0xFFFF00  # Busy (yellow)
    clock_icon_mask.fill = None
    wifi_icon_mask.fill = None
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
    clock_digits.text = local_time

    wday = time.localtime().tm_wday
    month = time.localtime().tm_mon
    day = time.localtime().tm_mday
    year = time.localtime().tm_year
    clock_day_mon_yr.text = f"{WEEKDAY[wday]}  {MONTH[month - 1]} {day:02d}, {year:04d}"
    print(clock_day_mon_yr.text)
    print(
        f"Time: {local_time} {WEEKDAY[wday]}  {MONTH[month - 1]} {day:02d}, {year:04d}"
    )
    #pixel[0] = 0x00FFFF  # Normal (green)
    clock_icon_mask.fill = LCARS_LT_BLU
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


# Connect to Wi-Fi
try:
    # Connect to Wi-Fi access point
    print(f"Connect to {os.getenv('CIRCUITPY_WIFI_SSID')}")
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD")
    )
    #pixel[0] = 0x00FF00  # Success (green)
    print("  CONNECTED to WiFi")
except Exception as wifi_access_error:
    #pixel[0] = 0xFF0000  # Error (red)
    print(f"  FAIL: WiFi connect \n    Error: {wifi_access_error}")
    print("    MCU will soft reset in 30 seconds.")
    busy(30)
    supervisor.reload()  # soft reset: keeps the terminal session alive

# Initialize the weather_table and history variables
weather_table = None
weather_table_old = None

# Create an instance of the Adafruit IO HTTP client
# https://docs.circuitpython.org/projects/adafruitio/en/stable/api.html
#pixel[0] = 0xFFFF00  # Busy (yellow)
print("Connecting to the AIO HTTP service")
# Initialize a socket pool and requests session
try:
    pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())
    io = IO_HTTP(os.getenv("AIO_USERNAME"), os.getenv("AIO_KEY"), requests)
except Exception as aio_client_error:
    #pixel[0] = 0xFF0000  # Error (red)
    print(f"  FAIL: AIO HTTP client connect \n    Error: {aio_client_error}")
    print("    MCU will soft reset in 30 seconds.")
    busy(30)
    supervisor.reload()  # soft reset: keeps the terminal session alive
#pixel[0] = 0x00FFFF  # Normal (green)

### PRIMARY LOOP ###
while True:
    print("=" * 35)
    update_local_time()
    print(
        f"Throttle Remain/Limit: {io.get_remaining_throttle_limit()}/{io.get_throttle_limit()}"
    )
    print("-" * 35)

    sensor_icon_mask.fill = None
    # Read the local temperature and humidity sensor
    sens_temp, sens_humid, sens_dew_pt, sens_index = read_local_sensor()
    #sens_heat = corrosion_sensor.heater
    sens_heat = False

    #pcb_temp.text = f"{read_pcb_temperature():.1f}°"
    temperature.text = f"{sens_temp:.1f}°"
    humidity.text = f"{sens_humid:.0f}%"
    dew_point.text = f"{sens_dew_pt:.1f}° Dew"

    publish_to_aio(
                int(round(time.monotonic() / 60, 0)),
                "system-watchdog",
                xmit=XMIT_SENSOR,
            )

    # Publish local sensor data
    wifi_icon_mask.fill = None
    publish_to_aio(sens_temp, "shop.int-temperature", xmit=XMIT_SENSOR)
    publish_to_aio(sens_humid, "shop.int-humidity", xmit=XMIT_SENSOR)
    publish_to_aio(sens_dew_pt, "shop.int-dewpoint", xmit=XMIT_SENSOR)
    publish_to_aio(sens_index, "shop.int-corrosion-index", xmit=XMIT_SENSOR)
    publish_to_aio(str(sens_heat), "shop.int-sensor-heater-on", xmit=XMIT_SENSOR)
    publish_to_aio(f"{read_cpu_temp():.2f}", "shop.int-pcb-temperature", xmit=XMIT_SENSOR)

     # Display the corrosion status. Default is no corrosion potential (0 = GREEN).
    if sens_index == 0:
        status_icon.fill = LT_GRN
        status.color = None
        alert("NORMAL")
        heater_icon_mask.fill = LCARS_LT_BLU
        sensor_icon_mask.fill = LCARS_LT_BLU
    elif sens_index == 1:
        status_icon.fill = YELLOW
        status.color = RED
        alert("CORROSION WARNING")
        heater_icon_mask.fill = LCARS_LT_BLU
        sensor_icon_mask.fill = LCARS_LT_BLU
    elif sens_index == 2:
        status_icon.fill = RED
        status.color = BLACK
        alert("CORROSION ALERT")
        heater_icon_mask.fill = None
        sensor_icon_mask.fill = None

    wifi_icon_mask.fill = LCARS_LT_BLU
    print("-" * 35)

    # Receive and update the conditions from AIO+ Weather
    try:
        #pixel[0] = 0xFFFF00  # AIO+ Weather fetch in progress (yellow)
        while io.get_remaining_throttle_limit() <= 2:
            time.sleep(1)  # Wait until throttle limit increases
        weather_table = io.receive_weather(os.getenv("WEATHER_TOPIC_KEY"))
        weather_table = weather_table['current']  # extract a subset
        # print(weather_table)  # This is a very large json table
        # print("... weather table received ...")
        #pixel[0] = 0x00FF00  # Success (green)
    except Exception as receive_weather_error:
        #pixel[0] = 0xFF0000  # Error (red)
        print(f"FAIL: receive weather from AIO+ \n  {str(receive_weather_error)}")
        print("  MCU will soft reset in 30 seconds.")
        busy(30)
        supervisor.reload()  # soft reset: keeps the terminal session alive

    if weather_table:
        if weather_table != weather_table_old:
            table_desc = weather_table["conditionCode"]
            table_temp = (
                f"{celsius_to_fahrenheit(weather_table['temperature']):.1f}"
            )
            table_humid = f"{weather_table['humidity'] * 100:.1f}"
            table_dew_point = f"{weather_table['temperatureDewPoint']:.1f}"
            table_wind_speed = f"{weather_table['windSpeed'] * 0.6214:.1f}"
            table_wind_dir = wind_direction(weather_table["windDirection"])
            table_wind_gusts = f"{weather_table['windGust'] * 0.6214:.1f}"
            table_timestamp = weather_table["metadata"]["readTime"]
            table_daylight = weather_table["daylight"]

            ext_temp.text = f"{table_temp}°"
            ext_humid.text = f"{table_humid[:-2]}%"
            ext_dew.text = f"{celsius_to_fahrenheit(float(table_dew_point)):.1f}° Dew"

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
        #print(f"NOTE Cooling fan state: {fan.value}")
        print("...")
        busy(SAMPLE_INTERVAL)  # Wait before checking sensor and AIO Weather
    else:
        w_topic_desc = os.getenv("WEATHER_TOPIC_DESC")
        print(f"  ... waiting for conditions from {w_topic_desc}")
        busy(10)  # Step up query rate when first starting

