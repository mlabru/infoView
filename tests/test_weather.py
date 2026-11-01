# -*- coding: utf-8 -*-
"""
tests: weather module — fetcher (against a local fake Open-Meteo) and view (texts never cut,
icons, states)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import copy
import time
import unittest

# pygame
import pygame as pg

# infoView
import infoview.core.i18n as i18n
import infoview.core.state as gd
import infoview.ui.fonts as vu
import infoview.modules.weather.config as wd
import infoview.modules.weather.fetcher as wtf
import infoview.modules.weather.view as wtv

# tests
from tests import support

# < TestWeatherFetcher >-----------------------------------------------------------------------

class TestWeatherFetcher(unittest.TestCase):
    """SWeatherFetcher.fetch_once against local servers (no internet)"""

    def setUp(self):
        gd.G_EVENTS.clear()
        self._lst_ev = []
        gd.G_EVENTS.on("WEATHER_DATA", lambda p: self._lst_ev.append(("data", p)))
        gd.G_EVENTS.on("WEATHER_ERROR", lambda p: self._lst_ev.append(("error", p)))

        # keep the module URLs
        self._urls = (wd.DS_FORECAST_URL, wd.DS_GEOCODING_URL)

    def tearDown(self):
        wd.DS_FORECAST_URL, wd.DS_GEOCODING_URL = self._urls
        gd.G_EVENTS.clear()

    def _config(self, **location):
        ldct = copy.deepcopy(wd.DDCT_DEFAULTS)
        ldct["location"].update(location)
        return ldct

    def test_geocoding_and_forecast(self):
        with support.LocalServer({"/geo": (200, "application/json", support.DBY_GEOCODING),
                                  "/fc": (200, "application/json", support.DBY_FORECAST)}) as l_srv:
            wd.DS_GEOCODING_URL, wd.DS_FORECAST_URL = l_srv.url("/geo"), l_srv.url("/fc")
            ldct = wtf.SWeatherFetcher(self._config(name="Cidade Teste")).fetch_once()

        self.assertEqual(self._lst_ev[-1][0], "data")
        self.assertEqual(ldct["place"], "Cidade Teste, Estado Teste")
        self.assertEqual((ldct["temp"], ldct["feels"], ldct["humidity"], ldct["code"]), (23.4, 25.1, 70, 2))
        self.assertEqual((ldct["tmin"], ldct["tmax"], ldct["rain_sum"], ldct["rain_prob"]), (15.0, 27.0, 2.2, 40))
        self.assertTrue(ldct["is_day"])

    def test_fixed_coordinates_skip_geocoding(self):
        # no geocoding route: it must not be called
        with support.LocalServer({"/fc": (200, "application/json", support.DBY_FORECAST)}) as l_srv:
            wd.DS_GEOCODING_URL, wd.DS_FORECAST_URL = l_srv.url("/nogeo"), l_srv.url("/fc")
            ldct = wtf.SWeatherFetcher(self._config(name="Meu sítio", latitude=-22.9, longitude=-43.2)).fetch_once()

        self.assertEqual(ldct["place"], "Meu sítio")

    def test_errors_keep_last_data(self):
        with support.LocalServer({"/fc": (200, "application/json", support.DBY_FORECAST)}) as l_srv:
            wd.DS_FORECAST_URL = l_srv.url("/fc")
            l_ftc = wtf.SWeatherFetcher(self._config(latitude=1., longitude=2.))
            ldct_good = l_ftc.fetch_once()

            # HTTP 404
            wd.DS_FORECAST_URL = l_srv.url("/missing")
            self.assertIsNone(l_ftc.fetch_once())
            self.assertEqual(self._lst_ev[-1], ("error", {"code": "404", "message": "HTTP 404"}))

        # connection refused
        wd.DS_FORECAST_URL = support.closed_port_url("/fc")
        self.assertIsNone(l_ftc.fetch_once())
        self.assertEqual(self._lst_ev[-1][1]["code"], "URLError")

        # the last good data is still the one kept
        self.assertIs(l_ftc._dct_data, ldct_good)

    def test_cycle_survives_listener_error(self):
        gd.G_EVENTS.on("WEATHER_DATA", lambda p: 1 / 0)

        with support.LocalServer({"/fc": (200, "application/json", support.DBY_FORECAST)}) as l_srv:
            wd.DS_FORECAST_URL = l_srv.url("/fc")
            l_ftc = wtf.SWeatherFetcher(self._config(latitude=1., longitude=2.))

            # logged, not raised: the thread would keep polling (and retries sooner)
            self.assertFalse(l_ftc._cycle())

        self.assertIsNotNone(l_ftc._dct_data)

    def test_place_not_found(self):
        with support.LocalServer({"/geo": (200, "application/json", b'{"results": []}')}) as l_srv:
            wd.DS_GEOCODING_URL = l_srv.url("/geo")
            self.assertIsNone(wtf.SWeatherFetcher(self._config(name="Lugar inexistente")).fetch_once())

        self.assertEqual(self._lst_ev[-1][1]["code"], "LookupError")

    def test_timeout(self):
        lf_timeout = wtf.DF_FETCH_TIMEOUT

        try:
            wtf.DF_FETCH_TIMEOUT = 1.
            with support.MuteServer() as l_srv:
                wd.DS_FORECAST_URL = l_srv.url("/fc")
                lf_ini = time.monotonic()
                self.assertIsNone(wtf.SWeatherFetcher(self._config(latitude=1., longitude=2.)).fetch_once())
                self.assertLess(time.monotonic() - lf_ini, 5.)
        finally:
            wtf.DF_FETCH_TIMEOUT = lf_timeout

        self.assertEqual(self._lst_ev[-1][1]["code"], "URLError")

# < TestWeatherView >--------------------------------------------------------------------------

# worst case texts: long condition, place, values with many digits, old data
DDCT_WORST = {"place": "São José dos Campos, São Paulo", "temp": -12.4, "feels": -18.1, "humidity": 100,
              "wind": 112.3, "wind_dir": 315, "gust": 140, "tmin": -20, "tmax": -5, "rain_sum": 125.4,
              "rain_prob": 100, "wind_unit": "km/h", "precip_unit": "mm", "is_day": True, "code": 96,
              "temp_unit": "°C"}

class TestWeatherView(unittest.TestCase):
    """SWeatherView: weather texts are never cut at 800x480 (both styles, both languages)"""

    @classmethod
    def setUpClass(cls):
        pg.init()

    def setUp(self):
        gd.G_EVENTS.clear()

        # record every text that had to be cut
        self._lst_cuts = []
        self._fit_text = vu.fit_text
        vu.fit_text = lambda f, t, w: (self._lst_cuts.append(t), self._fit_text(f, t, w))[1]

    def tearDown(self):
        vu.fit_text = self._fit_text
        i18n.DS_LANGUAGE = "pt_BR"
        gd.G_EVENTS.clear()

    def _draw(self, fs_style, fi_w, fi_h, fdct=None, fs_error=None):
        l_view = wtv.SWeatherView(fi_w, fi_h, fs_style)

        if fdct is not None:
            l_view.on_weather_data(fdct)
        if fs_error is not None:
            l_view.on_weather_error({"code": fs_error})

        self.assertTrue(l_view.update())
        return l_view

    def test_no_cuts_worst_case(self):
        for ls_lang in ("pt_BR", "en"):
            i18n.DS_LANGUAGE = ls_lang

            for ls_style, li_w, li_h in (("strip", 800, 96), ("sidebar", 280, 420)):
                for lf_age in (0, 125 * 60):
                    self._draw(ls_style, li_w, li_h, dict(DDCT_WORST, fetched=time.monotonic() - lf_age))

                for ls_error in ("URLError", "LookupError", "503", "JSONDecodeError"):
                    self._draw(ls_style, li_w, li_h, fs_error=ls_error)
                self._draw(ls_style, li_w, li_h)

        self.assertEqual(self._lst_cuts, [])

    def test_every_weather_code_draws(self):
        for li_code in list(wtv.DDCT_WMO) + [12345]:
            for lv_day in (True, False):
                self._draw("sidebar", 280, 420, dict(DDCT_WORST, code=li_code, is_day=lv_day, fetched=time.monotonic()))

    def test_update_only_when_changed(self):
        l_view = self._draw("strip", 800, 96, dict(DDCT_WORST, fetched=time.monotonic()))

        # nothing new: no redraw
        self.assertFalse(l_view.update())

        # new data: redraw
        l_view.on_weather_data(dict(DDCT_WORST, temp=30, fetched=time.monotonic()))
        self.assertTrue(l_view.update())

    def test_error_reasons(self):
        i18n.DS_LANGUAGE = "pt_BR"
        l_view = wtv.SWeatherView(800, 96, "strip")
        ls_place = l_view._dct_config["location"]["name"]

        self.assertEqual([l_view._error_reason(c) for c in ("URLError", "LookupError", "400", "ValueError")],
                         ["sem conexão", f"local não encontrado: {ls_place}", "erro HTTP 400", "resposta inválida"])

    def test_fresh_data_not_stale(self):
        # old data: grey, with its age
        l_view = self._draw("strip", 800, 96, dict(DDCT_WORST, fetched=time.monotonic() - 60 * 60))
        self.assertTrue(l_view._v_stale)

        # fresh data right after (before the next periodic check): not old anymore at once
        l_view.on_weather_data(dict(DDCT_WORST, fetched=time.monotonic()))
        self.assertTrue(l_view.update())
        self.assertFalse(l_view._v_stale)

    def test_compass(self):
        i18n.DS_LANGUAGE = "pt_BR"
        self.assertEqual([wtv.SWeatherView._compass(d) for d in (0, 45, 90, 180, 270, 315, 359)],
                         ["N", "NE", "L", "S", "O", "NO", "N"])

# < the end >----------------------------------------------------------------------------------
