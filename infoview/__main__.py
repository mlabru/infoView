# -*- coding: utf-8 -*-
"""
infoView 1.0
python3 -m infoview: same as python3 infoView.py

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import sys

# infoView
import infoview.core.logsetup as lg

# log format set before the application is imported (it reads the settings and the config file
# at import, and may log about them)
lg.setup()

import infoview.app  # noqa: E402

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process (python3 -m infoview)

sys.exit(infoview.app.run())

# < the end >----------------------------------------------------------------------------------
