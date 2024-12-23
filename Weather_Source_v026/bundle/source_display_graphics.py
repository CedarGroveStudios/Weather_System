# SPDX-FileCopyrightText: 2024 JG for Cedar Grove Maker Studios
# SPDX-License-Identifier: MIT
"""
source_display_graphics.py

Builds the display graphics class for the Weather Source device.

For the ESP32-S2 FeatherS2 with attached 3.2-inch TFT FeatherWing
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

from weatherkit_to_weathmap_icon import kit_to_map_icon


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
        self.image_group = displayio.Group()

        # Background Image; image_group[0]
        bkg_image = displayio.OnDiskBitmap("/LCARS_Weather_v026_480x320.bmp")
        bkg = displayio.TileGrid(bkg_image, pixel_shader=bkg_image.pixel_shader)
        self.image_group.append(bkg)

        self._display.root_group = self.image_group  # Load display

        desc_icon = displayio.OnDiskBitmap("/cedar_grove_blue_120x50.bmp")
        icon = displayio.TileGrid(desc_icon, pixel_shader=desc_icon.pixel_shader, x=29, y=225)
        self.image_group.append(icon)

        ### Define display graphic, label, and mask areas

        ## Define masks
        # Heartbeat Icon Mask
        self.clock_tick_mask = RoundRect(458, 297, 10, 11, 1, fill=VIOLET, outline=None, stroke=0)
        self.image_group.append(self.clock_tick_mask)

        # Temp/Humid Sensor Icon Mask
        self.sensor_icon_mask = Rect(370, 20, 20, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        self.image_group.append(self.sensor_icon_mask)

        # Sensor Heater Icon Mask
        self.heater_icon_mask = Rect(345, 20, 25, 30, fill=LCARS_LT_BLU, outline=None, stroke=0)
        self.image_group.append(self.heater_icon_mask)

        # Clock Icon Mask
        self.clock_icon_mask = Rect(405, 20, 50, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        self.image_group.append(self.clock_icon_mask)

        # SD Icon Mask; Also Masks Battery and Speaker Icons
        self.sd_icon_mask = Rect(330, 225, 90, 55, fill=LCARS_LT_BLU, outline=None, stroke=0)
        self.image_group.append(self.sd_icon_mask)

        # Network Icon Mask
        self.wifi_icon_mask = Rect(420, 230, 40, 50, fill=LCARS_LT_BLU, outline=None, stroke=0)
        self.image_group.append(self.wifi_icon_mask)

        # Data Status Masks
        self.temp_mask = Rect(295, 82, 20, 18, fill=None, outline=None, stroke=0)
        self.image_group.append(self.temp_mask)
        self.humid_mask = Rect(295, 105, 20, 18, fill=None, outline=None, stroke=0)
        self.image_group.append(self.humid_mask)
        self.dew_pt_mask = Rect(295, 127, 20, 18, fill=None, outline=None, stroke=0)
        self.image_group.append(self.dew_pt_mask)
        self.wind_mask = Rect(295, 172, 20, 18, fill=None, outline=None, stroke=0)
        self.image_group.append(self.wind_mask)
        self.gusts_mask = Rect(295, 194, 20, 18, fill=None, outline=None, stroke=0)
        self.image_group.append(self.gusts_mask)

        # Corrosion Status Icon and Text
        self.status_icon = Triangle(95, 155, 130, 210, 60, 210, fill=LCARS_LT_BLU, outline=None)
        self.image_group.append(self.status_icon)

        self.status = Label(ORBITRON_LIGHT_12, text=" ", color=WHITE)
        self.status.anchor_point = (0.5, 0.5)
        self.status.anchored_position = (95, 200)
        self.image_group.append(self.status)

        ## Define text labels
        # Temperature
        self.temperature = Label(ORBITRON_BOLD_24, text=" ", color=WHITE)
        self.temperature.anchor_point = (1.0, 0.5)
        self.temperature.anchored_position = (120, 90)
        self.image_group.append(self.temperature)

        # Humidity
        self.humidity = Label(ORBITRON_BOLD_18, text=" ", color=CYAN)
        self.humidity.anchor_point = (1.0, 0.5)
        self.humidity.anchored_position = (120, 115)
        self.image_group.append(self.humidity)

        # Dew Point
        self.dew_point = Label(ORBITRON_BOLD_18, text=" ", color=PINK)
        self.dew_point.anchor_point = (1.0, 0.5)
        self.dew_point.anchored_position = (120, 137)
        self.image_group.append(self.dew_point)

        # Exterior Temperature
        self.ext_temp = Label(ORBITRON_BOLD_24, text=" ", color=WHITE)
        self.ext_temp.anchor_point = (1.0, 0.5)
        self.ext_temp.anchored_position = (210, 90)
        self.image_group.append(self.ext_temp)

        # Exterior Humidity
        self.ext_humid = Label(ORBITRON_BOLD_18, text=" ", color=CYAN)
        self.ext_humid.anchor_point = (1.0, 0.5)
        self.ext_humid.anchored_position = (210, 115)
        self.image_group.append(self.ext_humid)

        # Exterior Dew Point
        self.ext_dew = Label(ORBITRON_BOLD_18, text=" ", color=PINK)
        self.ext_dew.anchor_point = (1.0, 0.5)
        self.ext_dew.anchored_position = (210, 137)
        self.image_group.append(self.ext_dew)

        # Exterior Wind Speed
        self.ext_wind = Label(ORBITRON_BOLD_18, text=" ", color=WIND)
        self.ext_wind.anchor_point = (1.0, 0.5)
        self.ext_wind.anchored_position = (210, 181)
        self.image_group.append(self.ext_wind)

        # Exterior Wind Gusts
        self.ext_gusts = Label(ORBITRON_BOLD_18, text=" ", color=GUSTS)
        self.ext_gusts.anchor_point = (1.0, 0.5)
        self.ext_gusts.anchored_position = (210, 203)
        self.image_group.append(self.ext_gusts)

        # Exterior Description
        self.ext_desc = Label(ORBITRON_LIGHT_12, text=" ", color=WHITE)
        self.ext_desc.anchor_point = (0.5, 0.5)
        self.ext_desc.anchored_position = (95, 285)
        self.image_group.append(self.ext_desc)

        # Exterior Sunrise
        self.ext_sunrise = Label(ORBITRON_LIGHT_12, text=" ", color=YELLOW)
        self.ext_sunrise.x = 325
        self.ext_sunrise.y = 200
        self.image_group.append(self.ext_sunrise)

        # Exterior Sunset
        self.ext_sunset = Label(ORBITRON_LIGHT_12, text=" ", color=ORANGE)
        self.ext_sunset.x = 405
        self.ext_sunset.y = 200
        self.image_group.append(self.ext_sunset)

        # Clock Hour:Min
        self.clock_digits = Label(ORBITRON_BOLD_48, text=" ", color=WHITE)
        self.clock_digits.anchor_point = (0.5, 0.5)
        self.clock_digits.anchored_position = (390, 135)
        self.image_group.append(self.clock_digits)

        # Weekday, Month, Date, Year
        self.clock_day_mon_yr = Label(ORBITRON_LIGHT_12, text=" ", color=WHITE)
        self.clock_day_mon_yr.anchor_point = (0.5, 0.5)
        self.clock_day_mon_yr.anchored_position = (390, 175)
        self.image_group.append(self.clock_day_mon_yr)

        # Project Message Area
        self.display_message = Label(ORBITRON_BOLD_14, text=" ", color=YELLOW)
        self.display_message.anchor_point = (0.5, 0.5)
        self.display_message.anchored_position = (390, 100)
        self.image_group.append(self.display_message)

        # PCB Temperature
        self.pcb_temp = Label(ORBITRON_LIGHT_12, text="°", color=CYAN)
        self.pcb_temp.anchor_point = (0.5, 0.5)
        self.pcb_temp.anchored_position = (390, 302)
        self.image_group.append(self.pcb_temp)

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


    def display_icon(self, desc="Clear", daylight=True):
        if isinstance(daylight, str):
            if daylight == "True":
                daylight = True
            else:
                daylight = False
        if daylight:
            icon_suffix = "d"
        else:
            icon_suffix = "n"
        icon_file = f"/icons/{kit_to_map_icon[desc][1]}{icon_suffix}_120x50.bmp"
        print(f"Icon filename: {icon_file}")

        self.image_group.pop(1)
        icon_image = displayio.OnDiskBitmap(icon_file)
        icon_bg = displayio.TileGrid(icon_image, pixel_shader=icon_image.pixel_shader, x=29, y=225)
        self.image_group.insert(1, icon_bg)


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

