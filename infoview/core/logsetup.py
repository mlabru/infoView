# -*- coding: utf-8 -*-
"""
infoview.core.logsetup
logging setup: one format for the application and the module self-tests

    2026/11/01 10:15:42 WARNING infoview.modules.newsfeed.helper: SNodeHelper. Could not fetch ...

setup() configures the root logger (basicConfig: does nothing if it already has a handler).
The entry points (infoView.py, python -m infoview) call it BEFORE importing infoview.app, so
the messages logged while the settings and the config file are read at import (config
warnings, invalid values) have the same format, with time and level, in logs/infoView.log.
This module imports nothing from infoview (importing settings would read the config file).
Each module still gates its own output with M_LOG.setLevel(...).

2026.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging

# < constants >--------------------------------------------------------------------------------

# root logger level (each module limits its own output, WARNING by default)
DI_LOG_LEVEL = logging.DEBUG

# message format: date and time (with seconds), level, module, message
DS_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DS_LOG_DATEFMT = "%Y/%m/%d %H:%M:%S"

# ---------------------------------------------------------------------------------------------
def setup(fi_level: int = DI_LOG_LEVEL):
    """
    configure the root logger (no-op if it already has a handler)

    :param fi_level (int): root logger level
    """
    logging.basicConfig(format=DS_LOG_FORMAT, datefmt=DS_LOG_DATEFMT, level=fi_level)

# < the end >----------------------------------------------------------------------------------
