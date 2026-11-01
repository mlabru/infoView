# -*- coding: utf-8 -*-
"""
tests: on-screen button bar (show / hide, act on release, quit by long press); clock view while
the system clock is not synchronized
"""
# < imports >----------------------------------------------------------------------------------

# python library
import datetime
import unittest

# pygame
import pygame as pg

# infoView
import infoview.core.i18n as i18n
import infoview.core.state as gd
import infoview.core.timesync as ts
import infoview.ui.controls as ctv
import infoview.modules.clock.view as ckv

# < TestControls >-----------------------------------------------------------------------------

class TestControls(unittest.TestCase):
    """SControlsView driven by pointer events (as the main loop does)"""

    @classmethod
    def setUpClass(cls):
        pg.init()

    def setUp(self):
        gd.G_EVENTS.clear()

        # actions emitted
        self._lst_actions = []
        for _, ls_action in ctv.DLST_BUTTONS:
            gd.G_EVENTS.on(ls_action, lambda p, a=ls_action: self._lst_actions.append(a))

        # bar shown (the first touch only shows it)
        self._bar = ctv.SControlsView(800)
        self._tap((400, 300))
        self.assertTrue(self._bar.v_visible)

    def tearDown(self):
        gd.G_EVENTS.clear()

    def _center(self, fs_id):
        return self._bar._dct_rect[fs_id].center

    def _tap(self, ft_pos):
        self._bar.pointer_down(ft_pos)
        self._bar.update()
        self._bar.pointer_up(ft_pos)
        self._bar.update()

    def test_button_acts_on_release(self):
        self._tap(self._center("next"))
        self.assertEqual(self._lst_actions, ["ARTICLE_NEXT"])

        # pressed on one button, released on another: nothing
        self._bar.pointer_down(self._center("prev"))
        self._bar.pointer_up(self._center("more"))
        self.assertEqual(self._lst_actions, ["ARTICLE_NEXT"])

    def test_quit_taps_do_nothing(self):
        # the old confirmation (two taps) must not quit anymore
        self._tap(self._center("quit"))
        self._tap(self._center("quit"))
        self.assertEqual(self._lst_actions, [])

    def test_quit_long_press(self):
        self._bar.pointer_down(self._center("quit"))

        # held, not long enough: filling up, no quit
        self._bar._tm_pressed -= ctv.DF_QUIT_HOLD / 2
        self.assertTrue(self._bar.update())
        self.assertAlmostEqual(self._bar._quit_progress(), .5, places=1)
        self.assertEqual(self._lst_actions, [])

        # held long enough: quits, once
        self._bar._tm_pressed -= ctv.DF_QUIT_HOLD
        self._bar.update()
        self._bar.update()
        self._bar.pointer_up(self._center("quit"))
        self.assertEqual(self._lst_actions, ["APP_QUIT"])

    def test_quit_released_early(self):
        self._bar.pointer_down(self._center("quit"))
        self._bar._tm_pressed -= ctv.DF_QUIT_HOLD - .5
        self._bar.update()
        self._bar.pointer_up(self._center("quit"))
        self._bar.update()

        self.assertEqual(self._lst_actions, [])
        self.assertEqual(self._bar._quit_progress(), 0.)

# < TestClock >--------------------------------------------------------------------------------

class TestClock(unittest.TestCase):
    """SClockView: a notice instead of the date while the clock is not synchronized"""

    @classmethod
    def setUpClass(cls):
        pg.init()

    def tearDown(self):
        ts.GV_SYNCED = True

    def test_unsynced_notice(self):
        l_view = ckv.SClockView(520, 420)
        ldt = datetime.datetime(2026, 10, 31, 12, 0, 0)

        self.assertEqual(l_view._date_text(ldt), i18n.format_date(ldt))

        ts.GV_SYNCED = False
        self.assertEqual(l_view._date_text(ldt), i18n.tr("clock.unsynced"))
        self.assertTrue(l_view.update())

    def _rects(self, fi_w: int, fi_h: int) -> tuple:
        """layout of a clock: (view, time rect, seconds rect) as drawn at 23:59:47"""
        l_view = ckv.SClockView(fi_w, fi_h)
        l_view._build_surface(datetime.datetime(2026, 11, 1, 23, 59, 47))

        lsf_time = l_view._render(l_view._fnt_l2, "23:59", (255, 255, 255))
        lsf_sec = l_view._render(l_view._fnt_sc, "47", (255, 255, 255))

        lrt_time = lsf_time.get_rect(topright=(l_view._i_time_right, l_view._i_time_y))
        lrt_sec = lsf_sec.get_rect(topleft=(l_view._i_sec_x, l_view._i_sec_y))

        return l_view, lrt_time, lrt_sec

    def test_seconds_placement(self):
        # sidebar (520x420): the width limits the time, the seconds go below -> bigger digits
        l_view, lrt_time, lrt_sec = self._rects(520, 420)
        self.assertTrue(l_view._v_sec_below)
        self.assertGreater(l_view._fnt_l2.get_height(), 121)
        self.assertGreaterEqual(lrt_sec.top, lrt_time.bottom)
        self.assertEqual(lrt_sec.right, lrt_time.right)

        # strip (800x324): no room below, the seconds stay beside the time
        l_view, lrt_time, lrt_sec = self._rects(800, 324)
        self.assertFalse(l_view._v_sec_below)
        self.assertGreaterEqual(lrt_sec.left, lrt_time.right)

    def test_layout_fits(self):
        # time and seconds inside the surface, apart, below the date line, at any size
        for li_w, li_h in ((520, 420), (800, 324), (320, 180), (208, 180), (1920, 1020), (300, 60)):
            with self.subTest(size=(li_w, li_h)):
                l_view, lrt_time, lrt_sec = self._rects(li_w, li_h)
                lrt_all = pg.Rect(0, 0, li_w, li_h)

                self.assertTrue(lrt_all.contains(lrt_time))
                self.assertTrue(lrt_all.contains(lrt_sec))
                self.assertFalse(lrt_time.colliderect(lrt_sec))
                self.assertGreaterEqual(lrt_time.top, l_view._i_date_y + l_view._fnt_l1.get_height())
                self.assertTrue(1. <= l_view._f_stretch <= ckv.DF_TIME_STRETCH)

    def test_stretch(self):
        # the digits are stretched by DF_TIME_STRETCH when there is room (sidebar), never more
        l_view, lrt_time, _ = self._rects(520, 420)
        self.assertEqual(l_view._f_stretch, ckv.DF_TIME_STRETCH)
        self.assertEqual(lrt_time.height, round(l_view._fnt_l2.size("23:59")[1] * ckv.DF_TIME_STRETCH))

    def test_render_cache(self):
        # each text rendered (and stretched) once; the cache never grows past DI_CACHE_MAX
        l_view = ckv.SClockView(520, 420)
        self.assertIs(l_view._render(l_view._fnt_sc, "47", (1, 2, 3)),
                      l_view._render(l_view._fnt_sc, "47", (1, 2, 3)))

        for li_min in range(2 * ckv.DI_CACHE_MAX):
            l_view._render(l_view._fnt_l2, f"0:{li_min:02d}", (1, 2, 3))

        self.assertLessEqual(len(l_view._dct_cache), ckv.DI_CACHE_MAX)

# < the end >----------------------------------------------------------------------------------
