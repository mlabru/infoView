#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infoView 1.0
entry point: python3 infoView.py (or: python3 -m infoview). The application is the infoview
package (infoview/app.py); see README.md.

2022.nov  mlabru  initial release (Linux/Python)
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
# this is the bootstrap process

if "__main__" == __name__:
    # run application
    sys.exit(infoview.app.run())

# < the end >----------------------------------------------------------------------------------
