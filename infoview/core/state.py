# -*- coding: utf-8 -*-
"""
infoview.core.state
shared mutable state: the global event bus and the run flag (settings: infoview/core/settings.py)

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# events
import infoview.core.events as evt

# < global objects >---------------------------------------------------------------------------

# global event bus (singleton, see infoview/core/events.py)
G_EVENTS = evt.SEventHandler()

# keep running (set False to stop the main loop and every background thread)
GV_KEEP_RUN = True

# < the end >----------------------------------------------------------------------------------
