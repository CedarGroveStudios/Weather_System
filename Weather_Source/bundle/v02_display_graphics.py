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
import displayio
import gc
import time
import pwmio
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect
from adafruit_display_shapes.roundrect import RoundRect
from adafruit_display_shapes.triangle import Triangle


# fmt: off
# A couple of day/month lookup tables
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", ]

# Default colors
BLACK        = 0x000000
GRAY         = 0x444455
WHITE        = 0xFFFFFF
RED          = 0xFF0000
PINK         = 0XEF5CA4
ORANGE       = 0xFF8811
YELLOW       = 0xFFFF00
GREEN        = 0x00FF00
LT_GRN       = 0x00BB00
CYAN         = 0x00FFFF
BLUE         = 0x0000FF
LT_BLUE      = 0x000044
LCARS_LT_BLU = 0x07A2FF
VIOLET       = 0x9900FF
DK_VIO       = 0x110022
WIND         = 0x00e7ce
GUSTS        = 0xfd614a
# fmt: on


class Display:
    """  """

    def __init__(self, tft="3.5-inch", rotation=180, brightness=0.50):

        self._backlite = pwmio.PWMOut(board.TX, frequency=500)
        self._backlite.duty_cycle = 0

        self._brightness = brightness
        self._rotation = rotation

        if "2.4" in tft:
            # Instantiate the 2.4" TFT FeatherWing Display
            import adafruit_ili9341  # 2.4" TFT FeatherWing
            displayio.release_displays()  # Release display resources
            display_bus = displayio.FourWire(
                board.SPI(), command=board.D10, chip_select=board.D9, reset=None
            )
            self._display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)
        else:
            # Instantiate the 3.5" TFT FeatherWing Display
            import adafruit_hx8357  # 3.5" TFT FeatherWing
            displayio.release_displays()  # Release display resources
            display_bus = displayio.FourWire(
                board.SPI(), command=board.D6, chip_select=board.D5, reset=None
            )
            self._display = adafruit_hx8357.HX8357(display_bus, width=480, height=320)
        self._display.rotation = self._rotation

        self.width = self._display.width
        self.height = self._display.height
        
        from font_orbitron_bold_webfont_14 import FONT as ORBITRON_BOLD_14
        from font_orbitron_bold_webfont_18 import FONT as ORBITRON_BOLD_18
        from font_orbitron_bold_webfont_24 import FONT as ORBITRON_BOLD_24
        from font_orbitron_bold_webfont_48 import FONT as ORBITRON_BOLD_48
        from font_orbitron_light_webfont_12 import FONT as ORBITRON_LIGHT_12

        # Define the display group
        image_group = displayio.Group()

        # Background Image; image_group[0]
        bkg_image = displayio.OnDiskBitmap("/LCARS_Weather_v025_480x320.bmp")
        bkg = displayio.TileGrid(bkg_image, pixel_shader=bkg_image.pixel_shader)
        image_group.append(bkg)

        self._display.root_group = image_group  # Load display

        ### Define display graphic, label, and mask areas
        
        ## Define masks
        # Clock Activity Icon Mask
        self.clock_tick_mask = RoundRect(458, 299, 10, 10, 1, fill=VIOLET, outline=None, stroke=0)
        image_group.append(self.clock_tick_mask)

        # Temp/Humid Sensor Icon Mask
        self.sensor_icon_mask = Rect(370, 20, 20, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        image_group.append(self.sensor_icon_mask)

        # Sensor Heater Icon Mask
        self.heater_icon_mask = Rect(345, 20, 25, 30, fill=LCARS_LT_BLU, outline=None, stroke=0)
        image_group.append(self.heater_icon_mask)

        # Clock Icon Mask
        self.clock_icon_mask = Rect(405, 20, 50, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        image_group.append(self.clock_icon_mask)

        # SD Icon Mask
        self.sd_icon_mask = Rect(380, 230, 40, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        image_group.append(self.sd_icon_mask)

        # Network Icon Mask
        self.wifi_icon_mask = Rect(420, 230, 40, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        image_group.append(self.wifi_icon_mask)
        
        # Data Status Masks
        self.temp_mask = Rect(295, 83, 20, 18, fill=None, outline=None, stroke=0)
        image_group.append(self.temp_mask)
        self.humid_mask = Rect(295, 105, 20, 18, fill=None, outline=None, stroke=0)
        image_group.append(self.humid_mask)
        self.dew_pt_mask = Rect(295, 127, 20, 18, fill=None, outline=None, stroke=0)
        image_group.append(self.dew_pt_mask)
        self.wind_mask = Rect(295, 172, 20, 18, fill=None, outline=None, stroke=0)
        image_group.append(self.wind_mask)
        self.gusts_mask = Rect(295, 194, 20, 18, fill=None, outline=None, stroke=0)
        image_group.append(self.gusts_mask)
        
        # Corrosion Status Icon and Text
        self.status_icon = Triangle(95, 155, 135, 215, 55, 215, fill=LCARS_LT_BLU, outline=None)
        image_group.append(self.status_icon)
        
        self.status = Label(ORBITRON_LIGHT_12, text="status", color=WHITE)
        self.status.anchor_point = (0.5, 0.5)
        self.status.anchored_position = (95, 200)
        image_group.append(self.status)
        
        ## Define text labels
        # Temperature
        self.temperature = Label(ORBITRON_BOLD_24, text=" ", color=WHITE)
        self.temperature.anchor_point = (1.0, 0.5)
        self.temperature.anchored_position = (120, 90)
        image_group.append(self.temperature)

        # Humidity
        self.humidity = Label(ORBITRON_BOLD_18, text=" ", color=CYAN)
        self.humidity.anchor_point = (1.0, 0.5)
        self.humidity.anchored_position = (120, 115)
        image_group.append(self.humidity)

        # Dew Point
        self.dew_point = Label(ORBITRON_BOLD_18, text=" ", color=PINK)
        self.dew_point.anchor_point = (1.0, 0.5)
        self.dew_point.anchored_position = (120, 137)
        image_group.append(self.dew_point)

        # Exterior Temperature
        self.ext_temp = Label(ORBITRON_BOLD_24, text=" ", color=WHITE)
        self.ext_temp.anchor_point = (1.0, 0.5)
        self.ext_temp.anchored_position = (210, 90)
        image_group.append(self.ext_temp)

        # Exterior Humidity
        self.ext_humid = Label(ORBITRON_BOLD_18, text=" ", color=CYAN)
        self.ext_humid.anchor_point = (1.0, 0.5)
        self.ext_humid.anchored_position = (210, 115)
        image_group.append(self.ext_humid)

        # Exterior Dew Point
        self.ext_dew = Label(ORBITRON_BOLD_18, text=" ", color=PINK)
        self.ext_dew.anchor_point = (1.0, 0.5)
        self.ext_dew.anchored_position = (210, 137)
        image_group.append(self.ext_dew)
        
        # Exterior Wind Speed
        self.ext_wind = Label(ORBITRON_BOLD_18, text=" ", color=WIND)
        self.ext_wind.anchor_point = (1.0, 0.5)
        self.ext_wind.anchored_position = (210, 181)
        image_group.append(self.ext_wind)
        
        # Exterior Wind Gusts
        self.ext_gusts = Label(ORBITRON_BOLD_18, text=" ", color=GUSTS)
        self.ext_gusts.anchor_point = (1.0, 0.5)
        self.ext_gusts.anchored_position = (210, 203)
        image_group.append(self.ext_gusts)

        # Exterior Description
        self.ext_desc = Label(ORBITRON_LIGHT_12, text=" ", color=WHITE)
        self.ext_desc.anchor_point = (0.5, 0.5)
        self.ext_desc.anchored_position = (95, 285)
        image_group.append(self.ext_desc)

        # Exterior Sunrise
        self.ext_sunrise = Label(ORBITRON_LIGHT_12, text=" ", color=YELLOW)
        self.ext_sunrise.x = 325
        self.ext_sunrise.y = 200
        image_group.append(self.ext_sunrise)

        # Exterior Sunset
        self.ext_sunset = Label(ORBITRON_LIGHT_12, text=" ", color=ORANGE)
        self.ext_sunset.x = 405
        self.ext_sunset.y = 200
        image_group.append(self.ext_sunset)

        # Clock Hour:Min
        self.clock_digits = Label(ORBITRON_BOLD_48, text=" ", color=WHITE)
        self.clock_digits.anchor_point = (0.5, 0.5)
        self.clock_digits.anchored_position = (390, 135)
        image_group.append(self.clock_digits)

        # Weekday, Month, Date, Year
        self.clock_day_mon_yr = Label(ORBITRON_LIGHT_12, text=" ", color=WHITE)
        self.clock_day_mon_yr.anchor_point = (0.5, 0.5)
        self.clock_day_mon_yr.anchored_position = (390, 175)
        image_group.append(self.clock_day_mon_yr)

        # Project Message Area
        self.display_message = Label(ORBITRON_BOLD_14, text=" ", color=YELLOW)
        self.display_message.anchor_point = (0.5, 0.5)
        self.display_message.anchored_position = (390, 100)
        image_group.append(self.display_message)

        # PCB Temperature
        self.pcb_temp = Label(ORBITRON_LIGHT_12, text="°", color=CYAN)
        self.pcb_temp.anchor_point = (0.5, 0.5)
        self.pcb_temp.anchored_position = (390, 303)
        image_group.append(self.pcb_temp)

        gc.collect()

        self.pcb_temp.text = f"{gc.mem_free()/10**6:.3f} Mb"

        # Set backlight to brightness after initialization
        self._backlite.duty_cycle = int(self._brightness * 0xFFFF)


    @property
    def display(self):
        return self._display

    @property
    def brightness(self):
        """The TFT display brightness."""
        return self._brightness

    @brightness.setter
    def brightness(self, brightness=1.0):
        """Set the TFT display brightness.
        :param float brightness: The display brightness.
          Defaults to full intensity (1.0)."""
        self._brightness = brightness
        self._backlite.duty_cycle = int(brightness * 0xFFFF)

    @property
    def rotation(self):
        """The TFT rotation."""
        return self._rotation

    @rotation.setter
    def rotation(self, rot=180):
        """Set the TFT display brightness.
        :param int rot: The display rotation in degrees.
          Defaults to 180."""
        self._rotation = rot
        self.display.rotation = rot


    def alert(self, text=""):
        # Place alert message in clock message area. Default is a blank message.
        msg_text = text[:20]
        if msg_text == "" or msg_text is None:
            msg_text = ""
            self.display_message.text = msg_text
        else:
            print("ALERT: " + msg_text)
            self.display_message.color = RED
            self.display_message.text = msg_text
            time.sleep(0.1)
            self.display_message.color = YELLOW
            time.sleep(0.1)
            self.display_message.color = RED
            time.sleep(0.1)
            self.display_message.color = YELLOW
            time.sleep(0.5)
            self.display_message.color = None
        return

