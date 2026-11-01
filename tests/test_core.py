# -*- coding: utf-8 -*-
"""
tests: core pieces — i18n (texts / dates), theme colors, font fitting, event bus, retry delay,
clock synchronization
"""
# < imports >----------------------------------------------------------------------------------

# python library
import datetime
import time
import unittest

# pygame
import pygame as pg

# infoView
import infoview.core.events as evt
import infoview.core.i18n as i18n
import infoview.core.net as hp
import infoview.core.settings as df
import infoview.core.timesync as ts
import infoview.ui.fonts as vu

# < TestI18n >---------------------------------------------------------------------------------

class TestI18n(unittest.TestCase):
    """texts per language"""

    def tearDown(self):
        i18n.DS_LANGUAGE = "pt_BR"

    def test_same_keys_in_every_language(self):
        # a key missing in one language would silently fall back to English
        ls_ref = set(i18n.DDCT_TEXTS["en"])

        for ls_lang, ldct in i18n.DDCT_TEXTS.items():
            self.assertEqual(set(ldct), ls_ref, f"keys differ in {ls_lang}")

            # same shape: lists of the same length, plurals as (singular, plural)
            for ls_key, l_val in ldct.items():
                l_ref = i18n.DDCT_TEXTS["en"][ls_key]
                self.assertIs(type(l_val), type(l_ref), f"{ls_lang}.{ls_key}")
                if isinstance(l_val, (list, tuple)):
                    self.assertEqual(len(l_val), len(l_ref), f"{ls_lang}.{ls_key}")

    def test_normalize(self):
        for ls_in, ls_out in (("pt_BR", "pt_BR"), ("pt-br", "pt_BR"), ("pt", "pt_BR"), ("en", "en"),
                              ("en_US", "en"), ("EN", "en")):
            self.assertEqual(i18n.normalize(ls_in), ls_out, ls_in)

        with self.assertLogs("infoview.core.i18n", "ERROR"):
            self.assertEqual(i18n.normalize("fr"), "pt_BR")

    def test_format_date(self):
        ldt = datetime.date(2026, 10, 31)

        i18n.DS_LANGUAGE = "pt_BR"
        self.assertEqual(i18n.format_date(ldt), "Sábado, 31 de outubro de 2026")

        i18n.DS_LANGUAGE = "en"
        self.assertEqual(i18n.format_date(ldt), "Saturday, October 31, 2026")

    def test_plural(self):
        i18n.DS_LANGUAGE = "pt_BR"
        self.assertEqual(i18n.tr_n("nf.minutes_ago", 1), "há 1 minuto")
        self.assertEqual(i18n.tr_n("nf.hours_ago", 3), "há 3 horas")

        i18n.DS_LANGUAGE = "en"
        self.assertEqual(i18n.tr_n("nf.days_ago", 1), "1 day ago")

    def test_missing_key_falls_back(self):
        self.assertEqual(i18n.tr("no.such.key"), "no.such.key")

# < TestTheme >--------------------------------------------------------------------------------

class TestTheme(unittest.TestCase):
    """temperature colors (color theme, the default)"""

    def test_stops_and_ends(self):
        for lf_t, lt_clr in df.DLST_TEMP_STOPS:
            self.assertEqual(df.temp_color(lf_t), lt_clr)

        # beyond the ends: the end colors
        self.assertEqual(df.temp_color(-30), df.DLST_TEMP_STOPS[0][1])
        self.assertEqual(df.temp_color(50), df.DLST_TEMP_STOPS[-1][1])

    def test_interpolation(self):
        # half way between 25 °C (255, 215, 140) and 30 °C (255, 170, 90)
        self.assertEqual(df.temp_color(27.5), (255, 192, 115))

    def test_unknown_temperature(self):
        self.assertEqual(df.temp_color(None), df.DCLR_TIME)

# < TestFonts >--------------------------------------------------------------------------------

class TestFonts(unittest.TestCase):
    """font fitting (infoview/ui/fonts.py)"""

    @classmethod
    def setUpClass(cls):
        pg.font.init()

    def test_fit_text(self):
        lfnt = vu.font(df.DS_FONT_TEXT, 20)

        # fits: unchanged
        self.assertEqual(vu.fit_text(lfnt, "curto", 500), "curto")

        # too long: cut with an ellipsis, within the width
        ls = vu.fit_text(lfnt, "um texto bem comprido " * 10, 200)
        self.assertTrue(ls.endswith("…"))
        self.assertLessEqual(lfnt.size(ls)[0], 200)

    def test_fit_size_all(self):
        llst = ["Chance de chuva 100%", "Umidade 97%"]
        li_sz = vu.fit_size_all(df.DS_FONT_TEXT, llst, 150, 40)

        # every line fits at that size, and not at the next one
        lfnt = vu.font(df.DS_FONT_TEXT, li_sz)
        self.assertTrue(all(lfnt.size(t)[0] <= 150 for t in llst))
        self.assertTrue(any(vu.font(df.DS_FONT_TEXT, li_sz + 1).size(t)[0] > 150 for t in llst))

    def test_font_cache(self):
        self.assertIs(vu.font(df.DS_FONT_TEXT, 17), vu.font(df.DS_FONT_TEXT, 17))

    def test_resources_exist(self):
        for ls_path in (df.DS_FONT_TEXT, df.DS_FONT_DIGITAL, df.DS_ICON_APP):
            with open(ls_path, "rb"):
                pass

