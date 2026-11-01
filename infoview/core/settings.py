# -*- coding: utf-8 -*-
"""
infoview.core.settings
global settings, resource paths and colors

This is the one place for the general settings. Each one is resolved here, and nowhere else,
with this precedence (highest first):

    1. environment variable IVW_*            (e.g. IVW_LAYOUT=strip ./infoView.sh restart)
    2. [general] section of the config file  (infoView.toml, see infoview/core/config.py)
    3. default below

    setting       config key   environment    default     values
    DS_LAYOUT     layout       IVW_LAYOUT     "sidebar"   "sidebar" | "strip"
    DS_LANGUAGE   language     IVW_LANGUAGE   "pt_BR"     "pt_BR" | "en" (normalized by core/i18n.py)
    DS_THEME      theme        IVW_THEME      "color"     "color" | "mono"
    DS_SCREEN     screen       IVW_SCREEN     ""          "" (display size) | "WxH", e.g. "800x480"
                                                          (at least DI_MIN_SCREEN_W x DI_MIN_SCREEN_H)
    DV_CLOCK_CHECK clock_check IVW_CLOCK_CHECK true       true | false (env: 1/0, yes/no, on/off)

Module specific settings live with the module (defaults) and in the config file sections
[newsfeed] / [weather]: infoview/modules/newsfeed/config.py, infoview/modules/weather/config.py.

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# Python library
import logging
import os

# infoView
import infoview.core.config as cfg

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < settings >---------------------------------------------------------------------------------

# general settings: (config key, environment variable, default)
DDCT_GENERAL = {"layout": ("IVW_LAYOUT", "sidebar"),
                "language": ("IVW_LANGUAGE", "pt_BR"),
                "theme": ("IVW_THEME", "color"),
                "screen": ("IVW_SCREEN", ""),
                "clock_check": ("IVW_CLOCK_CHECK", True)}

# [general] section of the config file, validated (unknown keys / wrong types logged, ignored)
DDCT_GENERAL_FILE = cfg.merge({ls_key: l_def for ls_key, (_, l_def) in DDCT_GENERAL.items()},
                              cfg.section("general"), "general")

# ---------------------------------------------------------------------------------------------
def _setting(fs_key: str) -> str:
    """
    general setting: environment variable, else config file, else default (see the docstring)

    :param fs_key (str): config key ("layout", "language", "theme", "screen", "clock_check")

    :returns (str | bool): value (an environment variable is always text)
    """
    ls_env, _ = DDCT_GENERAL[fs_key]

    return os.environ.get(ls_env, "") or DDCT_GENERAL_FILE[fs_key]

# screen layout:
#   "sidebar": clock on the left, weather column on the right, newsfeed ticker at the bottom
#   "strip":   clock on top, weather strip under it, newsfeed ticker at the bottom
DS_LAYOUT = _setting("layout")

if DS_LAYOUT not in ("sidebar", "strip"):
    M_LOG.error("invalid layout %r (expected sidebar or strip), using sidebar", DS_LAYOUT)
    DS_LAYOUT = "sidebar"

# language of the texts on screen: "pt_BR" (Português do Brasil, default) or "en" (English);
# infoview/core/i18n.py normalizes the code ("pt-BR", "pt" -> "pt_BR") and validates it
DS_LANGUAGE = _setting("language")

# color theme (validated below, with the themes):
#   "color": black background, soft blue accents, temperature colored by value (default)
#   "mono":  black, white and greys only
DS_THEME = _setting("theme")

# window size: "" = the display size (fullscreen kiosk); "WxH" (e.g. "800x480") forces a size,
# to simulate the Raspberry Pi touchscreen on a desktop (the mouse cursor is then shown)
DS_SCREEN = _setting("screen")

# smallest window the layout supports (ESP32-like 320x240)
DI_MIN_SCREEN_W = 320
DI_MIN_SCREEN_H = 240

# forced window size (DS_SCREEN parsed), None = the display size
DT_SCREEN = None

if DS_SCREEN:
    try:
        # "800x480"
        DT_SCREEN = tuple(int(x) for x in DS_SCREEN.lower().split("x"))

        # two numbers, not too small ?
        if (2 != len(DT_SCREEN)) or (DT_SCREEN[0] < DI_MIN_SCREEN_W) or (DT_SCREEN[1] < DI_MIN_SCREEN_H):
            raise ValueError

    # on error...
    except ValueError:
        M_LOG.error("invalid screen %r (expected WxH, at least %dx%d, e.g. 800x480), using the display size",
                    DS_SCREEN, DI_MIN_SCREEN_W, DI_MIN_SCREEN_H)
        DS_SCREEN, DT_SCREEN = "", None

# check whether the system clock is synchronized (NTP) before trusting it (core/timesync.py):
# false for a Pi with a hardware clock (RTC) and no network, which would otherwise show
# "setting the clock…" forever
DV_CLOCK_CHECK = _setting("clock_check")

if isinstance(DV_CLOCK_CHECK, str):
    if DV_CLOCK_CHECK.strip().lower() in ("1", "true", "yes", "on"):
        DV_CLOCK_CHECK = True

    elif DV_CLOCK_CHECK.strip().lower() in ("0", "false", "no", "off"):
        DV_CLOCK_CHECK = False

    else:
        M_LOG.error("invalid IVW_CLOCK_CHECK %r (expected 1/0, true/false, yes/no, on/off), using true", DV_CLOCK_CHECK)
        DV_CLOCK_CHECK = True

# < resource paths >---------------------------------------------------------------------------

# project root
DS_ROOT_DIR = cfg.DS_ROOT_DIR

# fonts and icons (licenses: assets/fonts/README.md)
DS_FONT_DIR = os.path.join(DS_ROOT_DIR, "assets", "fonts")
DS_ICON_DIR = os.path.join(DS_ROOT_DIR, "assets", "icons")

# font files used by the views: text (Liberation Sans: Arial metrics, SIL OFL), clock digits
# (DSEG7 Classic: 7 segments, monospaced digits, SIL OFL)
DS_FONT_TEXT = os.path.join(DS_FONT_DIR, "LiberationSans-Regular.ttf")
DS_FONT_DIGITAL = os.path.join(DS_FONT_DIR, "DSEG7Classic-Regular.ttf")

# window icon
DS_ICON_APP = os.path.join(DS_ICON_DIR, "clock-icon.png")

# < colors >-----------------------------------------------------------------------------------

# basic colors
DCLR_BLACK = (0, 0, 0)
DCLR_GREY30 = (30, 30, 30)
DCLR_GREY45 = (45, 45, 45)
DCLR_GREY69 = (69, 69, 69)
DCLR_GREY99 = (99, 99, 99)
DCLR_GREY180 = (180, 180, 180)
DCLR_WHITE = (255, 255, 255)
DCLR_RED = (170, 30, 30)

# < theme >------------------------------------------------------------------------------------

# semantic colors per theme (views use only these names, never the basic colors directly)
DDCT_THEMES = {
    "color": {"BG": DCLR_BLACK,
              "TIME": DCLR_WHITE,                  # clock digits
              "DATE": (150, 185, 220),             # date line
              "SECONDS": (70, 115, 160),           # clock seconds
              "ACCENT": (100, 160, 220),           # highlights: weather condition, news source
              "ACCENT_DIM": (45, 75, 110),         # borders / separators
              "TEXT": DCLR_GREY180,                # regular text
              "TEXT_BRIGHT": (220, 225, 232),      # emphasized text: values, news title
              "TEXT_DIM": (110, 118, 128),         # secondary text: labels, footers, links
              "BAR_BG": (22, 28, 38),              # button bar
              "BTN": (38, 50, 68),                 # button
              "BTN_PRESSED": (70, 105, 145),       # button being pressed
              "BTN_ICON": DCLR_WHITE,              # button icon
              "BTN_DISABLED": (70, 80, 95),        # disabled button icon
              "QUIT_ARMED": DCLR_RED},             # quit button waiting for confirmation
    "mono":  {"BG": DCLR_BLACK,
              "TIME": DCLR_WHITE,
              "DATE": DCLR_GREY99,
              "SECONDS": DCLR_GREY69,
              "ACCENT": DCLR_GREY180,
              "ACCENT_DIM": DCLR_GREY45,
              "TEXT": DCLR_GREY180,
              "TEXT_BRIGHT": DCLR_WHITE,
              "TEXT_DIM": DCLR_GREY99,
              "BAR_BG": DCLR_GREY30,
              "BTN": DCLR_GREY45,
              "BTN_PRESSED": DCLR_GREY99,
              "BTN_ICON": DCLR_WHITE,
              "BTN_DISABLED": DCLR_GREY69,
              "QUIT_ARMED": DCLR_RED}}

# selected theme (invalid -> "color")
if DS_THEME not in DDCT_THEMES:
    M_LOG.error("invalid theme %r (expected color or mono), using color", DS_THEME)
    DS_THEME = "color"

# semantic colors of the selected theme
DCLR_BG = DDCT_THEMES[DS_THEME]["BG"]
DCLR_TIME = DDCT_THEMES[DS_THEME]["TIME"]
DCLR_DATE = DDCT_THEMES[DS_THEME]["DATE"]
DCLR_SECONDS = DDCT_THEMES[DS_THEME]["SECONDS"]
DCLR_ACCENT = DDCT_THEMES[DS_THEME]["ACCENT"]
DCLR_ACCENT_DIM = DDCT_THEMES[DS_THEME]["ACCENT_DIM"]
DCLR_TEXT = DDCT_THEMES[DS_THEME]["TEXT"]
DCLR_TEXT_BRIGHT = DDCT_THEMES[DS_THEME]["TEXT_BRIGHT"]
DCLR_TEXT_DIM = DDCT_THEMES[DS_THEME]["TEXT_DIM"]
DCLR_BAR_BG = DDCT_THEMES[DS_THEME]["BAR_BG"]
DCLR_BTN = DDCT_THEMES[DS_THEME]["BTN"]
DCLR_BTN_PRESSED = DDCT_THEMES[DS_THEME]["BTN_PRESSED"]
DCLR_BTN_ICON = DDCT_THEMES[DS_THEME]["BTN_ICON"]
DCLR_BTN_DISABLED = DDCT_THEMES[DS_THEME]["BTN_DISABLED"]
DCLR_QUIT_ARMED = DDCT_THEMES[DS_THEME]["QUIT_ARMED"]

# temperature color stops (°C, color): cold blue -> mild near white -> warm amber -> hot orange
DLST_TEMP_STOPS = [(0., (120, 170, 255)),
                   (10., (150, 200, 250)),
                   (18., (225, 232, 240)),
                   (25., (255, 215, 140)),
                   (30., (255, 170, 90)),
                   (35., (255, 120, 90))]

# ---------------------------------------------------------------------------------------------
def temp_color(ff_celsius) -> tuple:
    """
    color for a temperature (linear between DLST_TEMP_STOPS; white in the mono theme)

    :param ff_celsius (float): temperature in °C (None: regular text color)

    :returns (tuple): RGB color
    """
    # mono theme or unknown temperature
    if ("mono" == DS_THEME) or (ff_celsius is None):
        return DCLR_TIME

    lf_t = float(ff_celsius)

    # below the first / above the last stop
    if lf_t <= DLST_TEMP_STOPS[0][0]:
        return DLST_TEMP_STOPS[0][1]

    if lf_t >= DLST_TEMP_STOPS[-1][0]:
        return DLST_TEMP_STOPS[-1][1]

    # between two stops
    for (lf_t0, lt_c0), (lf_t1, lt_c1) in zip(DLST_TEMP_STOPS, DLST_TEMP_STOPS[1:]):
        if lf_t <= lf_t1:
            lf_k = (lf_t - lf_t0) / (lf_t1 - lf_t0)
            return tuple(int(round(a + (b - a) * lf_k)) for a, b in zip(lt_c0, lt_c1))

    # not reached
    return DLST_TEMP_STOPS[-1][1]

# < the end >----------------------------------------------------------------------------------
