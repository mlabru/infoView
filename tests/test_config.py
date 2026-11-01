# -*- coding: utf-8 -*-
"""
tests: user configuration file (infoview/core/config.py) and general settings precedence
(infoview/core/settings.py)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import json
import os
import subprocess
import sys
import tempfile
import unittest

# infoView
import infoview.core.config as cfg

# < constants >--------------------------------------------------------------------------------

# project root (subprocesses run from there)
DS_ROOT = cfg.DS_ROOT_DIR

# ---------------------------------------------------------------------------------------------
def _settings_in_subprocess(fdct_env: dict, fs_toml: str = None) -> dict:
    """
    import infoview.core.settings in a fresh interpreter (the settings are resolved at import)
    with the given environment and config file contents; return the general settings
    """
    ldct_env = {k: v for k, v in os.environ.items() if not k.startswith("IVW_")}
    ldct_env.update(fdct_env)

    with tempfile.TemporaryDirectory() as ls_dir:
        ls_file = os.path.join(ls_dir, "infoView.toml")

        if fs_toml is not None:
            with open(ls_file, "w", encoding="utf-8") as l_fp:
                l_fp.write(fs_toml)

        ldct_env["IVW_CONFIG"] = ls_file

        ls_code = ("import json, infoview.core.settings as df, infoview.core.i18n as i18n;"
                   "print(json.dumps({'layout': df.DS_LAYOUT, 'language': i18n.DS_LANGUAGE,"
                   " 'theme': df.DS_THEME, 'screen': df.DS_SCREEN, 'clock_check': df.DV_CLOCK_CHECK}))")
        l_res = subprocess.run([sys.executable, "-c", ls_code], cwd=DS_ROOT, env=ldct_env,
                               capture_output=True, text=True, check=True)

    return json.loads(l_res.stdout.strip().splitlines()[-1])

# < TestMerge >--------------------------------------------------------------------------------

class TestMerge(unittest.TestCase):
    """cfg.merge: validation of the user's values against the code defaults"""

    DDCT_DEFAULTS = {"name": "x", "count": 10, "ratio": .5, "flag": False, "lat": None,
                     "items": [1, 2], "sub": {"a": "b", "n": 1}}

    def test_override_and_defaults_kept(self):
        ldct = cfg.merge(self.DDCT_DEFAULTS, {"name": "y", "count": 3}, "t")
        self.assertEqual(ldct["name"], "y")
        self.assertEqual(ldct["count"], 3)
        self.assertEqual(ldct["ratio"], .5)

    def test_defaults_not_modified(self):
        cfg.merge(self.DDCT_DEFAULTS, {"name": "y", "sub": {"a": "z"}}, "t")
        self.assertEqual(self.DDCT_DEFAULTS["name"], "x")
        self.assertEqual(self.DDCT_DEFAULTS["sub"]["a"], "b")

    def test_unknown_key_ignored_and_logged(self):
        with self.assertLogs("infoview.core.config", "WARNING") as l_log:
            ldct = cfg.merge(self.DDCT_DEFAULTS, {"nmae": "typo"}, "t")
        self.assertNotIn("nmae", ldct)
        self.assertIn("unknown key t.nmae", l_log.output[0])

    def test_wrong_type_ignored_and_logged(self):
        with self.assertLogs("infoview.core.config", "WARNING") as l_log:
            ldct = cfg.merge(self.DDCT_DEFAULTS, {"count": "ten", "flag": 1, "items": "x"}, "t")
        self.assertEqual((ldct["count"], ldct["flag"], ldct["items"]), (10, False, [1, 2]))
        self.assertEqual(len(l_log.output), 3)

    def test_type_rules(self):
        # int where float is expected; number where the default is None (not set)
        ldct = cfg.merge(self.DDCT_DEFAULTS, {"ratio": 2, "lat": -23.5}, "t")
        self.assertEqual((ldct["ratio"], ldct["lat"]), (2, -23.5))

        # bool is not an int, text is not a coordinate
        with self.assertLogs("infoview.core.config", "WARNING"):
            ldct = cfg.merge(self.DDCT_DEFAULTS, {"count": True, "lat": "-23.5"}, "t")
        self.assertEqual((ldct["count"], ldct["lat"]), (10, None))

    def test_nested_and_lists(self):
        ldct = cfg.merge(self.DDCT_DEFAULTS, {"sub": {"n": 5}, "items": [9]}, "t")
        self.assertEqual(ldct["sub"], {"a": "b", "n": 5})
        self.assertEqual(ldct["items"], [9])

        with self.assertLogs("infoview.core.config", "WARNING"):
            ldct = cfg.merge(self.DDCT_DEFAULTS, {"sub": "not a table"}, "t")
        self.assertEqual(ldct["sub"], {"a": "b", "n": 1})

    def test_value_rules(self):
        ldct_rules = {"count": {"min": 1, "max": 20}, "name": {"choices": ["x", "y"]},
                      "items": {"items": int}, "sub": {"n": {"min": 0}}}

        # inside the rules
        ldct = cfg.merge(self.DDCT_DEFAULTS, {"count": 20, "name": "y", "items": [3], "sub": {"n": 0}}, "t", ldct_rules)
        self.assertEqual((ldct["count"], ldct["name"], ldct["items"], ldct["sub"]["n"]), (20, "y", [3], 0))

        # out of them: logged, default kept; a list keeps its good items
        with self.assertLogs("infoview.core.config", "WARNING") as l_log:
            ldct = cfg.merge(self.DDCT_DEFAULTS, {"count": 0, "name": "z", "items": [3, "4", True, 5],
                                                  "sub": {"n": -1}}, "t", ldct_rules)
        self.assertEqual((ldct["count"], ldct["name"], ldct["items"], ldct["sub"]["n"]), (10, "x", [3, 5], 1))
        self.assertEqual(len(l_log.output), 5)
        self.assertIn("t.count = 0 ignored (minimum 1)", l_log.output[0])
        self.assertIn("t.sub.n = -1 ignored (minimum 0)", l_log.output[-1])

        with self.assertLogs("infoview.core.config", "WARNING"):
            self.assertEqual(cfg.merge(self.DDCT_DEFAULTS, {"count": 21}, "t", ldct_rules)["count"], 10)

    def test_module_rules(self):
        import infoview.modules.newsfeed.config as nd
        import infoview.modules.weather.config as wd

        # values of the right type that make no sense: the defaults are used
        ldct_bad = {"updateInterval": 0, "detailsTimeout": -1, "scrollLength": -100, "ignoreOlderThan": -5,
                    "maxNewsItems": -1, "reloadInterval": 1, "removeStartTags": "yes",
                    "startTags": [1, "AO VIVO: "], "prohibitedWords": [2]}

        with self.assertLogs("infoview.core.config", "WARNING"):
            ldct = cfg.merge(nd.DDCT_DEFAULTS, ldct_bad, "newsfeed", nd.DDCT_RULES)

        for ls_key in ("updateInterval", "detailsTimeout", "scrollLength", "ignoreOlderThan", "maxNewsItems",
                       "reloadInterval", "removeStartTags", "prohibitedWords"):
            self.assertEqual(ldct[ls_key], nd.DDCT_DEFAULTS[ls_key], ls_key)
        self.assertEqual(ldct["startTags"], ["AO VIVO: "])

        with self.assertLogs("infoview.core.config", "WARNING") as l_log:
            ldct = cfg.merge(wd.DDCT_DEFAULTS, {"units": {"temperature": "kelvin", "wind": "ms"}, "reloadInterval": 60,
                                                "location": {"latitude": -123.5}, "staleAfter": 0},
                             "weather", wd.DDCT_RULES)
        self.assertEqual(ldct["units"], dict(wd.DDCT_DEFAULTS["units"], wind="ms"))
        self.assertEqual((ldct["reloadInterval"], ldct["location"]["latitude"], ldct["staleAfter"]),
                         (wd.DDCT_DEFAULTS["reloadInterval"], None, wd.DDCT_DEFAULTS["staleAfter"]))
        self.assertEqual(len(l_log.output), 4)

    def test_valid_feeds(self):
        import infoview.modules.newsfeed.config as nd

        llst = [{"url": "http://a"}, {"url": "http://b", "reloadInterval": 300}, {"url": "http://c", "reloadInterval": 10},
                {"url": "http://d", "reloadInterval": True}, {"title": "no url"}, "http://e"]

        with self.assertLogs("infoview.modules.newsfeed.config", "WARNING") as l_log:
            self.assertEqual(nd._valid_feeds(llst), llst[:2])
        self.assertEqual(len(l_log.output), 4)

