# -*- coding: utf-8 -*-
"""
events
implements an EventHandler

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging

# infoView
import infoview.core.logsetup as lg

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.ERROR)

# < SEventHandler >----------------------------------------------------------------------------

class SEventHandler:
    """
    publish / subscribe event bus (singleton: SEventHandler() always returns the same object;
    the app uses it as infoview.core.state.G_EVENTS).

    emit() is synchronous: every listener runs in the emitter's thread, in registration order;
    an exception in a listener propagates to the emitter. There is no off() and no locking
    (listeners are registered at startup, before the threads start).
    """
    # -----------------------------------------------------------------------------------------
    # instance
    c_instance = None

    # event name -> list of listeners
    c_dct_events = {}
	
    # -----------------------------------------------------------------------------------------
    def __new__(cls):
        """
        implementation of the Singleton Pattern
        """
        # first instance ?
        if cls.c_instance is None:
            # create the object
            cls.c_instance = super(SEventHandler, cls).__new__(cls)

        # return instance
        return cls.c_instance

    # -----------------------------------------------------------------------------------------
    def __str__(self):
        """
        str representation
        """
        return f"<{self.__class__.__name__} {id(self)} {self.c_dct_events}>"

    # -----------------------------------------------------------------------------------------
    def clear(self):
        """
        remove every listener (for tests: the bus is a singleton, so listeners registered by
        one test would otherwise also receive the events of the next ones)
        """
        self.c_dct_events.clear()

    # -----------------------------------------------------------------------------------------
    def emit(self, fs_event: str, fdct_payload: dict):
        """
        emit an event

        :param fs_event (str): event to emit
        :param fdct_payload (dict): payload
        """
        # logger
        M_LOG.info(">> emit")

        # for all listeners of this event (none, if it was never registered)...
        for lfn_callback in self.c_dct_events.get(fs_event, []):
            # trigger all functions
            lfn_callback(fdct_payload)
	
    # -----------------------------------------------------------------------------------------
    def on(self, fs_event: str, f_callback):
        """
        listen an event

        :param fs_event (str): event to listen
        :param f_callback (callable): callback function
        """
        # logger
        M_LOG.info(">> on")

        # register the callback, creating the listener list on first use
        self.c_dct_events.setdefault(fs_event, []).append(f_callback)
	
# ---------------------------------------------------------------------------------------------
# this is the bootstrap process
                     
if "__main__" == __name__:

    # logger
    lg.setup()

    # singleton: every "instance" is the same object
    l_evt = SEventHandler()
    print("singleton:", l_evt is SEventHandler())

    # two listeners, one event (called in registration order, in this thread)
    l_evt.on("test_event", lambda p: print("listener 1:", p))
    l_evt.on("test_event", lambda p: print("listener 2:", p))
    l_evt.emit("test_event", {"x": 10, "y": 20})

    # event without listeners: nothing happens
    l_evt.emit("no_listeners", {})

# < the end >----------------------------------------------------------------------------------