# < TestEvents >-------------------------------------------------------------------------------

class TestEvents(unittest.TestCase):
    """event bus"""

    def tearDown(self):
        evt.SEventHandler().clear()

    def test_singleton_and_order(self):
        l_bus = evt.SEventHandler()
        self.assertIs(l_bus, evt.SEventHandler())

        llst = []
        l_bus.on("t", lambda p: llst.append(("a", p["x"])))
        l_bus.on("t", lambda p: llst.append(("b", p["x"])))
        l_bus.emit("t", {"x": 1})
        l_bus.emit("nobody_listens", {})

        self.assertEqual(llst, [("a", 1), ("b", 1)])

# < TestRetry >--------------------------------------------------------------------------------

class TestRetry(unittest.TestCase):
    """polling loops: sooner retries after failures"""

    def test_retry_delay(self):
        # success: the normal interval
        self.assertEqual(hp.retry_delay(0, 900), 900)
        # failures: 30, 60, 120, ... never later than the interval
        self.assertEqual([hp.retry_delay(n, 900) for n in (1, 2, 3, 5, 6, 1000)], [30, 60, 120, 480, 900, 900])
        # interval shorter than the first retry
        self.assertEqual(hp.retry_delay(1, 20), 20)

# < TestTimesync >-----------------------------------------------------------------------------

class TestTimesync(unittest.TestCase):
    """system clock synchronized ? (timedatectl replaced by shell commands)"""

    def setUp(self):
        self._saved = (ts.DLST_COMMAND, ts.DF_POLL, ts.DI_UNKNOWN_MAX, ts.GV_SYNCED)

    def tearDown(self):
        ts.DLST_COMMAND, ts.DF_POLL, ts.DI_UNKNOWN_MAX, ts.GV_SYNCED = self._saved

    def test_check_answers(self):
        for ls_cmd, l_expected in (("echo yes", True), ("echo no", False), ("echo maybe", None), ("exit 1", None)):
            ts.DLST_COMMAND = ["sh", "-c", ls_cmd]
            self.assertIs(ts.check(), l_expected, ls_cmd)

        # no timedatectl at all
        ts.DLST_COMMAND = ["/nonexistent/timedatectl"]
        self.assertIsNone(ts.check())

    def test_start_synced(self):
        ts.DLST_COMMAND = ["sh", "-c", "echo yes"]
        self.assertIsNone(ts.start())
        self.assertTrue(ts.GV_SYNCED)

    def test_start_unknown_trusted_after_retries(self):
        # can't tell (no timedatectl, error): trusted meanwhile, asked again a few times
        ts.DLST_COMMAND, ts.DF_POLL, ts.DI_UNKNOWN_MAX = ["sh", "-c", "exit 1"], .02, 3
        l_thread = ts.start()
        self.assertTrue(ts.GV_SYNCED)

        l_thread.join(5.)
        self.assertFalse(l_thread.is_alive())
        self.assertTrue(ts.GV_SYNCED)

    def test_start_unknown_then_not_synced(self):
        # at boot timedatectl fails (dbus not up yet), then answers "no": not trusted for good
        ts.DLST_COMMAND, ts.DF_POLL = ["sh", "-c", "exit 1"], .05
        l_thread = ts.start()
        self.assertTrue(ts.GV_SYNCED)

        ts.DLST_COMMAND = ["sh", "-c", "echo no"]
        time.sleep(.5)
        self.assertFalse(ts.GV_SYNCED)

        # NTP sets the clock
        ts.DLST_COMMAND = ["sh", "-c", "echo yes"]
        l_thread.join(5.)
        self.assertFalse(l_thread.is_alive())
        self.assertTrue(ts.GV_SYNCED)

    def test_start_not_checked(self):
        # clock_check = false: the clock is trusted, timedatectl is not even asked
        ts.DLST_COMMAND = ["sh", "-c", "echo no"]
        self.assertIsNone(ts.start(False))
        self.assertTrue(ts.GV_SYNCED)

    def test_start_waits_for_sync(self):
        ts.DLST_COMMAND, ts.DF_POLL = ["sh", "-c", "echo no"], .05
        l_thread = ts.start()
        self.assertFalse(ts.GV_SYNCED)

        # NTP sets the clock
        ts.DLST_COMMAND = ["sh", "-c", "echo yes"]
        l_thread.join(5.)

        self.assertFalse(l_thread.is_alive())
        self.assertTrue(ts.GV_SYNCED)

# < the end >----------------------------------------------------------------------------------
