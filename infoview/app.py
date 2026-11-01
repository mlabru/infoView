# -*- coding: utf-8 -*-
"""
infoView 1.0
infoview.app: composition root (window, layout, main loop, touch / key input)

target: Raspberry Pi 3 B+ with the official 7" touchscreen (800x480), no keyboard / mouse.
All interaction goes through the on-screen button bar (infoview/ui/controls.py); the keyboard is
kept as a development aid. Buttons and keys emit the same abstract actions on the event bus.

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import signal
import sys

# pygame
import pygame as pg

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.settings as df
import infoview.core.timesync as ts

# clock
import infoview.modules.clock.view as ckv

# controls
import infoview.ui.controls as ctv

# newsfeed
import infoview.modules.newsfeed.helper as nfh

import infoview.modules.newsfeed.model as nfm
import infoview.modules.newsfeed.view as nfv

# weather
import infoview.modules.weather.fetcher as wtf
import infoview.modules.weather.view as wtv

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------


# view modules: name -> {"module": view, "x": ..., "y": ... | "anchor": "bottom"} (drawing order)
DDCT_MODULE_VIEWS = {}

# non-view objects (models, helpers, fetcher threads): referenced here explicitly, not only
# through the event bus listeners
DLST_BACKENDS = []

# on-screen button bar (overlay, drawn last, gets the touches)
M_CONTROLS = None


# "strip" layout: weather strip height (fraction of the screen height): 96 px on 800x480
DF_WEATHER_HEIGHT = .2
# "sidebar" layout: weather column width (fraction of the screen width): 280 px on 800x480
DF_SIDEBAR_WIDTH = .35

# development keys -> actions (the device has no keyboard: same actions as the buttons)
DDCT_KEY_ACTIONS = {pg.K_ESCAPE: "APP_QUIT",
                    pg.K_q: "APP_QUIT",
                    pg.K_RIGHT: "ARTICLE_NEXT",
                    pg.K_LEFT: "ARTICLE_PREVIOUS",
                    pg.K_DOWN: "ARTICLE_MORE_DETAILS",      # description, full article, scroll down
                    pg.K_UP: "ARTICLE_SCROLL_UP",           # scroll up (full article)
                    pg.K_BACKSPACE: "ARTICLE_LESS_DETAILS", # back to titles
                    pg.K_RETURN: "ARTICLE_TOGGLE_FULL"}

# ---------------------------------------------------------------------------------------------
def _on_app_quit(fdct_payload: dict):
    """
    APP_QUIT action (quit button / key): ask the main loop to stop
    """
    # logger
    M_LOG.warning("quit requested.")

    # stop things
    gd.GV_KEEP_RUN = False

# ---------------------------------------------------------------------------------------------
def _on_signal(fi_signum, f_frame):
    """
    SIGTERM / SIGHUP handler: ask the main loop to stop

    :param fi_signum (int): signal number
    :param f_frame: current stack frame (unused: part of the signal handler signature)
    """
    # logger
    M_LOG.warning("signal %d received, stopping.", fi_signum)

    # stop things
    gd.GV_KEEP_RUN = False

# ---------------------------------------------------------------------------------------------
def _build_screen(fsrf_screen, fv_force: bool = False) -> list:
    """
    let every view update itself and recompose only the screen areas that changed

    :param fsrf_screen (pg.Surface): screen
    :param fv_force (bool): recompose the whole screen (first frame)

    :returns (list): changed screen rectangles (to update on the display), empty if none
    """
    # changed areas
    llst_dirty = [fsrf_screen.get_rect()] if fv_force else []

    # let all views redraw their surfaces if needed (all rendering happens in this thread)
    for lval in DDCT_MODULE_VIEWS.values():
        # update view
        lv_changed = lval["module"].update()

        # view surface (may have changed size, e.g. newsfeed details)
        lsrf = lval["module"].get_surface()

        # Y position (bottom anchored views grow upwards)
        li_y = fsrf_screen.get_height() - lsrf.get_height() if "bottom" == lval.get("anchor") else lval["y"]

        # screen area of the view, now and in the last frame
        lrct = pg.Rect(lval["x"], li_y, lsrf.get_width(), lsrf.get_height())
        lrct_prev = lval.get("rect")

        # changed contents or moved / resized (then the old area must be repainted too) ?
        if lv_changed or (lrct != lrct_prev):
            llst_dirty.append(lrct.union(lrct_prev) if lrct_prev else lrct)

        # save screen area
        lval["rect"] = lrct

    # button bar (shown, hidden or redrawn) ?
    if M_CONTROLS and M_CONTROLS.update():
        llst_dirty.append(pg.Rect(0, 0, fsrf_screen.get_width(), M_CONTROLS.i_height))

    # nothing changed ? (most frames; at rest only the clock changes, once a second)
    if not llst_dirty:
        return []

    # logger
    M_LOG.info(">> _build_screen")

    # for all changed areas...
    for lrct_dirty in llst_dirty:
        # paint only inside this area
        fsrf_screen.set_clip(lrct_dirty)

        # clear (theme background)
        fsrf_screen.fill(df.DCLR_BG)

        # all views, in order (later ones on top, e.g. newsfeed details over the clock)
        for lval in DDCT_MODULE_VIEWS.values():
            fsrf_screen.blit(lval["module"].get_surface(), lval["rect"])

        # button bar on top of everything
        if M_CONTROLS and M_CONTROLS.v_visible:
            fsrf_screen.blit(M_CONTROLS.get_surface(), (0, 0))

    # paint anywhere again
    fsrf_screen.set_clip(None)

    # changed areas
    return llst_dirty

# ---------------------------------------------------------------------------------------------
def clock(fi_width: int, fi_height: int):
    """
    start clock module

    :param fi_width (int): clock area width
    :param fi_height (int): clock area height (above the newsfeed ticker)
    """
    # logger
    M_LOG.info(">> clock")

    # create view
    lview = ckv.SClockView(fi_width, fi_height)

    # start viewer
    lview.start()

    # register module view
    DDCT_MODULE_VIEWS["clock"] = {"module": lview, "x": 0, "y": 0}

# ---------------------------------------------------------------------------------------------
def controls(fi_width: int):
    """
    start the on-screen button bar

    :param fi_width (int): bar width
    """
    global M_CONTROLS

    # logger
    M_LOG.info(">> controls")

    # create view
    M_CONTROLS = ctv.SControlsView(fi_width)

    # quit action
    gd.G_EVENTS.on("APP_QUIT", _on_app_quit)

# ---------------------------------------------------------------------------------------------
def newsfeed(fi_width: int, fi_max_height: int, fi_min_details_height: int = 0):
    """
    start newsfeed module

    :param fi_width (int): ticker width
    :param fi_max_height (int): max height when showing details
    :param fi_min_details_height (int): min height when showing details (covers the weather strip)
    """
    # logger
    M_LOG.info(">> newsfeed")

    # create SNewsFeed
    l_nf = nfm.SNewsFeed()
    # create SNodeHelper (listens to ADD_FEED, so before l_nf.start())
    l_nh = nfh.SNodeHelper()

    # keep references
    DLST_BACKENDS.extend([l_nf, l_nh])

    # start (registers the feeds: the node helper creates one fetcher thread per feed)
    l_nf.start()

    # create view
    lview = nfv.SNewsFeedView(fi_width, fi_max_height, fi_min_details_height)

    # start viewer
    lview.start()

    # register module view (anchored to the bottom of the screen)
    DDCT_MODULE_VIEWS["newsfeed"] = {"module": lview, "x": 0, "anchor": "bottom"}

# ---------------------------------------------------------------------------------------------
def weather(fi_width: int, fi_height: int, fi_x: int, fi_y: int, fs_style: str):
    """
    start weather module (Open-Meteo fetcher thread + view)

    :param fi_width (int): view width
    :param fi_height (int): view height
    :param fi_x (int): view X position
    :param fi_y (int): view Y position
    :param fs_style (str): "strip" or "sidebar"
    """
    # logger
    M_LOG.info(">> weather")

    # create view first (it listens to the data the fetcher emits)
    lview = wtv.SWeatherView(fi_width, fi_height, fs_style)

    # start viewer
    lview.start()

    # create and start fetcher (daemon thread)
    l_fetcher = wtf.SWeatherFetcher()

    l_fetcher.start()

    # keep reference
    DLST_BACKENDS.append(l_fetcher)

    # register module view
    DDCT_MODULE_VIEWS["weather"] = {"module": lview, "x": fi_x, "y": fi_y}

# ---------------------------------------------------------------------------------------------
def _screen_size():
    """
    screen size: IVW_SCREEN / screen ("WxH", validated by settings) if set, else the current
    display mode

    :returns (tuple): (width, height)
    """
    # override ?
    if df.DT_SCREEN:
        return df.DT_SCREEN

    # current display mode
    linfo = pg.display.Info()

    return linfo.current_w, linfo.current_h

# ---------------------------------------------------------------------------------------------
def main():
    """
    drive application
    """
    # logger
    M_LOG.info(">> main")

    # initialize pygame library
    pg.init()

    # icon to the Digital Clock frame
    l_icon = pg.image.load(df.DS_ICON_APP)
    pg.display.set_icon(l_icon)

    # size of the window
    li_w, li_h = _screen_size()
    lsrf_screen = pg.display.set_mode((li_w, li_h), pg.NOFRAME)

    # caption
    pg.display.set_caption("infoView 1.0")

    # kiosk (touch only): no mouse cursor, unless simulating the screen on a desktop
    pg.mouse.set_visible(bool(df.DS_SCREEN))

    # graceful stop on kill / logout
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGHUP, _on_signal)

    # system clock synchronized (NTP) ? if not yet, a thread watches it (no RTC on the Pi;
    # [general] clock_check = false trusts the clock)
    l_ts = ts.start(df.DV_CLOCK_CHECK)

    if l_ts:
        DLST_BACKENDS.append(l_ts)

    # height above the newsfeed ticker
    li_top_h = li_h - nfv.DI_SURFACE_HEIGHT

    # newsfeed details grow up to the button bar, over clock and weather; the bar overlays the
    # top of the screen when shown. Views are registered in drawing order: clock, weather, newsfeed
    if "strip" == df.DS_LAYOUT:
        # clock on top, weather strip under it, ticker at the bottom
        li_wt_h = int(li_h * DF_WEATHER_HEIGHT)

        clock(li_w, li_top_h - li_wt_h)
        weather(li_w, li_wt_h, 0, li_top_h - li_wt_h, "strip")

        # description covers the whole strip + ticker (never cuts the strip in half)
        li_min_details_h = li_wt_h + nfv.DI_SURFACE_HEIGHT

    # else, "sidebar" (default; infoview/core/settings.py has validated DS_LAYOUT)...
    else:
        # clock on the left, weather column on the right, ticker at the bottom
        li_wt_w = int(li_w * DF_SIDEBAR_WIDTH)

        clock(li_w - li_wt_w, li_top_h)
        weather(li_wt_w, li_top_h, li_w - li_wt_w, 0, "sidebar")

        # any details panel would cut the column: details always use the whole reading pane
        li_min_details_h = li_h - ctv.DI_BAR_HEIGHT

    # button bar (before the newsfeed: it follows the newsfeed display mode)
    controls(li_w)
    # newsfeed
    newsfeed(li_w, li_h - ctv.DI_BAR_HEIGHT, li_min_details_h)

    # keep things running
    gd.GV_KEEP_RUN = True

    # caps the main loop (touch latency ~33 ms; the screen is only redrawn when it changes)
    l_clock = pg.time.Clock()

    # first frame must be drawn
    lv_force = True

    # for ever....
    while gd.GV_KEEP_RUN:
        # for all events
        for l_evt in pg.event.get():
            # window closed ?
            if pg.QUIT == l_evt.type:
                # stop things
                gd.GV_KEEP_RUN = False

            # touch / mouse (SDL turns touches into left button events)
            elif (pg.MOUSEBUTTONDOWN == l_evt.type) and (1 == l_evt.button):
                M_CONTROLS.pointer_down(l_evt.pos)

            elif (pg.MOUSEBUTTONUP == l_evt.type) and (1 == l_evt.button):
                M_CONTROLS.pointer_up(l_evt.pos)

            # development key ?
            elif (pg.KEYDOWN == l_evt.type) and (l_evt.key in DDCT_KEY_ACTIONS):
                # same action as the button (handled in this thread, like everything that renders)
                gd.G_EVENTS.emit(DDCT_KEY_ACTIONS[l_evt.key], {})

        # asked to stop while handling events above ?
        if not gd.GV_KEEP_RUN:
            # don't touch the display again, just leave
            break

        # build screen (only the areas that changed)
        llst_dirty = _build_screen(lsrf_screen, lv_force)

        # anything changed ?
        if llst_dirty:
            # update only those areas of the display
            pg.display.update(llst_dirty)
            lv_force = False

        # yield to the scheduler
        l_clock.tick(30)

    # quit
    pg.quit()

# ---------------------------------------------------------------------------------------------
def run() -> int:
    """
    entry point (infoView.py, python -m infoview): logging setup (already done by the entry
    points, before importing this module; kept for python -m infoview.app) + main()

    :returns (int): exit code (0: normal end, also on Ctrl-C)
    """
    # logger
    lg.setup()

    try:
        # run application
        main()

    # on error...
    except KeyboardInterrupt:
        # quit pygame
        pg.display.quit()
        # logger
        logging.warning("Interrupted.")

    # normal end
    return 0

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # run application
    sys.exit(run())

# < the end >----------------------------------------------------------------------------------
