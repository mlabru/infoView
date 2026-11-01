# -*- coding: utf-8 -*-
"""
infoView 1.0
Clock / View

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import datetime
import logging
import sys

# pygame
import pygame as pg

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.settings as df
import infoview.core.i18n as i18n
import infoview.core.timesync as ts
import infoview.ui.fonts as vu

# < constants >--------------------------------------------------------------------------------

# default surface size
DI_SURFACE_HEIGHT = 250
DI_SURFACE_WIDTH = 700

# date line height (fraction of the surface height)
DF_DATE_HEIGHT = .16

# seconds font size (fraction of the time font size)
DF_SECONDS_SCALE = .36

# vertical stretch of the digits (1. = font proportions), used only as far as the height allows:
# the time font is limited by the width, seven segment digits stand a taller shape well
DF_TIME_STRETCH = 1.3

# seconds top below the digits top, beside the time (fraction of the digits height)
DF_SECONDS_TOP = .12

# rendered (and stretched) texts kept, cleared when bigger (a new time every minute)
DI_CACHE_MAX = 128

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < SClockView >-------------------------------------------------------------------------------

class SClockView:
    """
    digital clock: date line (configured language) + hours:minutes + seconds, fonts fitted to
    the surface size; redrawn only when the second changes (update() -> True)
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fi_width: int = DI_SURFACE_WIDTH, fi_height: int = DI_SURFACE_HEIGHT):
        """
        constructor

        :param fi_width (int): surface width
        :param fi_height (int): surface height (fonts and layout are fitted to the surface)
        """
        # logger
        M_LOG.info(">> constructor")

        # surface size
        self._i_width: int = fi_width
        self._i_height: int = fi_height

        # frame size
        self._srf_clock = pg.Surface((fi_width, fi_height))

        # fonts and positions for this size
        self._layout()

        # time (to the second) currently drawn on the surface
        self._dt_drawn = None

    # -----------------------------------------------------------------------------------------
    def _layout(self):
        """
        fit fonts and compute positions for the surface size
        """
        # font files
        ls_font = df.DS_FONT_TEXT
        ls_digi = df.DS_FONT_DIGITAL

        # margin
        li_mrg = max(4, self._i_height // 50)
        # available width
        li_w = self._i_width - 2 * li_mrg

        # date line: top DF_DATE_HEIGHT of the surface, the widest date of the language must fit
        li_date_h = int(self._i_height * DF_DATE_HEIGHT)
        lfnt_ref = pg.font.Font(ls_font, 20)
        ls_sample = max(i18n.date_samples(), key=lambda s: lfnt_ref.size(s)[0])
        self._fnt_l1 = vu.fit_font(ls_font, ls_sample, li_w, li_date_h)
        self._i_date_y = li_mrg

        # time line: the rest, "88:88" with the seconds ("88", DF_SECONDS_SCALE of the time font)
        # beside it or below it (right aligned to the minutes), whichever gives bigger digits
        li_time_h = self._i_height - li_date_h - 2 * li_mrg
        li_gap = max(2, li_mrg)

        lt_side = self._fit_time(ls_digi, li_w, li_time_h, li_gap, False)
        lt_below = self._fit_time(ls_digi, li_w, li_time_h, li_gap, True)

        # digits area (width x stretched height): seconds below only when the time gets bigger
        self._v_sec_below = (lt_below[0] ** 2 * lt_below[1]) > (lt_side[0] ** 2 * lt_side[1])
        li_size, self._f_stretch = lt_below if self._v_sec_below else lt_side

        self._fnt_l2 = vu.font(ls_digi, li_size)
        self._fnt_sc = vu.font(ls_digi, self._sec_size(li_size))

        # stretched heights
        li_time_w, li_time_hh = self._fnt_l2.size("88:88")
        li_time_hh = round(li_time_hh * self._f_stretch)
        li_sec_w, li_sec_hh = self._fnt_sc.size("88")
        li_sec_hh = round(li_sec_hh * self._f_stretch)

        # time right aligned to a fixed point (the colon doesn't move when the hour goes from one
        # to two digits); block centered
        if self._v_sec_below:
            # seconds under the minutes, right aligned to the time
            li_block_w, li_block_h = li_time_w, li_time_hh + li_gap + li_sec_hh
        else:
            # seconds right after the time, near its top
            li_block_w, li_block_h = li_time_w + li_gap + li_sec_w, li_time_hh

        self._i_time_right = (self._i_width - li_block_w) // 2 + li_time_w
        self._i_time_y = li_date_h + li_mrg + max(0, (li_time_h - li_block_h) // 2)

        if self._v_sec_below:
            self._i_sec_x = self._i_time_right - li_sec_w
            self._i_sec_y = self._i_time_y + li_time_hh + li_gap
        else:
            self._i_sec_x = self._i_time_right + li_gap
            self._i_sec_y = self._i_time_y + int(li_time_hh * DF_SECONDS_TOP)

        # rendered texts: (font, text, color) -> surface
        self._dct_cache = {}

        # debug
        M_LOG.debug("clock %dx%d: date font %d, time font %d x%.2f, seconds %s", self._i_width,
                    self._i_height, self._fnt_l1.get_height(), li_size, self._f_stretch,
                    "below" if self._v_sec_below else "beside")

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _sec_size(fi_size: int) -> int:
        """
        seconds font size for a time font size

        :param fi_size (int): time font size

        :returns (int): seconds font size
        """
        return max(1, int(fi_size * DF_SECONDS_SCALE))

    # -----------------------------------------------------------------------------------------
    @classmethod
    def _fit_time(cls, fs_digi: str, fi_w: int, fi_h: int, fi_gap: int, fv_below: bool) -> tuple:
        """
        biggest time font for one placement of the seconds, and the stretch the height still allows

        :param fs_digi (str): digits font file
        :param fi_w (int): available width
        :param fi_h (int): available height
        :param fi_gap (int): gap between the time and the seconds
        :param fv_below (bool): seconds below the time (else beside it)

        :returns (tuple): (font size, vertical stretch in [1, DF_TIME_STRETCH])
        """
        # block size (not stretched) for a time font size (fonts not cached: many sizes are tried)
        def lt_block(fi_size: int) -> tuple:
            li_tw, li_th = pg.font.Font(fs_digi, fi_size).size("88:88")
            li_sw, li_sh = pg.font.Font(fs_digi, cls._sec_size(fi_size)).size("88")

            if fv_below:
                return max(li_tw, li_sw), li_th, li_sh

            return li_tw + fi_gap + li_sw, li_th, 0

        # block fits ?
        def lv_fits(fi_size: int) -> bool:
            li_bw, li_th, li_sh = lt_block(fi_size)
            return (li_bw <= fi_w) and (li_th + ((fi_gap + li_sh) if fv_below else 0) <= fi_h)

        # binary search: biggest size whose block fits (width and height grow with the size)
        li_lo, li_hi = 8, vu.fit_size(fs_digi, "88:88", fi_w, fi_h)

        while li_lo < li_hi:
            li_mid = (li_lo + li_hi + 1) // 2

            if lv_fits(li_mid):
                li_lo = li_mid
            else:
                li_hi = li_mid - 1

        li_size = li_lo

        # stretch: as much as DF_TIME_STRETCH, as far as the height allows (the gap isn't stretched)
        _, li_th, li_sh = lt_block(li_size)
        li_free = fi_h - (fi_gap if fv_below else 0)
        lf_stretch = min(DF_TIME_STRETCH, li_free / max(1, li_th + li_sh))

        return li_size, max(1., lf_stretch)

    # -----------------------------------------------------------------------------------------
    def _render(self, f_font, fs_text: str, fclr):
        """
        render a text with the digits stretched (DF_TIME_STRETCH), cached: the stretch is done
        once per text, not on every redraw (the seconds repeat every minute)

        :param f_font (pg.font.Font): font
        :param fs_text (str): text
        :param fclr (tuple): color

        :returns (pg.Surface): rendered text
        """
        lt_key = (id(f_font), fs_text, fclr)

        if lt_key not in self._dct_cache:
            # a new time every minute: keep the cache small
            if len(self._dct_cache) >= DI_CACHE_MAX:
                self._dct_cache.clear()

            lsf_text = f_font.render(fs_text, True, fclr)

            # without the line spacing below the digits (the layout uses the text height)
            li_h = min(lsf_text.get_height(), f_font.size(fs_text)[1])
            lsf_text = lsf_text.subsurface((0, 0, lsf_text.get_width(), li_h)).copy()

            if self._f_stretch > 1.:
                lsf_text = pg.transform.smoothscale(lsf_text, (lsf_text.get_width(),
                                                    round(lsf_text.get_height() * self._f_stretch)))

            self._dct_cache[lt_key] = lsf_text

        return self._dct_cache[lt_key]

    # -----------------------------------------------------------------------------------------
    def _build_surface(self, fdt_now):
        """
        build the view surface

        :param fdt_now (datetime): time to display
        """
        # logger
        M_LOG.info(">> _build_surface")

        # clear surface (fill with black color)
        self._srf_clock.fill(df.DCLR_BG)

        # date line >>>

        # build text of date line (day of week, day, month, year in the configured language), centered
        lsf_date = self._fnt_l1.render(self._date_text(fdt_now), True, df.DCLR_DATE)
        self._srf_clock.blit(lsf_date, lsf_date.get_rect(midtop=(self._i_width // 2, self._i_date_y)))

        # time line >>>

        # build text of time line (hour without leading zero)
        lsf_time = self._render(self._fnt_l2, f"{fdt_now.hour}:{fdt_now:%M}", self._time_color(df.DCLR_TIME))
        self._srf_clock.blit(lsf_time, lsf_time.get_rect(topright=(self._i_time_right, self._i_time_y)))

        # build text for seconds
        lsf_sec = self._render(self._fnt_sc, f"{fdt_now:%S}", self._time_color(df.DCLR_SECONDS))
        self._srf_clock.blit(lsf_sec, (self._i_sec_x, self._i_sec_y))

    # -----------------------------------------------------------------------------------------
    def _date_text(self, fdt_now) -> str:
        """
        text of the date line: the date, or a notice while the system clock is not synchronized
        (the Raspberry Pi has no real time clock: see infoview/core/timesync.py)

        :param fdt_now (datetime): time to display

        :returns (str): text (fits the surface width)
        """
        # not synchronized: the date (and time) may be wrong
        if not ts.GV_SYNCED:
            return vu.fit_text(self._fnt_l1, i18n.tr("clock.unsynced"), self._i_width)

        return i18n.format_date(fdt_now)

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _time_color(fclr):
        """
        color of the time digits: dimmed while the system clock is not synchronized

        :param fclr (tuple): color when synchronized

        :returns (tuple): color
        """
        return fclr if ts.GV_SYNCED else df.DCLR_TEXT_DIM

    # -----------------------------------------------------------------------------------------
    def get_surface(self):
        """
        return surface
        """
        # logger
        M_LOG.info(">> get_surface")
        
        # return surface
        return self._srf_clock

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
        called by the main thread every frame: redraw only when the second changes

        :returns (bool): True if the surface changed
        """
        # now (to the second)
        ldt_now = datetime.datetime.now().replace(microsecond=0)

        # same second already drawn ?
        if ldt_now == self._dt_drawn:
            # nothing changed
            return False

        # build the surface clock
        self._build_surface(ldt_now)

        # save drawn time
        self._dt_drawn = ldt_now

        # surface changed
        return True

    # =========================================================================================
    # data
    # =========================================================================================
        
    # -----------------------------------------------------------------------------------------
    @property
    def i_height(self) -> int:
        """surface height"""
        return self._i_height

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # logger
    lg.setup()

    try:
        # initialize pygame library
        pg.init()

        # icon to the Digital Clock frame
        l_icon = pg.image.load(df.DS_ICON_APP)
        pg.display.set_icon(l_icon)

        # frame size
        lscreen = pg.display.set_mode((DI_SURFACE_WIDTH, DI_SURFACE_HEIGHT))

        # caption
        pg.display.set_caption("Digital Clock")

        # keep things running
        gd.GV_KEEP_RUN = True

        # create view
        lview = SClockView()

        # start viewer
        lview.start()

        # caps the main loop so it doesn't redraw faster than needed
        l_clock = pg.time.Clock()

        # for ever....
        while gd.GV_KEEP_RUN:
            # for all events
            for l_evt in pg.event.get():
                # quit ?
                if pg.QUIT == l_evt.type:
                    # stop things
                    gd.GV_KEEP_RUN = False

            # asked to stop while handling events above ?
            if not gd.GV_KEEP_RUN:
                # don't touch the display again, just leave
                break

            # update view
            lview.update()

            # build screen
            lscreen.blit(lview.get_surface(), (0, 0))

            # update the time displayed
            pg.display.update()

            # yield to the scheduler, no need to redraw faster than this
            l_clock.tick(30)

        # quit
        pg.quit()

    # on error...
    except KeyboardInterrupt:
        # logger
        logging.warning("Interrupted.")

    # terminate
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