# < TestLoad >---------------------------------------------------------------------------------

class TestLoad(unittest.TestCase):
    """cfg.load: reading the TOML file"""

    def test_missing_file(self):
        self.assertEqual(cfg.load("/nonexistent/infoView.toml"), {})

    def test_invalid_toml_logged(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as l_fp:
            l_fp.write("[general\nlayout = ")

        try:
            with self.assertLogs("infoview.core.config", "ERROR"):
                self.assertEqual(cfg.load(l_fp.name), {})
        finally:
            os.unlink(l_fp.name)

    def test_example_file_is_the_defaults(self):
        # infoView.example.toml documents the defaults: loading it changes nothing
        import infoview.core.settings as df
        import infoview.modules.newsfeed.config as nd
        import infoview.modules.weather.config as wd

        ldct = cfg.load(os.path.join(DS_ROOT, "infoView.example.toml"))

        self.assertEqual(cfg.merge(nd.DDCT_DEFAULTS, ldct["newsfeed"], "newsfeed", nd.DDCT_RULES), nd.DDCT_DEFAULTS)
        self.assertEqual(cfg.merge(wd.DDCT_DEFAULTS, ldct["weather"], "weather", wd.DDCT_RULES), wd.DDCT_DEFAULTS)
        self.assertEqual(ldct["general"], {k: d for k, (_, d) in df.DDCT_GENERAL.items()})

# < TestPrecedence >---------------------------------------------------------------------------

class TestPrecedence(unittest.TestCase):
    """general settings: environment > config file > default (fresh interpreter each)"""

    def test_defaults(self):
        self.assertEqual(_settings_in_subprocess({}),
                         {"layout": "sidebar", "language": "pt_BR", "theme": "color", "screen": "", "clock_check": True})

    def test_file_over_default(self):
        ldct = _settings_in_subprocess({}, '[general]\nlayout = "strip"\nlanguage = "en"\ntheme = "mono"\n')
        self.assertEqual((ldct["layout"], ldct["language"], ldct["theme"]), ("strip", "en", "mono"))

    def test_environment_over_file(self):
        ldct = _settings_in_subprocess({"IVW_LAYOUT": "sidebar", "IVW_SCREEN": "800x480"},
                                       '[general]\nlayout = "strip"\n')
        self.assertEqual((ldct["layout"], ldct["screen"]), ("sidebar", "800x480"))

    def test_clock_check(self):
        self.assertFalse(_settings_in_subprocess({}, '[general]\nclock_check = false\n')["clock_check"])
        self.assertFalse(_settings_in_subprocess({"IVW_CLOCK_CHECK": "no"})["clock_check"])
        self.assertTrue(_settings_in_subprocess({"IVW_CLOCK_CHECK": "1"}, '[general]\nclock_check = false\n')["clock_check"])
        # invalid: the default (checked)
        self.assertTrue(_settings_in_subprocess({"IVW_CLOCK_CHECK": "maybe"})["clock_check"])

    def test_screen(self):
        self.assertEqual(_settings_in_subprocess({"IVW_SCREEN": "320X240"})["screen"], "320X240")

        # not WxH, or too small (the app would crash): the display size
        for ls_screen in ("100x50", "0x0", "800*480", "800x480x2", "800x"):
            self.assertEqual(_settings_in_subprocess({}, f'[general]\nscreen = "{ls_screen}"\n')["screen"], "", ls_screen)

    def test_log_format_at_import(self):
        # as the entry points do: log format first, then the settings (config read at import)
        with tempfile.TemporaryDirectory() as ls_dir:
            ls_file = os.path.join(ls_dir, "infoView.toml")
            with open(ls_file, "w", encoding="utf-8") as l_fp:
                l_fp.write('[general]\nscreen = "1x1"\n')

            ldct_env = {k: v for k, v in os.environ.items() if not k.startswith("IVW_")}
            ldct_env["IVW_CONFIG"] = ls_file
            l_res = subprocess.run([sys.executable, "-c", "import infoview.core.logsetup as lg; lg.setup();"
                                    " import infoview.core.settings"],
                                   cwd=DS_ROOT, env=ldct_env, capture_output=True, text=True, check=True)

        # date and time with seconds, level, module
        self.assertRegex(l_res.stderr, r"(?m)^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d ERROR infoview\.core\.settings: invalid screen '1x1'")

    def test_invalid_values_fall_back_to_defaults(self):
        ldct = _settings_in_subprocess({}, '[general]\nlayout = "diagonal"\nlanguage = "fr"\ntheme = "neon"\n')
        self.assertEqual((ldct["layout"], ldct["language"], ldct["theme"]), ("sidebar", "pt_BR", "color"))

# < the end >----------------------------------------------------------------------------------
