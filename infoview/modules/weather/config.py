# -*- coding: utf-8 -*-
"""
infoView 1.0
Weather / configuration

DDCT_DEFAULTS: the code defaults. DDCT_RULES: limits / accepted values of the user's values (a
value out of them: the default). DDCT_CONFIG: the effective configuration = defaults + [weather]
section of the user's config file (infoView.toml, see infoview/core/config.py), validated. The
code reads only DDCT_CONFIG. Set your location there (the default is only an example).

weather data by Open-Meteo.com (CC BY 4.0, no API key): https://open-meteo.com

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging

# infoView
import infoview.core.config as cfg

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < module data >------------------------------------------------------------------------------

# Open-Meteo endpoints
DS_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DS_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# code defaults
DDCT_DEFAULTS = {# location: an EXAMPLE - set yours in infoView.toml [weather.location], not here.
                 # With latitude/longitude set, the name is
                 # only displayed; without them, the name is looked up (geocoding),
                 # restricted to country_code (ISO 3166-1 alpha-2) when given
                 "location": {"name": "São Paulo",
                              "country_code": "BR",
                              "latitude": None,
                              "longitude": None},
                 "reloadInterval": 15 * 60,   # Open-Meteo "current" updates every 15 min (sec)
                 "units": {"temperature": "celsius",   # celsius | fahrenheit
                           "wind": "kmh",              # kmh | ms | mph | kn
                           "precipitation": "mm"},     # mm | inch
                 "staleAfter": 45 * 60,       # data older than this is marked old (sec)
}  # DDCT_DEFAULTS

# min reload interval (sec): be nice to the free API
DI_MIN_RELOAD = 5 * 60

# limits / accepted values (see cfg.merge); units: the Open-Meteo parameter values
DDCT_RULES = {"location": {"latitude": {"min": -90, "max": 90},
                           "longitude": {"min": -180, "max": 180}},
              "reloadInterval": {"min": DI_MIN_RELOAD},
              "units": {"temperature": {"choices": ["celsius", "fahrenheit"]},
                        "wind": {"choices": ["kmh", "ms", "mph", "kn"]},
                        "precipitation": {"choices": ["mm", "inch"]}},
              "staleAfter": {"min": 60}}

# effective configuration
DDCT_CONFIG = cfg.merge(DDCT_DEFAULTS, cfg.section("weather"), "weather", DDCT_RULES)

# < the end >----------------------------------------------------------------------------------
