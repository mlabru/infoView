# -*- coding: utf-8 -*-
"""
infoView tests (unittest, standard library only)

    python3 -m unittest discover -s tests -t .          # from the project root
    python3 -m unittest tests.test_config -v            # one module

No display and no network needed: SDL runs with the dummy video driver, the feeds and the
Open-Meteo API are served by local HTTP servers (tests/support.py).

This package __init__ runs before any test module is imported, so it isolates the environment
the infoview package reads at import time: no IVW_* variable from the user's shell, and an empty
config file (the user's infoView.toml is never read by the tests).

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import os

# < environment >------------------------------------------------------------------------------

# no IVW_* settings from the user's shell
for _ls_var in [x for x in os.environ if x.startswith("IVW_")]:
    del os.environ[_ls_var]

# empty config file: code defaults only
os.environ["IVW_CONFIG"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "empty.toml")

# no display, no sound, no pygame banner
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# no log noise on the console (assertLogs still captures; failures still show tracebacks)
logging.getLogger("infoview").addHandler(logging.NullHandler())

# < the end >----------------------------------------------------------------------------------
