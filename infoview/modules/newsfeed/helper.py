# -*- coding: utf-8 -*-
"""
infoView 1.0
NewsFeed / Node Helper

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import sys
import threading
import time
import urllib.parse as up

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd

# newsfeed
import infoview.modules.newsfeed.config as nd
import infoview.modules.newsfeed.fetcher as ftr

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < SNodeHelper >------------------------------------------------------------------------------

class SNodeHelper:
    """
    newsfeed backend: one SNewsfeedFetcher (thread) per feed URL, created on ADD_FEED; every time
    a fetcher gets new items, all fetchers' items are broadcast as NEWS_ITEMS; fetch errors are
    classified and emitted as NEWSFEED_ERROR. Port of the MagicMirror² newsfeed node_helper.js
    (here in the same process: it talks to SNewsFeed over the global event bus).
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self):
        """
        constructor
        """
        # logger
        M_LOG.info(">> constructor")

        # fetchers: URL -> SNewsfeedFetcher
        self._fetchers: dict = {}

        # guards _fetchers and serializes the broadcasts: each fetcher broadcasts from its own
        # thread, so without it (1) a broadcast could iterate _fetchers while start() is still
        # adding fetchers and (2) a slower broadcast holding an older snapshot of another feed
        # could reach the model after a newer one, replacing that feed's new items by old ones.
        # Not reentrant, and held while NEWS_ITEMS is emitted: a NEWS_ITEMS listener must never
        # emit ADD_FEED (create_fetcher would wait for this lock forever)
        self._lock = threading.Lock()

        # events callback
        gd.G_EVENTS.on("ADD_FEED", self.on_add_feed)

    # -----------------------------------------------------------------------------------------
    def broadcast_feeds(self, fs_url: str):
        """
        a fetcher got new items: broadcast the items of all registered feeds as NEWS_ITEMS
        ({URL: [items]}; called in that fetcher's thread)

        :param fs_url (str): fetcher URL
        """
        # logger
        M_LOG.info(">> broadcast_feeds")

        # debug
        M_LOG.debug("fetchers: %d, broadcast by: %s", len(self._fetchers), fs_url)

        # one broadcast at a time: snapshot and emit together (the model then always gets the
        # newest lists; a fetcher replaces its list before broadcasting it)
        with self._lock:
            # emit news items
            gd.G_EVENTS.emit("NEWS_ITEMS", {x: y.lst_items for x, y in self._fetchers.items()})

    # -----------------------------------------------------------------------------------------
    def create_fetcher(self, fdct_feed: dict, fdct_config: dict):
        """
        creates a fetcher for a new feed if it doesn't exist yet. Otherwise it reuses the
        existing one

        :param fdct_feed (dict): feed object
        :param fdct_config (dict): configuration object
        """
        # logger
        M_LOG.info(">> create_fetcher")

        # debug
        M_LOG.debug("fdct_feed: %s", fdct_feed)
        M_LOG.debug("fdct_config: %s", fdct_config)

        # source URL
        ls_url = fdct_feed.get("url", None) or ""
        # reload interval: the feed's, else the module's, else the default (the fetcher keeps
        # it at least nd.DI_MIN_RELOAD)
        li_reload_interval = fdct_feed.get("reloadInterval", None) or \
                             fdct_config.get("reloadInterval", None) or \
                             nd.DDCT_DEFAULTS["reloadInterval"]
        try:
            # validate URL
            l_rc = up.urlparse(ls_url)

            # any error ?
            if not all([l_rc.scheme, l_rc.netloc]):
                # generate exception
                raise ValueError 

        # on error...
        except ValueError as l_err:
            # logger
            M_LOG.error("SNodeHelper: Malformed newsfeed url: %s. %s", ls_url, l_err)

            # emit notification
            gd.G_EVENTS.emit("NEWSFEED_ERROR", {"error_type": "MODULE_ERROR_MALFORMED_URL"})

            # no fetcher
            return

        # fetcher doesn't exists ?
        if ls_url not in self._fetchers:
            # debug
            M_LOG.debug("create newsfetcher for url: %s - Interval: %d", ls_url, li_reload_interval)

            # create fetcher
            l_fetcher = ftr.SNewsfeedFetcher(ls_url, li_reload_interval, fdct_config.get("logFeedWarnings", False))

            # setup fetcher
            l_fetcher.on_receive(self.broadcast_feeds)
            l_fetcher.on_error(self.on_error)

            # save fetcher (not while a broadcast iterates the fetchers)
            with self._lock:
                self._fetchers[ls_url] = l_fetcher

            # start fetcher
            l_fetcher.start()

        # else,...
        else:
            # debug
            M_LOG.debug("use existing newsfetcher for url: %s", ls_url)

            # get fetcher
            l_fetcher = self._fetchers[ls_url]

            # same URL configured again: the shortest reload interval wins (see the setter)
            l_fetcher.i_reload_interval = li_reload_interval
            l_fetcher.broadcast_items()

    # -----------------------------------------------------------------------------------------
    def on_add_feed(self, fdct_payload: dict):
        """
        on add feed callback

        :param fdct_payload (dict): payload
        """
        # logger
        M_LOG.info(">> on_add_feed")

        # create fetcher
        self.create_fetcher(fdct_payload["feed"], fdct_payload["config"])

    # -----------------------------------------------------------------------------------------
    def on_error(self, f_fetcher, fs_url: str, fdct_error: dict):
        """
        fetch error callback of a fetcher: log, classify and emit NEWSFEED_ERROR

        :param f_fetcher (SNewsfeedFetcher): the fetcher (unused: part of the callback signature)
        :param fs_url (str): URL
        :param fdct_error (dict): {"code", "message"} (see infoview.core.net.error_info)
        """
        # logger
        M_LOG.info(">> on_error")

        # log
        M_LOG.error("SNodeHelper. Could not fetch newsfeed from: %s cause: %s", fs_url, fdct_error)

        # fill in defaults only if missing, without discarding the real error info
        fdct_error.setdefault("code", "*undefined*")
        fdct_error.setdefault("message", "*undefined*")

        # error type
        ls_error_type = fetch_error_type(fdct_error)

        # emit signal
        gd.G_EVENTS.emit("NEWSFEED_ERROR", { "error_type": ls_error_type })

