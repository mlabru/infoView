# -*- coding: utf-8 -*-
"""
infoView 1.0
Weather / WeatherFetcher

polls Open-Meteo (current conditions + today's min/max/rain) on an interval and emits a compact
dict as WEATHER_DATA (errors as WEATHER_ERROR, keeping the last good data). Runs in its own
daemon thread: listeners get the data in this thread and must not render from the callback.

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import json
import logging
import sys
import threading
import time
import urllib.parse

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.net as hp
import infoview.core.i18n as i18n

# weather
import infoview.modules.weather.config as wd

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# network timeout for one request (sec)
DF_FETCH_TIMEOUT = 30.

# current conditions / daily values requested
DS_CURRENT = "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code," \
             "wind_speed_10m,wind_direction_10m,wind_gusts_10m,is_day"
DS_DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max"

# < SWeatherFetcher >--------------------------------------------------------------------------

class SWeatherFetcher(threading.Thread):
    """
    weather fetcher thread (see the module docstring): fetch_once() every reloadInterval
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fdct_config: dict = None):
        """
        constructor

        :param fdct_config (dict): weather config (default: weather/config.py defaults)
        """
        # logger
        M_LOG.info(">> constructor")

        # init super class
        super().__init__()

        # daemon thread, so a pending sleep doesn't hold the process on exit
        self.daemon = True

        # config
        self._dct_config: dict = fdct_config or wd.DDCT_CONFIG

        # location (from the config; latitude / longitude filled in by geocoding if needed)
        ldct_loc = self._dct_config["location"]

        self._s_place: str = ldct_loc.get("name", None) or ""
        self._f_lat = ldct_loc.get("latitude", None)
        self._f_lon = ldct_loc.get("longitude", None)

        # reload interval (sec)
        self._i_reload_interval: int = max(int(self._dct_config.get("reloadInterval", 15 * 60)), wd.DI_MIN_RELOAD)

        # last good data (None until the first successful fetch)
        self._dct_data = None

    # -----------------------------------------------------------------------------------------
    def _geocode(self) -> bool:
        """
        look up latitude / longitude of the configured place name (Open-Meteo geocoding)

        :returns (bool): True if the location is known
        """
        # logger
        M_LOG.info(">> _geocode")

        # already known ?
        if (self._f_lat is not None) and (self._f_lon is not None):
            return True

        # location config
        ldct_loc = self._dct_config["location"]

        # query (first result: most relevant / populated)
        ldct_query = {"name": ldct_loc.get("name", ""), "count": 1, "format": "json",
                      # place names in the configured language ("pt_BR" -> "pt")
                      "language": i18n.DS_LANGUAGE.split("_")[0]}

        if ldct_loc.get("country_code", None):
            ldct_query["countryCode"] = ldct_loc["country_code"]

        # request
        lby_data, _ = hp.http_get(f"{wd.DS_GEOCODING_URL}?{urllib.parse.urlencode(ldct_query)}", DF_FETCH_TIMEOUT)

        # results
        llst_res = json.loads(lby_data).get("results", None) or []

        # not found ?
        if not llst_res:
            raise LookupError(f"place not found: {ldct_query['name']!r}")

        # location
        self._f_lat, self._f_lon = llst_res[0]["latitude"], llst_res[0]["longitude"]
        # displayed name (city + state / region, unless both have the same name)
        ls_name, ls_admin = llst_res[0].get("name", ""), llst_res[0].get("admin1", "")
        self._s_place = f"{ls_name}, {ls_admin}" if ls_admin and (ls_admin != ls_name) else ls_name

        # logger
        M_LOG.info("weather location: %s (%.4f, %.4f)", self._s_place, self._f_lat, self._f_lon)

        # ok
        return True

    # -----------------------------------------------------------------------------------------
    def _fetch(self) -> dict:
        """
        request current conditions + today's values

        :returns (dict): compact weather data
        """
        # logger
        M_LOG.info(">> _fetch")

        # units
        ldct_units = self._dct_config.get("units", {})

        # query
        ldct_query = {"latitude": self._f_lat, "longitude": self._f_lon,
                      "current": DS_CURRENT, "daily": DS_DAILY,
                      "forecast_days": 1, "timezone": "auto",
                      "temperature_unit": ldct_units.get("temperature", "celsius"),
                      "wind_speed_unit": ldct_units.get("wind", "kmh"),
                      "precipitation_unit": ldct_units.get("precipitation", "mm")}

        # request
        lby_data, _ = hp.http_get(f"{wd.DS_FORECAST_URL}?{urllib.parse.urlencode(ldct_query)}", DF_FETCH_TIMEOUT)

        # response
        ldct_resp = json.loads(lby_data)

        # API error ? ({"error": true, "reason": "..."})
        if ldct_resp.get("error", False):
            raise ValueError(ldct_resp.get("reason", "Open-Meteo error"))

        # current conditions, today's values (first day), units
        ldct_cur = ldct_resp["current"]
        ldct_day = {k: (v[0] if v else None) for k, v in ldct_resp.get("daily", {}).items()}
        ldct_cu = ldct_resp.get("current_units", {})

        # compact data (the view's contract; also what a small device would need)
        return {"place": self._s_place,
                "time": ldct_cur.get("time"),
                "temp": ldct_cur.get("temperature_2m"),
                "feels": ldct_cur.get("apparent_temperature"),
                "humidity": ldct_cur.get("relative_humidity_2m"),
                "precip": ldct_cur.get("precipitation"),
                "code": ldct_cur.get("weather_code"),
                "is_day": bool(ldct_cur.get("is_day", 1)),
                "wind": ldct_cur.get("wind_speed_10m"),
                "wind_dir": ldct_cur.get("wind_direction_10m"),
                "gust": ldct_cur.get("wind_gusts_10m"),
                "tmin": ldct_day.get("temperature_2m_min"),
                "tmax": ldct_day.get("temperature_2m_max"),
                "rain_sum": ldct_day.get("precipitation_sum"),
                "rain_prob": ldct_day.get("precipitation_probability_max"),
                "temp_unit": ldct_cu.get("temperature_2m", "°C"),
                "wind_unit": ldct_cu.get("wind_speed_10m", "km/h"),
                "precip_unit": ldct_cu.get("precipitation", "mm"),
                # monotonic: the data age must not jump with the wall clock (set by NTP after boot)
                "fetched": time.monotonic()}

    # -----------------------------------------------------------------------------------------
    def fetch_once(self):
        """
        one cycle: locate (if needed), fetch, emit WEATHER_DATA or WEATHER_ERROR

        :returns (dict): new data, or None on error (the last good data is kept)
        """
        try:
            # location known (geocoding if needed) and fetch
            self._geocode()
            ldct_data = self._fetch()

        # on error... (HTTP, network, JSON, API, place not found)
        except Exception as l_err:
            # error info
            ldct_err = hp.error_info(l_err)

            # logger
            M_LOG.error("SWeatherFetcher: could not fetch weather: %s", ldct_err)

            # notify error
            gd.G_EVENTS.emit("WEATHER_ERROR", ldct_err)

            # keep last good data
            return None

        # save and broadcast
        self._dct_data = ldct_data
        gd.G_EVENTS.emit("WEATHER_DATA", ldct_data)

        # new data
        return ldct_data

    # -----------------------------------------------------------------------------------------
    def _cycle(self) -> bool:
        """
        one cycle of the loop: fetch_once() that never raises. The listeners run in this thread
        (WEATHER_DATA / WEATHER_ERROR), and an error in any of them would otherwise end the
        thread, freezing the weather until the app restarts. It is logged, polling goes on

        :returns (bool): True if new data was fetched (False: retry sooner, see run)
        """
        try:
            return self.fetch_once() is not None

        # on error... (a bug: fetch errors are already handled in fetch_once)
        except Exception:
            M_LOG.exception("SWeatherFetcher: fetch cycle failed (still polling)")

        # failed
        return False

    # -----------------------------------------------------------------------------------------
    def run(self):
        """
        fetch loop
        """
        # logger
        M_LOG.info(">> run")

        # consecutive failed cycles
        li_failures = 0

        # while keep running...
        while gd.GV_KEEP_RUN:
            # start time (sec)
            lf_ini = time.perf_counter()

            # one cycle (never raises)
            li_failures = 0 if self._cycle() else li_failures + 1

            # next cycle: the reload interval, or sooner after failures (e.g. no network yet)
            lf_wait = hp.retry_delay(li_failures, self._i_reload_interval)

            # elapsed time (sec)
            lf_dt = time.perf_counter() - lf_ini

            # time left ?
            if lf_wait > lf_dt:
                # wait for the next cycle
                time.sleep(lf_wait - lf_dt)

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # logger
    lg.setup()

    # one fetch, printed
    gd.G_EVENTS.on("WEATHER_DATA", lambda p: print("WEATHER_DATA:", p))
    gd.G_EVENTS.on("WEATHER_ERROR", lambda p: print("WEATHER_ERROR:", p))

    SWeatherFetcher().fetch_once()

    # terminate
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
