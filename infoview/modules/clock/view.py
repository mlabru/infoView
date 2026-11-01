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

        # time line: the rest; "88:88" + gap + seconds ("88", DF_SECONDS_SCALE of the time font)
        li_time_h = self._i_height - li_date_h - 2 * li_mrg
        li_gap = max(2, li_mrg)

        # width of the time block for a time font size
        def lf_block_w(fi_size: int) -> int:
            return pg.font.Font(ls_digi, fi_size).size("88:88")[0] + li_gap + \
                   pg.font.Font(ls_digi, max(1, int(fi_size * DF_SECONDS_SCALE))).size("88")[0]

        # biggest time font that fits height (fit_font) and the whole block width
        li_size = vu.fit_size(ls_digi, "88:88", li_w, li_time_h)
        while (li_size > 8) and (lf_block_w(li_size) > li_w):
            li_size -= 2

        self._fnt_l2 = pg.font.Font(ls_digi, li_size)
        self._fnt_sc = pg.font.Font(ls_digi, max(1, int(li_size * DF_SECONDS_SCALE)))

        # time block centered: time right aligned to a fixed point (colon doesn't move when the
        # hour goes from one to two digits), seconds right after it
        li_time_w, li_time_hh = self._fnt_l2.size("88:88")
        li_block_w = lf_block_w(li_size)

        self._i_time_right = (self._i_width - li_block_w) // 2 + li_time_w
        self._i_sec_x = self._i_time_right + li_gap
        self._i_time_y = li_date_h + li_mrg + max(0, (li_time_h - li_time_hh) // 2)
        self._i_sec_y = self._i_time_y + int(li_time_hh * .12)

        # debug
        M_LOG.debug("clock %dx%d: date font %d, time font %d", self._i_width, self._i_height,
                    self._fnt_l1.get_height(), li_size)

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
        lsf_time = self._fnt_l2.render(f"{fdt_now.hour}:{fdt_now:%M}", True, self._time_color(df.DCLR_TIME))
        self._srf_clock.blit(lsf_time, lsf_time.get_rect(topright=(self._i_time_right, self._i_time_y)))

        # build text for seconds
        lsf_sec = self._fnt_sc.render(f"{fdt_now:%S}", True, self._time_color(df.DCLR_SECONDS))
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