# ---------------------------------------------------------------------------------------------
def fetch_error_type(fdct_error: dict) -> str:
    """
    classify a fetch error (MagicMirror² checkFetchError)

    :param fdct_error (dict): {"code", "message"} (see infoview.core.net.error_info)

    :returns (str): MODULE_ERROR_NO_CONNECTION (code URLError, or node's EAI_AGAIN),
                    MODULE_ERROR_UNAUTHORIZED (message "Unauthorized", HTTP 401), or
                    MODULE_ERROR_UNSPECIFIED
    """
    # no connection ?
    if fdct_error.get("code", None) in ("EAI_AGAIN", "URLError"):
        return "MODULE_ERROR_NO_CONNECTION"

    # unauthorized ?
    if "Unauthorized" == fdct_error.get("message", None):
        return "MODULE_ERROR_UNAUTHORIZED"

    # anything else
    return "MODULE_ERROR_UNSPECIFIED"

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # logger
    lg.setup()

    try:
        # print what is broadcast
        gd.G_EVENTS.on("NEWS_ITEMS", lambda p: print({u: len(l) for u, l in p.items()}))

        # instantiate class
        l_nh = SNodeHelper()

        # create a fetcher (daemon thread)
        l_nh.create_fetcher({"url": "https://feeds.folha.uol.com.br/ciencia/rss091.xml",
                             "reloadInterval": 60},
                            {"logFeedWarnings": False})

        # give the fetcher time for its first fetch (the daemon thread dies with the process)
        time.sleep(20)

    # on error...
    except KeyboardInterrupt:
        # logger
        logging.warning("Interrupted.")
    
    # terminate
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
