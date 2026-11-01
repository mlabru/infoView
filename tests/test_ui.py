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

# < the end >----------------------------------------------------------------------------------
