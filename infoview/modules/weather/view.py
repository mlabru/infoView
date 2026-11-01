# -*- coding: utf-8 -*-
"""
infoView 1.0
Weather / View

weather view, two styles: "strip" (under the clock: icon | big temperature + today's min / max |
condition, feels like, wind, rain, humidity, place) or "sidebar" (column beside the clock: icon +
temperature, condition, label / value rows, place). Data comes from SWeatherFetcher (WEATHER_DATA, emitted in the fetcher thread:
the callback only keeps a reference, rendering happens in update(), in the main thread).
Icons are drawn with primitives only (no font glyphs / images), as in infoview/ui/controls.py.

weather data by Open-Meteo.com (CC BY 4.0): attribution shown on the strip.

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import math
import time

# pygame
import pygame as pg

# infoView
import infoview.core.state as gd
import infoview.core.settings as df
import infoview.core.i18n as i18n
import infoview.ui.fonts as vu

# weather
import infoview.modules.weather.config as wd

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# default surface size
DI_SURFACE_HEIGHT = 96
DI_SURFACE_WIDTH = 800

# check whether the data got old every (sec)
DF_STALE_CHECK = 30.

# icon colors
DCLR_SUN = (235, 190, 60)
DCLR_MOON = (205, 205, 215)
DCLR_CLOUD = (175, 175, 180)
DCLR_CLOUD_DARK = (120, 120, 128)
DCLR_RAIN = (90, 145, 235)
DCLR_SNOW = (235, 235, 245)
DCLR_BOLT = (245, 210, 60)

# WMO weather code -> icon (labels: "wmo.<code>" in infoview/core/i18n.py)
DDCT_WMO = {0: "clear", 1: "partly", 2: "partly", 3: "cloudy", 45: "fog", 48: "fog",
            51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "drizzle", 57: "drizzle",
            61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
            71: "snow", 73: "snow", 75: "snow", 77: "snow",
            80: "rain", 81: "rain", 82: "rain", 85: "snow", 86: "snow",
            95: "thunder", 96: "thunder", 99: "thunder"}

# wind direction (degrees, "from") -> compass point: 8 points, "wt.compass" in infoview/core/i18n.py

# layout styles
DLST_STYLES = ["strip", "sidebar"]

# sidebar rows: (label text key in infoview/core/i18n.py, value key in _texts())
DLST_SIDEBAR_ROWS = [("wt.feels", "feels"),
                     ("wt.wind", "wind"),
                     ("wt.gusts", "gust"),
                     ("wt.rain", "rain"),
                     ("wt.rain_prob", "rain_prob"),
                     ("wt.humidity", "humidity")]

# < SWeatherView >-----------------------------------------------------------------------------

class SWeatherView:
    """
    weather view, "strip" or "sidebar" style (see the module docstring); data from
    SWeatherFetcher (WEATHER_DATA / WEATHER_ERROR); texts never cut (font reduced to fit)
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fi_width: int = DI_SURFACE_WIDTH, fi_height: int = DI_SURFACE_HEIGHT,
                 fs_style: str = "strip"):
        """
        constructor

        :param fi_width (int): view width
        :param fi_height (int): view height (fonts and layout are fitted to it)
        :param fs_style (str): "strip" (wide, short: under the clock) or "sidebar" (narrow, tall
                               column beside the clock)
        """
        # logger
        M_LOG.info(">> constructor")

        # surface size
        self._i_width: int = fi_width
        self._i_height: int = fi_height

        # layout style
        self._s_style: str = fs_style if fs_style in DLST_STYLES else "strip"

        # view surface
        self._srf_wt = pg.Surface((fi_width, fi_height))

        # config (own copy is not needed: read only)
        self._dct_config: dict = wd.DDCT_CONFIG

        # data shown / data received (set from the fetcher thread: reference assignment only)
        self._dct_data = None
        self._dct_new = None
        # last error (code) received / drawn, shown while there's no data
        self._s_error = None
        self._s_error_drawn = None

        # data was old when last drawn ? / last time the age was checked
        self._v_stale = False
        self._tm_stale_check = 0.

        # redraw needed ?
        self._v_dirty: bool = True

        # fonts and positions for this size and style
        if "sidebar" == self._s_style:
            self._layout_sidebar()
        else:
            self._layout_strip()

        # events callback (fetcher thread)
        gd.G_EVENTS.on("WEATHER_DATA", self.on_weather_data)
        gd.G_EVENTS.on("WEATHER_ERROR", self.on_weather_error)

    # -----------------------------------------------------------------------------------------
    def _layout_strip(self):
        """
        strip: fit fonts and compute positions (icon | temperature + min/max | 4 text lines)
        """
        # font file
        self._s_font = ls_font = df.DS_FONT_TEXT

        # margin
        li_h = self._i_height
        self._i_mrg = li_mrg = max(3, li_h // 16)

        # icon: square on the left
        self._rct_icon = pg.Rect(li_mrg, li_mrg, li_h - 2 * li_mrg, li_h - 2 * li_mrg)

        # temperature (big) and min / max (under it)
        self._fnt_temp = vu.fit_font(ls_font, "-88°", li_h * 2, int(li_h * .66))
        self._fnt_minmax = vu.fit_font(ls_font, "-88° / -88°", li_h * 2, int(li_h * .26))

        # temperature column: as wide as the widest of both samples
        self._i_temp_x = self._rct_icon.right + 2 * li_mrg
        li_temp_w = max(self._fnt_temp.size("-88°")[0], self._fnt_minmax.size("-88° / -88°")[0])

        # text column: the rest (4 lines: 3 details + place / attribution)
        self._i_text_x = self._i_temp_x + li_temp_w + 3 * li_mrg
        self._i_text_w = max(10, self._i_width - self._i_text_x - li_mrg)

        # preferred (max) font sizes: details / footer
        li_line_h = (li_h - 2 * li_mrg) // 4
        self._i_line_h = li_line_h
        self._i_sz_text = vu.fit_size(ls_font, "Ag", 10 * li_h, int(li_line_h * .95))
        self._i_sz_small = vu.fit_size(ls_font, "Ag", 10 * li_h, int(li_line_h * .75))

    # -----------------------------------------------------------------------------------------
    def _layout_sidebar(self):
        """
        sidebar: fit fonts and compute positions (header: icon + temperature + min/max; condition;
        label / value rows; footer: place, attribution, data age)
        """
        # font file
        self._s_font = ls_font = df.DS_FONT_TEXT

        # size and margin
        li_w, li_h = self._i_width, self._i_height
        self._i_mrg = li_mrg = max(4, li_w // 35)

        # header: icon (square) + temperature / min-max at its right
        li_s = int(min(li_w * .4, li_h * .27))
        self._rct_icon = pg.Rect(li_mrg, li_mrg, li_s, li_s)

        self._i_temp_x = self._rct_icon.right + li_mrg
        li_temp_w = max(10, li_w - self._i_temp_x - li_mrg)
        self._fnt_temp = vu.fit_font(ls_font, "-88°", li_temp_w, int(li_s * .62))
        self._fnt_minmax = vu.fit_font(ls_font, "-88° / -88°", li_temp_w, int(li_s * .24))
        self._i_header_h = li_mrg + li_s

        # condition label (centered), under the header
        self._i_label_y = self._i_header_h + li_mrg
        li_label_h = int(li_h * .065)
        self._i_sz_text = vu.fit_size(ls_font, "Ag", 10 * li_w, li_label_h)

        # footer (up to 3 small lines: place, attribution, data age) at the bottom
        li_foot_h = int(li_h * .15)
        self._i_foot_bottom = li_h - li_mrg
        self._i_foot_line_h = li_foot_h // 3
        self._i_sz_small = vu.fit_size(ls_font, "Ag", 10 * li_w, self._i_foot_line_h)

        # label / value rows in between
        self._i_rows_y = self._i_label_y + li_label_h + li_mrg
        self._i_row_h = max(1, (self._i_foot_bottom - li_foot_h - li_mrg - self._i_rows_y) // len(DLST_SIDEBAR_ROWS))
        self._i_sz_row = vu.fit_size(ls_font, "Ag", 10 * li_w, int(self._i_row_h * .62))

        # text width (inside the left border line and margins)
        self._i_text_w = li_w - 3 * li_mrg

    # -----------------------------------------------------------------------------------------
    def _draw(self):
        """
        draw the view
        """
        # logger
        M_LOG.info(">> _draw")

        # clear
        self._srf_wt.fill(df.DCLR_BG)

        # sidebar: thin left border, separating it from the clock
        if "sidebar" == self._s_style:
            pg.draw.line(self._srf_wt, df.DCLR_ACCENT_DIM, (0, 0), (0, self._i_height), 2)

        # data
        ldct = self._dct_data

        # no data yet ?
        if not ldct:
            # message (and the error, if any)
            ls_msg = i18n.tr("wt.waiting") if not self._s_error else \
                     i18n.tr("wt.unavailable", reason=self._error_reason(self._s_error))

            # whole message, font reduced if needed
            lsrf = self._render_fit([ls_msg], self._i_sz_text, self._i_width - 2 * self._i_mrg, df.DCLR_TEXT_DIM)[0]
            self._srf_wt.blit(lsrf, lsrf.get_rect(center=(self._i_width // 2, self._i_height // 2)))

            # done
            self._v_dirty = False
            return

        # icon
        self._draw_icon(DDCT_WMO.get(ldct.get("code"), "cloudy"), ldct.get("is_day", True), self._rct_icon)

        # texts for the current data
        ldct_txt = self._texts(ldct)

        # temperature color: by value (°C), grey when the data is old
        lf_temp = ldct.get("temp")

        if (lf_temp is not None) and ("°F" == ldct.get("temp_unit")):
            lf_temp = (float(lf_temp) - 32.) * 5. / 9.

        lclr_temp = df.DCLR_TEXT_DIM if self._v_stale else df.temp_color(lf_temp)

        # style
        if "sidebar" == self._s_style:
            self._draw_sidebar(ldct_txt, lclr_temp)
        else:
            self._draw_strip(ldct_txt, lclr_temp)

        # done
        self._v_dirty = False

    # -----------------------------------------------------------------------------------------
    def _draw_sidebar(self, fdct_txt: dict, fclr_temp):
        """
        sidebar body (icon already drawn)

        :param fdct_txt (dict): texts (see _texts)
        :param fclr_temp (tuple): temperature color
        """
        # temperature (top) + min / max (bottom), right of the icon
        lsrf = self._fnt_temp.render(fdct_txt["temp"], True, fclr_temp)
        self._srf_wt.blit(lsrf, (self._i_temp_x, self._rct_icon.top))

        lsrf = self._fnt_minmax.render(fdct_txt["minmax"], True, df.DCLR_TEXT)
        self._srf_wt.blit(lsrf, (self._i_temp_x + 2, self._rct_icon.bottom - lsrf.get_height()))

        # condition (centered)
        lsrf = self._render_fit([fdct_txt["label"]], self._i_sz_text, self._i_text_w, df.DCLR_ACCENT)[0]
        self._srf_wt.blit(lsrf, lsrf.get_rect(midtop=(self._i_width // 2, self._i_label_y)))

        # label (left) / value (right) rows: one font size for all rows, so that the widest
        # label + margin + value fits
        li_left, li_right = 2 * self._i_mrg, self._i_width - self._i_mrg
        llst_rows = [(i18n.tr(ls_label_key), fdct_txt[ls_key]) for ls_label_key, ls_key in DLST_SIDEBAR_ROWS]

        li_sz = vu.fit_size_by(self._s_font,
                               lambda f: max(f.size(l)[0] + self._i_mrg + f.size(v)[0] for l, v in llst_rows),
                               li_right - li_left, self._i_sz_row)
        lfnt = vu.font(self._s_font, li_sz)

        for li_i, (ls_label, ls_value) in enumerate(llst_rows):
            # row center
            li_cy = self._i_rows_y + li_i * self._i_row_h + self._i_row_h // 2

            # value (right aligned), label (left aligned)
            lsrf = lfnt.render(ls_value, True, df.DCLR_TEXT_BRIGHT)
            self._srf_wt.blit(lsrf, lsrf.get_rect(midright=(li_right, li_cy)))

            lsrf = lfnt.render(ls_label, True, df.DCLR_TEXT_DIM)
            self._srf_wt.blit(lsrf, lsrf.get_rect(midleft=(li_left, li_cy)))

        # footer, centered, bottom aligned: place / attribution / data age (when old)
        llst_foot = [x for x in (fdct_txt["place"], fdct_txt["source"], fdct_txt["age"]) if x]
        llst_srf = self._render_fit(llst_foot, self._i_sz_small, self._i_text_w, df.DCLR_TEXT_DIM)

        li_y = self._i_foot_bottom - len(llst_srf) * self._i_foot_line_h

        for li_i, lsrf in enumerate(llst_srf):
            lrct = lsrf.get_rect(centerx=self._i_width // 2,
                                 centery=li_y + li_i * self._i_foot_line_h + self._i_foot_line_h // 2)
            self._srf_wt.blit(lsrf, lrct)

    # -----------------------------------------------------------------------------------------
    def _error_reason(self, fs_code: str) -> str:
        """
        error code (net.error_info, from the fetcher) -> short text for the screen; the details
        are in the log

        :param fs_code (str): "URLError", "LookupError" (place not found), HTTP status, or the
                              type of another error (bad JSON, API error, response too big)

        :returns (str): reason, in the current language
        """
        # network (DNS, no connection, timeout)
        if "URLError" == fs_code:
            return i18n.tr("wt.no_connection")

        # geocoding found no such place (misspelled name / wrong country_code ?)
        if "LookupError" == fs_code:
            return i18n.tr("wt.not_found", place=self._dct_config["location"].get("name", ""))

        # HTTP status
        if fs_code.isdigit():
            return i18n.tr("wt.http_error", code=fs_code)

        # anything else: the response could not be used
        return i18n.tr("wt.bad_response")

    # -----------------------------------------------------------------------------------------
    def _render_fit(self, flst_texts: list, fi_max_size: int, fi_max_w: int, fclr) -> list:
        """
        render lines with one font size that makes all of them fit fi_max_w: the preferred size,
        or a smaller one (weather texts are never cut; only if even ui.fonts.DI_MIN_FONT doesn't
        fit - tiny screens - a line is cut with "…" as a last resort)

        :param flst_texts (list): lines
        :param fi_max_size (int): preferred (max) font size
        :param fi_max_w (int): available width (px)
        :param fclr (tuple): color

        :returns (list): rendered lines (pg.Surface)
        """
        # one size for all lines
        lfnt = vu.font(self._s_font, vu.fit_size_all(self._s_font, flst_texts, fi_max_w, fi_max_size))

        # render (cut only if the min size still doesn't fit)
        return [lfnt.render(ls if lfnt.size(ls)[0] <= fi_max_w else vu.fit_text(lfnt, ls, fi_max_w), True, fclr)
                for ls in flst_texts]

    # -----------------------------------------------------------------------------------------
    def _draw_strip(self, fdct_txt: dict, fclr_temp):
        """
        strip body (icon already drawn)

        :param fdct_txt (dict): texts (see _texts)
        :param fclr_temp (tuple): temperature color
        """
        # temperature + min / max >>>

        lsrf = self._fnt_temp.render(fdct_txt["temp"], True, fclr_temp)
        self._srf_wt.blit(lsrf, (self._i_temp_x, self._i_mrg - lsrf.get_height() // 12))

        lsrf = self._fnt_minmax.render(fdct_txt["minmax"], True, df.DCLR_TEXT)
        self._srf_wt.blit(lsrf, (self._i_temp_x + 2, self._i_height - self._i_mrg - lsrf.get_height()))

        # details >>>

        # wind (+ gusts), rain today (+ probability)
        ls_wind = i18n.tr("wt.wind_inline", value=fdct_txt["wind"]) + \
                  (" · " + i18n.tr("wt.gusts_inline", value=fdct_txt["gust_num"]) if fdct_txt["gust_num"] != "--" else "")
        ls_rain = i18n.tr("wt.rain_inline", value=fdct_txt["rain"]) + \
                  (f" ({fdct_txt['rain_prob']})" if fdct_txt["rain_prob"] != "--%" else "")

        # condition line (condition in the accent color, then " · feels ...")
        ls_cond = fdct_txt["label"]
        ls_feels = " · " + i18n.tr("wt.feels_inline", value=fdct_txt["feels"])

        # 3 detail lines with one font size (uniform), footer with its own
        llst_detail = [ls_cond + ls_feels,
                       ls_wind,
                       f"{ls_rain} · " + i18n.tr("wt.humidity_inline", value=fdct_txt["humidity"])]
        ls_foot = " · ".join(x for x in (fdct_txt["place"], fdct_txt["source"], fdct_txt["age"]) if x)

        llst_srf = self._render_fit(llst_detail, self._i_sz_text, self._i_text_w, df.DCLR_TEXT)
        llst_srf += self._render_fit([ls_foot], self._i_sz_small, self._i_text_w, df.DCLR_TEXT_DIM)

        # condition highlighted: redraw its first part in the accent color (same font size)
        if llst_srf[0].get_width() <= self._i_text_w:
            lfnt = vu.font(self._s_font, vu.fit_size_all(self._s_font, llst_detail, self._i_text_w, self._i_sz_text))
            lsrf_c = lfnt.render(ls_cond, True, df.DCLR_ACCENT)
            lsrf_f = lfnt.render(ls_feels, True, df.DCLR_TEXT)
            lsrf = pg.Surface((lsrf_c.get_width() + lsrf_f.get_width(), max(lsrf_c.get_height(), lsrf_f.get_height())))
            lsrf.fill(df.DCLR_BG)
            lsrf.blit(lsrf_c, (0, 0))
            lsrf.blit(lsrf_f, (lsrf_c.get_width(), 0))
            llst_srf[0] = lsrf

        # for all lines...
        for li_i, lsrf in enumerate(llst_srf):
            # vertically centered in its line slot
            li_y = self._i_mrg + li_i * self._i_line_h + (self._i_line_h - lsrf.get_height()) // 2
            self._srf_wt.blit(lsrf, (self._i_text_x, li_y))

    # -----------------------------------------------------------------------------------------
    def _texts(self, fdct: dict) -> dict:
        """
        formatted texts for the weather data (shared by both styles)

        :param fdct (dict): weather data

        :returns (dict): label, temp, minmax, feels, wind, gust, gust_num, rain, rain_prob,
                         humidity, place, source, age
        """
        # units
        ls_wu = fdct.get("wind_unit", "")
        ls_pu = fdct.get("precip_unit", "")

        # attribution, and the data age when old ("" otherwise)
        ls_source = "open-meteo.com"
        ls_age = i18n.tr("wt.old", n=int((time.monotonic() - fdct.get("fetched", 0)) // 60)) if self._v_stale else ""

        # texts
        return {"label": i18n.tr(f"wmo.{fdct.get('code')}") if fdct.get("code") in DDCT_WMO else i18n.tr("wmo.unknown"),
                "temp": self._deg(fdct.get("temp")),
                "minmax": f"{self._deg(fdct.get('tmin'))} / {self._deg(fdct.get('tmax'))}",
                "feels": self._deg(fdct.get("feels")),
                "wind": f"{self._num(fdct.get('wind'))} {ls_wu} {self._compass(fdct.get('wind_dir'))}".rstrip(),
                "gust": f"{self._num(fdct.get('gust'))} {ls_wu}".rstrip(),
                "gust_num": self._num(fdct.get("gust")),
                "rain": f"{self._num(fdct.get('rain_sum'), 1)} {ls_pu}".rstrip(),
                "rain_prob": f"{self._num(fdct.get('rain_prob'))}%",
                "humidity": f"{self._num(fdct.get('humidity'))}%",
                "place": fdct.get("place", ""),
                "source": ls_source,
                "age": ls_age}

    # -----------------------------------------------------------------------------------------
    def _draw_icon(self, fs_icon: str, fv_day: bool, frct: pg.Rect):
        """
        draw a weather icon with primitives only

        :param fs_icon (str): clear, partly, cloudy, fog, drizzle, rain, snow, thunder
        :param fv_day (bool): day (sun) or night (moon)
        :param frct (pg.Rect): icon box
        """
        # box size and center
        li_s = min(frct.width, frct.height)
        li_cx, li_cy = frct.center

        # clear sky: big sun / moon
        if "clear" == fs_icon:
            self._draw_sky(fv_day, li_cx, li_cy, li_s * 22 // 100)
            return

        # partly cloudy: small sun / moon behind a cloud
        if "partly" == fs_icon:
            self._draw_sky(fv_day, li_cx - li_s // 7, li_cy - li_s // 7, li_s * 16 // 100)
            self._draw_cloud(li_cx + li_s // 12, li_cy + li_s // 10, li_s * 62 // 100, DCLR_CLOUD)
            return

        # fog: horizontal lines
        if "fog" == fs_icon:
            for li_i in range(4):
                li_y = li_cy - li_s // 4 + li_i * li_s // 6
                li_dx = (li_s // 12) * (li_i % 2)
                pg.draw.line(self._srf_wt, DCLR_CLOUD, (li_cx - li_s * 4 // 10 + li_dx, li_y),
                             (li_cx + li_s * 4 // 10 - li_dx, li_y), max(2, li_s // 18))
            return

        # cloud (overcast, darker with precipitation), a bit higher if something falls from it
        lv_falls = fs_icon in ("drizzle", "rain", "snow", "thunder")
        li_cloud_cy = li_cy - li_s // 8 if lv_falls else li_cy
        self._draw_cloud(li_cx, li_cloud_cy, li_s * 80 // 100, DCLR_CLOUD_DARK if lv_falls else DCLR_CLOUD)

        # below the cloud
        li_top = li_cloud_cy + li_s // 7
        li_lw = max(2, li_s // 20)

        # drizzle / rain: slanted drops (more and longer for rain)
        if fs_icon in ("drizzle", "rain"):
            li_len = li_s // 7 if "rain" == fs_icon else li_s // 12

            for li_i in (-1, 0, 1):
                li_x = li_cx + li_i * li_s // 5
                pg.draw.line(self._srf_wt, DCLR_RAIN, (li_x, li_top + li_s // 20),
                             (li_x - li_len // 2, li_top + li_s // 20 + li_len), li_lw)

        # snow: dots
        elif "snow" == fs_icon:
            for li_i, li_j in ((-1, 0), (0, 1), (1, 0)):
                pg.draw.circle(self._srf_wt, DCLR_SNOW, (li_cx + li_i * li_s // 5, li_top + li_s // 10 + li_j * li_s // 10),
                               max(2, li_s // 22))

        # thunder: bolt
        elif "thunder" == fs_icon:
            li_u = li_s // 10
            pg.draw.polygon(self._srf_wt, DCLR_BOLT,
                            [(li_cx + li_u // 2, li_top), (li_cx - li_u, li_top + 2 * li_u), (li_cx, li_top + 2 * li_u),
                             (li_cx - li_u // 2, li_top + 4 * li_u), (li_cx + li_u, li_top + li_u + li_u // 2),
                             (li_cx, li_top + li_u + li_u // 2)])

    # -----------------------------------------------------------------------------------------
    def _draw_cloud(self, fi_cx: int, fi_cy: int, fi_w: int, fclr):
        """
        cloud: three circles over a rounded base

        :param fi_cx, fi_cy (int): center
        :param fi_w (int): width
        :param fclr (tuple): color
        """
        li_r = fi_w // 6

        # base
        pg.draw.rect(self._srf_wt, fclr, pg.Rect(fi_cx - fi_w // 2, fi_cy - li_r // 2, fi_w, li_r * 2),
                     border_radius=li_r)
        # puffs
        pg.draw.circle(self._srf_wt, fclr, (fi_cx - fi_w // 5, fi_cy - li_r // 3), li_r + li_r // 4)
        pg.draw.circle(self._srf_wt, fclr, (fi_cx + fi_w // 8, fi_cy - li_r * 2 // 3), li_r * 3 // 2)

    # -----------------------------------------------------------------------------------------
    def _draw_sky(self, fv_day: bool, fi_cx: int, fi_cy: int, fi_r: int):
        """
        sun (with rays) or crescent moon

        :param fv_day (bool): sun if day, moon if night
        :param fi_cx, fi_cy (int): center
        :param fi_r (int): radius
        """
        # sun
        if fv_day:
            pg.draw.circle(self._srf_wt, DCLR_SUN, (fi_cx, fi_cy), fi_r)

            # rays
            for li_k in range(8):
                lf_a = li_k * math.pi / 4
                pg.draw.line(self._srf_wt, DCLR_SUN,
                             (fi_cx + int(math.cos(lf_a) * fi_r * 1.35), fi_cy + int(math.sin(lf_a) * fi_r * 1.35)),
                             (fi_cx + int(math.cos(lf_a) * fi_r * 1.75), fi_cy + int(math.sin(lf_a) * fi_r * 1.75)),
                             max(2, fi_r // 5))
            return

        # moon: disc minus an offset disc (background color)
        pg.draw.circle(self._srf_wt, DCLR_MOON, (fi_cx, fi_cy), fi_r)
        pg.draw.circle(self._srf_wt, df.DCLR_BG, (fi_cx + fi_r * 2 // 3, fi_cy - fi_r // 3), fi_r * 9 // 10)

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _compass(f_deg) -> str:
        """
        wind direction -> compass point ("" if unknown)
        """
        return "" if f_deg is None else i18n.tr_list("wt.compass")[int((float(f_deg) + 22.5) // 45) % 8]

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _deg(f_val) -> str:
        """
        temperature -> "23°" ("--°" if unknown)
        """
        return "--°" if f_val is None else f"{round(float(f_val))}°"

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _num(f_val, fi_dec: int = 0) -> str:
        """
        number -> text ("--" if unknown)
        """
        return "--" if f_val is None else (f"{float(f_val):.{fi_dec}f}" if fi_dec else f"{round(float(f_val))}")

    # -----------------------------------------------------------------------------------------
    def get_surface(self):
        """
        return surface
        """
        return self._srf_wt

    # -----------------------------------------------------------------------------------------
    def on_weather_data(self, fdct_payload: dict):
        """
        new weather data (called in the fetcher thread: keep the reference only, no rendering)

        :param fdct_payload (dict): weather data
        """
        # keep it (atomic reference assignment; picked up by update(), in the main thread)
        self._dct_new = fdct_payload

    # -----------------------------------------------------------------------------------------
    def on_weather_error(self, fdct_payload: dict):
        """
        weather error (fetcher thread): only matters while there's no data

        :param fdct_payload (dict): {"code", "message"}
        """
        # keep the error code (picked up by update())
        self._s_error = fdct_payload.get("code", "error")

    # -----------------------------------------------------------------------------------------
    def start(self):
        """
        start view (draw the first frame)
        """
        # logger
        M_LOG.info(">> start")

        # draw the first frame
        self.update()

    # -----------------------------------------------------------------------------------------
    def update(self):
        """
        called by the main thread every frame: redraw on new data, error, or when the data age
        changes (checked on new data and every DF_STALE_CHECK seconds)

        :returns (bool): True if the surface changed
        """
        # new data ?
        ldct_new = self._dct_new
        lv_new = ldct_new is not self._dct_data

        if lv_new:
            self._dct_data = ldct_new
            self._v_dirty = True

        # new error while there's no data (message to show) ?
        ls_error = self._s_error

        if (not self._dct_data) and (ls_error != self._s_error_drawn):
            self._s_error_drawn = ls_error
            self._v_dirty = True

        # time to check the data age (new data: at once, it may not be old anymore) ?
        lf_now = time.perf_counter()

        if self._dct_data and (lv_new or (lf_now - self._tm_stale_check >= DF_STALE_CHECK)):
            self._tm_stale_check = lf_now

            # old ?
            lv_stale = time.monotonic() - self._dct_data.get("fetched", 0) > self._dct_config.get("staleAfter", 45 * 60)

            # changed, or old (the "N min old" text changes) ?
            if lv_stale or (lv_stale != self._v_stale):
                self._v_stale = lv_stale
                self._v_dirty = True

        # nothing to do ?
        if not self._v_dirty:
            return False

        # redraw
        self._draw()

        # changed
        return True

    # =========================================================================================
    # data
    # =========================================================================================

    # -----------------------------------------------------------------------------------------
    @property
    def i_height(self) -> int:
        """strip height"""
        return self._i_height

# < the end >----------------------------------------------------------------------------------
