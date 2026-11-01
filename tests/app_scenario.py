# -*- coding: utf-8 -*-
"""
infoView tests: end to end scenario, run by tests/test_app.py in a separate interpreter

    python3 -m tests.app_scenario <layout>        # prints one JSON line with what happened

The whole application runs headless at 800x480 against local servers (RSS feed + fake
Open-Meteo, configured through a temporary config file), driven by simulated touches:
show the bar, open the description and the full article, back to titles, quit by holding ⏻.

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import json
import os
import sys
import tempfile
import threading
import time

# tests (sets the test environment: dummy SDL, no IVW_* from the shell)
from tests import support

# < scenario >---------------------------------------------------------------------------------

def main(fs_layout: str) -> int:
    """
    run the scenario; print the result as JSON

    :param fs_layout (str): "sidebar" or "strip"
    """
    # local servers: RSS feed and fake Open-Meteo
    l_srv = support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS),
                                 "/fc": (200, "application/json", support.DBY_FORECAST)}).__enter__()

    # config file: the local feed, fixed coordinates (no geocoding), the layout under test
    ls_dir = tempfile.mkdtemp()
    ls_cfg = os.path.join(ls_dir, "infoView.toml")

    with open(ls_cfg, "w", encoding="utf-8") as l_fp:
        l_fp.write(f'[general]\nlayout = "{fs_layout}"\nscreen = "800x480"\n\n'
                   f'[weather.location]\nname = "Teste"\nlatitude = -22.5\nlongitude = -45.5\n\n'
                   f'[[newsfeed.feeds]]\ntitle = "Local"\nurl = "{l_srv.url("/rss")}"\n')

    # read at import of infoview.core.config
    os.environ["IVW_CONFIG"] = ls_cfg

    # pygame and the application (after the environment is set)
    import pygame as pg
    import infoview.app as app
    import infoview.core.timesync as ts
    import infoview.modules.weather.config as wd

    # clock synchronization: not checkable here (a command that fails) -> trusted
    ts.DLST_COMMAND = ["false"]

    # forecast from the local server
    wd.DS_FORECAST_URL = l_srv.url("/fc")

    # result
    ldct_res = {"layout": fs_layout, "steps": {}}
    llst_requests = []

    # record the state at each step, from the main thread (inside _build_screen)
    lfn_build = app._build_screen

    def lfn_build_and_record(fsrf, fv_force=False):
        llst_dirty = lfn_build(fsrf, fv_force)

        while llst_requests:
            ls_step = llst_requests.pop(0)
            l_nf = app.DDCT_MODULE_VIEWS["newsfeed"]["module"]
            ldct_res["steps"][ls_step] = {"bar": app.M_CONTROLS.v_visible,
                                          "mode": l_nf._dct_article.get("mode"),
                                          "title": l_nf._dct_article.get("title"),
                                          "height": l_nf.i_height}
        return llst_dirty

    app._build_screen = lfn_build_and_record

    # quit long press (sec)
    ctv_hold = app.ctv.DF_QUIT_HOLD

    # button centers (6 equal slots on the 64 px bar)
    li_slot = 800 // 6
    ldct_btn = {ls: (i * li_slot + li_slot // 2, 32) for i, ls in enumerate(["prev", "next", "more", "up", "less", "quit"])}

    def tap(ft_pos):
        pg.event.post(pg.event.Event(pg.MOUSEBUTTONDOWN, pos=ft_pos, button=1))
        time.sleep(.1)
        pg.event.post(pg.event.Event(pg.MOUSEBUTTONUP, pos=ft_pos, button=1))
        time.sleep(.4)

    # touches, from a driver thread (pygame posts are thread safe)
    def driver():
        time.sleep(2.5)                     # feed and weather fetched (local: fast)
        llst_requests.append("start")
        time.sleep(.3)
        tap((400, 300))                     # shows the bar
        llst_requests.append("bar")
        time.sleep(.3)
        tap(ldct_btn["more"])               # description
        llst_requests.append("description")
        time.sleep(.3)
        tap(ldct_btn["more"])               # full article
        llst_requests.append("full")
        time.sleep(.3)
        tap(ldct_btn["less"])               # back to titles
        llst_requests.append("titles")
        time.sleep(.3)
        ldct_res["views"] = {k: list(v["rect"]) for k, v in app.DDCT_MODULE_VIEWS.items()}
        ldct_res["weather"] = app.DDCT_MODULE_VIEWS["weather"]["module"]._dct_data is not None
        tap(ldct_btn["quit"])               # a tap on ⏻ does nothing
        time.sleep(.5)
        ldct_res["after_quit_tap"] = app.gd.GV_KEEP_RUN
        pg.event.post(pg.event.Event(pg.MOUSEBUTTONDOWN, pos=ldct_btn["quit"], button=1))
        time.sleep(ctv_hold + .7)           # held: quits
        pg.event.post(pg.event.Event(pg.MOUSEBUTTONUP, pos=ldct_btn["quit"], button=1))

    threading.Thread(target=driver, daemon=True).start()

    # run (returns when ⏻ is confirmed; a watchdog kills a stuck run)
    threading.Timer(30., lambda: os._exit(3)).start()

    lf_ini = time.monotonic()
    li_rc = app.run()
    ldct_res["seconds"] = round(time.monotonic() - lf_ini, 1)
    ldct_res["rc"] = li_rc

    print(json.dumps(ldct_res))
    sys.stdout.flush()

    # leave now (the watchdog timer and the daemon threads would otherwise keep running)
    os._exit(0)

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    main(sys.argv[1] if len(sys.argv) > 1 else "sidebar")

# < the end >----------------------------------------------------------------------------------
