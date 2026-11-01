# -*- coding: utf-8 -*-
"""
tests: the whole application, end to end (tests/app_scenario.py in a separate interpreter:
the app reads its settings at import and runs pygame in the main thread)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import json
import os
import subprocess
import sys
import unittest

# infoView
import infoview.core.config as cfg

# ---------------------------------------------------------------------------------------------
def _run_scenario(fs_layout: str) -> dict:
    """run the scenario for a layout, return its JSON result"""
    l_res = subprocess.run([sys.executable, "-m", "tests.app_scenario", fs_layout], cwd=cfg.DS_ROOT_DIR,
                           env=dict(os.environ), capture_output=True, text=True, timeout=60)

    assert 0 == l_res.returncode, f"scenario failed (rc {l_res.returncode}):\n{l_res.stderr[-2000:]}"

    return json.loads(l_res.stdout.strip().splitlines()[-1])

# < TestApp >----------------------------------------------------------------------------------

class TestApp(unittest.TestCase):
    """touch scenario on the 800x480 screen, both layouts"""

    def _check_common(self, fdct):
        ldct = fdct["steps"]

        # the feed and the weather arrived (local servers)
        self.assertEqual(ldct["start"]["title"], "Notícia & acentuação")
        self.assertTrue(fdct["weather"])

        # first touch only shows the bar; then description, full article, back to titles
        self.assertEqual((ldct["start"]["bar"], ldct["bar"]["bar"], ldct["bar"]["mode"]), (False, True, "title"))
        self.assertEqual(ldct["description"]["mode"], "description")
        self.assertEqual((ldct["full"]["mode"], ldct["full"]["height"]), ("full", 480 - 64))
        self.assertEqual((ldct["titles"]["mode"], ldct["titles"]["height"]), ("title", 60))

        # a tap on ⏻ doesn't quit; holding it does: normal end
        self.assertTrue(fdct["after_quit_tap"])
        self.assertEqual(fdct["rc"], 0)

    def test_sidebar(self):
        ldct = _run_scenario("sidebar")
        self._check_common(ldct)

        self.assertEqual(ldct["views"], {"clock": [0, 0, 520, 420], "weather": [520, 0, 280, 420],
                                         "newsfeed": [0, 420, 800, 60]})
        # sidebar: details always use the whole reading pane
        self.assertEqual(ldct["steps"]["description"]["height"], 480 - 64)

    def test_strip(self):
        ldct = _run_scenario("strip")
        self._check_common(ldct)

        self.assertEqual(ldct["views"], {"clock": [0, 0, 800, 324], "weather": [0, 324, 800, 96],
                                         "newsfeed": [0, 420, 800, 60]})
        # strip: the description covers at least the weather strip + ticker
        self.assertGreaterEqual(ldct["steps"]["description"]["height"], 96 + 60)

# < the end >----------------------------------------------------------------------------------
