# -*- coding: utf-8 -*-
"""
infoview.core.timesync
is the system clock synchronized (NTP) ?

The Raspberry Pi has no real time clock: at boot the time is the one saved at the last shutdown
(fake-hwclock) or even 1970, until NTP (systemd-timesyncd) sets it, which needs the network.
Until then the clock would show a wrong time and the article ages would be wrong. start() asks
`timedatectl` once and, if it says "not synchronized", keeps asking every DF_POLL seconds in a
daemon thread until it does. Where timedatectl doesn't exist or doesn't answer (no systemd, a
container, a desktop without it) the clock is trusted: GV_SYNCED stays True. A "can't tell" is
not taken as final at once, though: at boot timedatectl may fail or time out only because dbus /
timedated are not up yet, so it is asked again (DI_UNKNOWN_MAX times, every DF_POLL seconds)
before trusting the clock for good; a "not synchronized" meanwhile is still caught. The check can be
turned off ([general] clock_check = false: a Pi with a hardware clock and no network, where
timedatectl would say "not synchronized" forever although the time is right).

    GV_SYNCED   True: the time is right (or can't be checked); False: not synchronized yet

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import subprocess
import threading
import time

# infoView
import infoview.core.state as gd

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# the question (prints "yes" / "no")
DLST_COMMAND = ["timedatectl", "show", "--property=NTPSynchronized", "--value"]

# time limit for one answer (sec)
DF_TIMEOUT = 5.

# while not synchronized (or can't tell yet), ask again every (sec)
DF_POLL = 10.

# consecutive "can't tell" answers before the clock is trusted for good (1 min with DF_POLL)
DI_UNKNOWN_MAX = 6

# < state >------------------------------------------------------------------------------------

# clock synchronized ? (True until start() finds out otherwise; read by the views)
GV_SYNCED = True

# ---------------------------------------------------------------------------------------------
def check():
    """
    ask the system whether the clock is synchronized

    :returns (bool | None): True / False, or None if it can't be told (no timedatectl, error,
                            timeout, unexpected answer)
    """
    try:
        l_res = subprocess.run(DLST_COMMAND, capture_output=True, text=True, timeout=DF_TIMEOUT, check=False)

    # on error... (not installed, timeout)
    except (OSError, subprocess.SubprocessError) as l_err:
        M_LOG.info("timesync: can't check (%s)", l_err)
        return None

    # answer
    ls_answer = l_res.stdout.strip().lower()

    if (0 == l_res.returncode) and (ls_answer in ("yes", "no")):
        return "yes" == ls_answer

    # anything else
    M_LOG.info("timesync: unexpected answer (rc %d): %r", l_res.returncode, ls_answer)
    return None

# ---------------------------------------------------------------------------------------------
def _poll(fi_unknown: int):
    """
    daemon thread: ask again every DF_POLL seconds until synchronized, or until it couldn't be
    told DI_UNKNOWN_MAX times in a row (then the clock is trusted)

    :param fi_unknown (int): consecutive "can't tell" answers so far
    """
    global GV_SYNCED

    li_unknown = fi_unknown

    while gd.GV_KEEP_RUN:
        time.sleep(DF_POLL)

        # answer
        lv_synced = check()

        # synchronized now ?
        if lv_synced:
            M_LOG.warning("timesync: clock synchronized")
            GV_SYNCED = True
            return

        # can't tell (again) ?
        if lv_synced is None:
            li_unknown += 1

            # for long enough: trust the clock
            if li_unknown >= DI_UNKNOWN_MAX:
                M_LOG.warning("timesync: can't check the clock, trusting it")
                GV_SYNCED = True
                return

            continue

        # not synchronized
        li_unknown = 0

        if GV_SYNCED:
            M_LOG.warning("timesync: clock not synchronized yet (NTP), waiting")
            GV_SYNCED = False

# ---------------------------------------------------------------------------------------------
def start(fv_check: bool = True):
    """
    check once; if not synchronized, GV_SYNCED = False and a daemon thread watches until it is;
    if it can't be told, the clock is trusted meanwhile (GV_SYNCED = True) and the thread asks
    again a few times (see _poll)

    :param fv_check (bool): False: don't check, trust the clock (settings.DV_CLOCK_CHECK)

    :returns (threading.Thread | None): the watching thread, or None if not needed
    """
    global GV_SYNCED

    # not checked: trust the clock
    if not fv_check:
        GV_SYNCED = True
        return None

    # answer
    lv_synced = check()

    # synchronized ?
    if lv_synced:
        GV_SYNCED = True
        return None

    # can't tell (yet) ? trusted meanwhile
    if lv_synced is None:
        GV_SYNCED = True

    # not synchronized
    else:
        M_LOG.warning("timesync: clock not synchronized yet (NTP), waiting")
        GV_SYNCED = False

    # watch
    l_thread = threading.Thread(target=_poll, args=(0 if lv_synced is False else 1,), name="timesync", daemon=True)
    l_thread.start()

    return l_thread

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # one check, printed
    print("synchronized:", check())

# < the end >----------------------------------------------------------------------------------
