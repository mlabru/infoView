# -*- coding: utf-8 -*-
"""
infoView 1.0
Controls / View

on-screen button bar for touchscreens (no keyboard / mouse). Hidden by default: a tap anywhere
shows it, it hides itself after DF_AUTOHIDE seconds without touches. Buttons emit the same
actions as the keyboard (events on the global bus), so input stays independent of the device.
Quit needs a long press (held DF_QUIT_HOLD seconds, the button fills up red meanwhile): a kiosk
must not stop by accident (a quit is a normal end, the supervisor does not restart the app).
Icons are drawn with primitives only (polygons, lines, arcs) - no font glyphs - to keep them
easy to port (e.g. to LVGL / TFT_eSPI on an ESP32).

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import math
import sys
import time

# pygame
import pygame as pg

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.settings as df

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# bar height (px): ~10 mm on the 7" Raspberry Pi touchscreen (800x480)
DI_BAR_HEIGHT = 64
DI_SURFACE_WIDTH = 800

# margin around / between buttons (px)
DI_BTN_MARGIN = 6

# hide the bar after this time without touches (sec)
DF_AUTOHIDE = 8.
# "quit" must be held down this long (sec)
DF_QUIT_HOLD = 3.

# buttons: (id, action emitted on the event bus), left to right
DLST_BUTTONS = [("prev", "ARTICLE_PREVIOUS"),
                ("next", "ARTICLE_NEXT"),
                ("more", "ARTICLE_MORE_DETAILS"),   # description, full article, scroll down
                ("up", "ARTICLE_SCROLL_UP"),        # scroll up (full article)
                ("less", "ARTICLE_LESS_DETAILS"),   # back to titles
                ("quit", "APP_QUIT")]               # long press (DF_QUIT_HOLD)

# < SControlsView >----------------------------------------------------------------------------

class SControlsView:
    """
    touch button bar (see the module docstring): pointer_down / pointer_up from the main loop,
    update() for the auto hide / quit confirmation timeouts
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fi_width: int = DI_SURFACE_WIDTH, fi_height: int = DI_BAR_HEIGHT):
        """
        constructor

        :param fi_width (int): bar width (usually the screen width)
        :param fi_height (int): bar height
        """
        # logger
        M_LOG.info(">> constructor")

        # bar size
        self._i_width: int = fi_width
        self._i_height: int = fi_height

        # bar surface
        self._srf_bar = pg.Surface((fi_width, fi_height))

        # button rectangles, equal slots
        li_slot = fi_width // len(DLST_BUTTONS)

        self._dct_rect = {ls_id: pg.Rect(li_i * li_slot + DI_BTN_MARGIN, DI_BTN_MARGIN,
                                         li_slot - 2 * DI_BTN_MARGIN, fi_height - 2 * DI_BTN_MARGIN)
                          for li_i, (ls_id, _) in enumerate(DLST_BUTTONS)}

        # button actions
        self._dct_action = dict(DLST_BUTTONS)

        # newsfeed display mode (enables / disables buttons)
        self._s_mode: str = "title"

        # bar visible ?
        self._v_visible: bool = False
        # time of the last touch
        self._tm_last_touch: float = 0.
        # button being pressed (None if none)
        self._s_pressed = None
        # ignore the next release (the touch that only showed / hid the bar)
        self._v_swallow_up: bool = False
        # time the current press started (quit long press)
        self._tm_pressed: float = 0.

        # redraw needed ?
        self._v_dirty: bool = True

        # events callback (display mode)
        gd.G_EVENTS.on("ARTICLE_INFO_RESPONSE", self.on_article_info_response)

    # -----------------------------------------------------------------------------------------
    def _button_at(self, ft_pos):
        """
        button under a point

        :param ft_pos (tuple): (x, y) in screen coordinates (the bar is at the top, y = 0)

        :returns (str): button id, or None
        """
        for ls_id, lrct in self._dct_rect.items():
            if lrct.collidepoint(ft_pos):
                return ls_id

        return None

    # -----------------------------------------------------------------------------------------
    def _draw(self):
        """
        draw the bar
        """
        # logger
        M_LOG.info(">> _draw")

        # background
        self._srf_bar.fill(df.DCLR_BAR_BG)

        # for all buttons...
        for ls_id, lrct in self._dct_rect.items():
            # state
            lv_enabled = self._is_enabled(ls_id)

            # button background
            lclr_bg = df.DCLR_BTN_PRESSED if lv_enabled and (ls_id == self._s_pressed) else df.DCLR_BTN

            pg.draw.rect(self._srf_bar, lclr_bg, lrct, border_radius=lrct.height // 5)

            # quit held down: fills up red from the left (full: quits)
            lf_progress = self._quit_progress() if "quit" == ls_id else 0.

            if lf_progress > 0.:
                lrct_fill = pg.Rect(lrct.left, lrct.top, max(1, int(lrct.width * lf_progress)), lrct.height)
                pg.draw.rect(self._srf_bar, df.DCLR_QUIT_ARMED, lrct_fill, border_radius=lrct.height // 5)

            # icon
            self._draw_icon(ls_id, lrct, df.DCLR_BTN_ICON if lv_enabled else df.DCLR_BTN_DISABLED)

        # done
        self._v_dirty = False

    # -----------------------------------------------------------------------------------------
    def _draw_icon(self, fs_id: str, frct: pg.Rect, fclr):
        """
        draw a button icon with primitives only

        :param fs_id (str): button id
        :param frct (pg.Rect): button rectangle
        :param fclr (tuple): icon color
        """
        # center and half size of the icon
        li_cx, li_cy = frct.center
        li_r = min(frct.width, frct.height) * 3 // 10
        # line width
        li_lw = max(2, li_r // 4)

        # triangles: previous / next / more (down) / up
        if "prev" == fs_id:
            pg.draw.polygon(self._srf_bar, fclr, [(li_cx - li_r, li_cy), (li_cx + li_r, li_cy - li_r), (li_cx + li_r, li_cy + li_r)])

        elif "next" == fs_id:
            pg.draw.polygon(self._srf_bar, fclr, [(li_cx + li_r, li_cy), (li_cx - li_r, li_cy - li_r), (li_cx - li_r, li_cy + li_r)])

        elif "more" == fs_id:
            pg.draw.polygon(self._srf_bar, fclr, [(li_cx, li_cy + li_r), (li_cx - li_r, li_cy - li_r), (li_cx + li_r, li_cy - li_r)])

        elif "up" == fs_id:
            pg.draw.polygon(self._srf_bar, fclr, [(li_cx, li_cy - li_r), (li_cx - li_r, li_cy + li_r), (li_cx + li_r, li_cy + li_r)])

        # back to titles: X
        elif "less" == fs_id:
            pg.draw.line(self._srf_bar, fclr, (li_cx - li_r, li_cy - li_r), (li_cx + li_r, li_cy + li_r), li_lw)
            pg.draw.line(self._srf_bar, fclr, (li_cx - li_r, li_cy + li_r), (li_cx + li_r, li_cy - li_r), li_lw)

        # quit: power symbol (arc open at the top + vertical bar)
        elif "quit" == fs_id:
            lrct_arc = pg.Rect(0, 0, 2 * li_r, 2 * li_r)
            lrct_arc.center = (li_cx, li_cy)
            # arc from 120 to 420 degrees (counterclockwise from 3 o'clock), gap at the top
            pg.draw.arc(self._srf_bar, fclr, lrct_arc, math.radians(120), math.radians(420), li_lw)
            pg.draw.line(self._srf_bar, fclr, (li_cx, li_cy - li_r - li_lw // 2), (li_cx, li_cy), li_lw)

    # -----------------------------------------------------------------------------------------
    def _is_enabled(self, fs_id: str) -> bool:
        """
        button enabled for the current newsfeed mode ?

        :param fs_id (str): button id
        """
        # scroll up: only showing the full article
        if "up" == fs_id:
            return "full" == self._s_mode

        # back to titles: only showing details
        if "less" == fs_id:
            return "title" != self._s_mode

        # others: always
        return True

    # -----------------------------------------------------------------------------------------
    def _set_visible(self, fv_visible: bool):
        """
        show / hide the bar

        :param fv_visible (bool): visible ?
        """
        # changed ?
        if fv_visible != self._v_visible:
            self._v_visible = fv_visible
            self._v_dirty = True

        # hidden: nothing pressed
        if not fv_visible:
            self._s_pressed = None

    # -----------------------------------------------------------------------------------------
    def get_surface(self):
        """
        return surface
        """
        return self._srf_bar

    # -----------------------------------------------------------------------------------------
    def on_article_info_response(self, fdct_payload: dict):
        """
        newsfeed article info: keep the display mode to enable / disable buttons

        :param fdct_payload (dict): article data
        """
        # display mode
        ls_mode = fdct_payload.get("mode", "title")

        # changed ?
        if ls_mode != self._s_mode:
            self._s_mode = ls_mode
            self._v_dirty = True

    # -----------------------------------------------------------------------------------------
    def pointer_down(self, ft_pos):
        """
        touch / mouse press

        :param ft_pos (tuple): (x, y) screen coordinates
        """
        # logger
        M_LOG.info(">> pointer_down")

        # touch time (auto hide timer)
        self._tm_last_touch = time.perf_counter()

        # hidden ? the first touch only shows the bar
        if not self._v_visible:
            self._set_visible(True)
            self._v_swallow_up = True
            return

        # button under the touch
        ls_id = self._button_at(ft_pos)

        # touch outside the buttons hides the bar
        if ls_id is None:
            # outside the bar ?
            if ft_pos[1] >= self._i_height:
                self._set_visible(False)
                self._v_swallow_up = True
            return

        # press feedback (enabled buttons only); start of a (quit) long press
        if self._is_enabled(ls_id):
            self._s_pressed = ls_id
            self._tm_pressed = time.perf_counter()
            self._v_dirty = True

    # -----------------------------------------------------------------------------------------
    def _quit_progress(self) -> float:
        """
        quit long press progress

        :returns (float): 0. (quit not pressed) .. 1. (held DF_QUIT_HOLD seconds: quit)
        """
        # quit not pressed ?
        if "quit" != self._s_pressed:
            return 0.

        return min(1., (time.perf_counter() - self._tm_pressed) / DF_QUIT_HOLD)

    # -----------------------------------------------------------------------------------------
    def pointer_up(self, ft_pos):
        """
        touch / mouse release: a button acts if pressed and released on it

        :param ft_pos (tuple): (x, y) screen coordinates
        """
        # logger
        M_LOG.info(">> pointer_up")

        # release of a touch that only showed / hid the bar ?
        if self._v_swallow_up:
            self._v_swallow_up = False
            return

        # button pressed
        ls_id = self._s_pressed

        # release press feedback
        if ls_id is not None:
            self._s_pressed = None
            self._v_dirty = True

        # released on the same button ? (quit acts only by being held, in update())
        if (ls_id is not None) and ("quit" != ls_id) and (ls_id == self._button_at(ft_pos)):
            # touch time (auto hide timer)
            self._tm_last_touch = time.perf_counter()

            # act
            self._activate(ls_id)

    # -----------------------------------------------------------------------------------------
    def _activate(self, fs_id: str):
        """
        button action

        :param fs_id (str): button id
        """
        # logger
        M_LOG.info(">> _activate: %s", fs_id)

        # emit action
        gd.G_EVENTS.emit(self._dct_action[fs_id], {})

    # -----------------------------------------------------------------------------------------
    def update(self):
        """
        called by the main thread every frame: timeouts and redraw if needed

        :returns (bool): True if the bar changed (shown, hidden or redrawn)
        """
        # now
        lf_now = time.perf_counter()

        # quit held down ? (progress drawn every frame; held long enough: quit, once)
        if "quit" == self._s_pressed:
            self._v_dirty = True

            if self._quit_progress() >= 1.:
                self._s_pressed = None
                gd.G_EVENTS.emit(self._dct_action["quit"], {})

        # auto hide (not while a button is held down) ?
        if self._v_visible and (self._s_pressed is None) and (lf_now - self._tm_last_touch > DF_AUTOHIDE):
            self._set_visible(False)

        # nothing to do ?
        if not self._v_dirty:
            return False

        # redraw (only matters while visible, but keep the surface current)
        self._draw()

        # changed
        return True

    # =========================================================================================
    # data
    # =========================================================================================

    # -----------------------------------------------------------------------------------------
    @property
    def i_height(self) -> int:
        """bar height"""
        return self._i_height

    # -----------------------------------------------------------------------------------------
    @property
    def v_visible(self) -> bool:
        """bar visible ?"""
        return self._v_visible

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # logger
    lg.setup()

    # initialize pygame library
    pg.init()

    # window
    lscreen = pg.display.set_mode((DI_SURFACE_WIDTH, 2 * DI_BAR_HEIGHT))
    pg.display.set_caption("Controls")

    # show emitted actions
    for _, ls_action in DLST_BUTTONS:
        gd.G_EVENTS.on(ls_action, lambda p, a=ls_action: print("action:", a))

    # quit on the quit button
    gd.G_EVENTS.on("APP_QUIT", lambda p: setattr(gd, "GV_KEEP_RUN", False))

    # create view
    lview = SControlsView()

    # caps the main loop
    l_clock = pg.time.Clock()

    # first frame must be drawn
    lv_first = True

    # for ever....
    while gd.GV_KEEP_RUN:
        # for all events
        for l_evt in pg.event.get():
            if pg.QUIT == l_evt.type:
                gd.GV_KEEP_RUN = False
            elif (pg.MOUSEBUTTONDOWN == l_evt.type) and (1 == l_evt.button):
                lview.pointer_down(l_evt.pos)
            elif (pg.MOUSEBUTTONUP == l_evt.type) and (1 == l_evt.button):
                lview.pointer_up(l_evt.pos)

        # redraw on change
        if lview.update() or lv_first:
            lscreen.fill(df.DCLR_BG)
            if lview.v_visible:
                lscreen.blit(lview.get_surface(), (0, 0))
            pg.display.update()
            lv_first = False

        l_clock.tick(30)

    pg.quit()
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
