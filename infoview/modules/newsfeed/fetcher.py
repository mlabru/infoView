# -*- coding: utf-8 -*-
"""
infoView 1.0
NewsFeed / NewsfeedFetcher

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import calendar
import logging
import sys
import threading
import time

# newsfeed
import feedparser

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.net as hp

# newsfeed
import infoview.modules.newsfeed.config as nd

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# network timeout for one feed download (sec)
DF_FETCH_TIMEOUT = 30.

# < SNewsfeedFetcher >-------------------------------------------------------------------------

class SNewsfeedFetcher(threading.Thread):
    """
    responsible for requesting an update on the set interval and broadcasting the data
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fs_url: str, fi_reload_interval: int, fv_log_feed_warnings: bool):
        """
        constructor (the feed charset comes from the HTTP Content-Type header or the XML
        declaration: no encoding parameter)

        :param fs_url (str): URL of the news feed
        :param fi_reload_interval (int): reload interval in seconds (min 60)
        :param fv_log_feed_warnings (bool): if true log warnings when there is an error parsing a news article
        """
        # logger
        M_LOG.info(">> constructor")

        # debug
        M_LOG.debug("fs_url: %s", fs_url)
        M_LOG.debug("fi_reload_interval: %s", fi_reload_interval)
        M_LOG.debug("fv_log_feed_warnings: %s", fv_log_feed_warnings)

        # init super class
        super().__init__()

        # daemon thread, so a pending sleep (reload interval) doesn't hold the process on exit
        self.daemon = True

        # attributes

        # feed items
        self._lst_items: list = []

        # feed source URL
        self._s_url: str = fs_url

        # configured interval for the update in seconds (never shorter than the minimum) and
        # the effective one (a feed <ttl> may make it longer, see on_fetch_ttl)
        self._i_base_interval: int = max(fi_reload_interval, nd.DI_MIN_RELOAD)
        self._i_reload_interval: int = self._i_base_interval
        # feed <ttl> of the last feed parsed (sec; 0: none)
        self._i_ttl_sec: int = 0

        # log feed warnings flag
        self._v_log_feed_warnings: bool = fv_log_feed_warnings

        # cache validators of the last feed parsed (sent back as If-None-Match /
        # If-Modified-Since: an unchanged feed then answers 304 with no body)
        self._s_etag: str = ""
        self._s_last_modified: str = ""

        # called when received items 
        self._fnc_items_received_callback = None

        # called when fetch fail
        self._fnc_fetch_failed_callback = None

        # note: errors are reported straight to this fetcher's own callback (on_fetch_error),
        # not through the global event bus, otherwise every fetcher would get every error

    # -----------------------------------------------------------------------------------------
    def broadcast_items(self):
        """
        broadcast the existing items
        """
        # logger
        M_LOG.info(">> broadcast_items")

        # no items ?
        if not self._lst_items:
            # logger
            M_LOG.warning("SNewsfeedFetcher: No items to broadcast yet from %s", self._s_url)
            # nothing to broadcast
            return

        # debug
        M_LOG.debug("SNewsfeedFetcher: Broadcasting %d items from %s.", len(self._lst_items), self._s_url)

        # exist callback ?
        if self._fnc_items_received_callback:
            # call callback 
            self._fnc_items_received_callback(self._s_url)

    # -----------------------------------------------------------------------------------------
    def _cycle(self) -> bool:
        """
        one fetch cycle: fetch, replace the items and broadcast them (also when the feed didn't
        change, HTTP 304: the model then filters the items again, so those that became too old
        leave the ticker even if the feed never changes). Never raises: the listeners
        run in this thread (node helper -> model), and an error in any of them would otherwise
        end the thread, freezing this feed until the app restarts. It is logged, polling goes on

        :returns (bool): True if the feed was fetched (False: retry sooner, see run)
        """
        try:
            # request the new items
            llst_items = self._fetch_get()

            # fetched ? (on failure keep the previous items, so the feed doesn't vanish)
            if llst_items is not None:
                # replace items at once (other threads may be reading the old list; not
                # modified: the same list)
                self._lst_items = llst_items

                # broadcast items
                self.broadcast_items()

            # fetched ?
            return llst_items is not None

        # on error... (a bug: fetch errors are already handled in _fetch_get)
        except Exception:
            M_LOG.exception("SNewsfeedFetcher: fetch cycle failed for %s (still polling)", self._s_url)

        # failed
        return False

    # -----------------------------------------------------------------------------------------
    def _fetch_get(self):
        """
        request the new items

        :returns (list): fetched items; the current list itself if the feed didn't change (HTTP
                         304); None if the fetch failed (error already reported)
        """
        # logger
        M_LOG.info(">> _fetch_get")

        try:
            # conditional request (validators of the last feed parsed, if the server sent any;
            # the User-Agent is the app's own, see infoview/core/net.py)
            ldct_request = {}

            if self._s_etag:
                ldct_request["If-None-Match"] = self._s_etag
            if self._s_last_modified:
                ldct_request["If-Modified-Since"] = self._s_last_modified

            # download here (feedparser has no network timeout), keeping the headers that matter
            # to the parser (charset, base URL), then let feedparser parse the bytes
            lby_data, ldct_headers = hp.http_get(self._s_url, DF_FETCH_TIMEOUT, ldct_request)

            # not modified (HTTP 304) ? the items we have are current
            if lby_data is None:
                M_LOG.debug("SNewsfeedFetcher: not modified: %s", self._s_url)
                return self._lst_items

            # parse feed
            ldct_feed = feedparser.parse(lby_data, response_headers=ldct_headers)

        # on error... (HTTP, network: no connection, DNS, timeout; parser)
        except Exception as l_err:
            # notify error
            self.on_fetch_error(hp.error_info(l_err))
            # failed
            return None

        # nothing parsed (invalid feed) ?
        if ldct_feed.get("bozo", False) and not ldct_feed["entries"]:
            # notify error (parse exception)
            self.on_fetch_error(hp.error_info(ldct_feed.get("bozo_exception", None) or ValueError("empty feed")))
            # failed
            return None

        M_LOG.debug("ldct_feed: %s", ldct_feed["feed"])

        # feed time to live (minutes; None if it has none): may make the reload interval longer
        # than the configured one, or bring it back when the ttl shrinks or disappears
        self.on_fetch_ttl(ldct_feed["feed"].get("ttl", None))

        # parsed: keep its validators for the next request
        self._s_etag = ldct_headers.get("etag", "")
        self._s_last_modified = ldct_headers.get("last-modified", "")

        # fetch all entries, dropping the ones that can't be parsed
        return [ldct_item for ldct_item in map(self._fetch_item, ldct_feed["entries"]) if ldct_item]

    # -----------------------------------------------------------------------------------------
    def _fetch_item(self, ldct_entry: dict):
        """
        convert one feed entry into a news item

        :param ldct_entry (dict): one entry

        :returns (dict): news item, or None if the entry has no title or no parseable date

        :TODO: remove duplicate items
        """
        # title
        ls_title = ldct_entry.get("title", None)
        # description
        ls_descr = ldct_entry.get("description", None) or \
                   ldct_entry.get("summary", None) or \
                   (ldct_entry.get("content", None) or [{}])[0].get("value", None) or \
                   ""
        # published date as text (only for the warning below: the code uses the timestamp)
        ls_pub_date = ldct_entry.get("pubdate", None) or \
                      ldct_entry.get("published", None) or \
                      ldct_entry.get("updated", None) or \
                      ldct_entry.get("dc:date", None)
        # published date, already parsed by feedparser (any format, struct_time in UTC)
        l_pub_parsed = ldct_entry.get("published_parsed", None) or \
                       ldct_entry.get("updated_parsed", None)
        # published date timestamp (sec since epoch)
        lf_timestamp = calendar.timegm(l_pub_parsed) if l_pub_parsed else None
        # url
        ls_url = ldct_entry.get("url", None) or \
                 ldct_entry.get("link", None) or \
                 ""

        # title & published date ok ?
        if ls_title and (lf_timestamp is not None):
            # return item
            return {"title": ls_title,
                    "description": ls_descr,
                    "timestamp": lf_timestamp,
                    "url": ls_url}

        # log warnings ?
        if self._v_log_feed_warnings:
            # logger
            M_LOG.warning("SNewsfeedFetcher: can't parse feed item: %s "
                          "(Title: %s Description: %s Pubdate: %s)", str(ldct_entry),
                          ls_title, ls_descr, ls_pub_date)

        # invalid item
        return None

    # -----------------------------------------------------------------------------------------
    def on_error(self, f_callback):
        """
        on error callback
        """
        # logger
        M_LOG.info(">> on_error")

        # set fetch error callback
        self._fnc_fetch_failed_callback = f_callback

    # -----------------------------------------------------------------------------------------
    def on_fetch_error(self, fdct_error: dict):
        """
        fetch error callback

        :param ldct_entry (dict): error entry
        """
        # logger
        M_LOG.info(">> on_fetch_error")

        # fetch failed handler ?
        if self._fnc_fetch_failed_callback:
            # handle error 
            self._fnc_fetch_failed_callback(self, self._s_url, fdct_error)

    # -----------------------------------------------------------------------------------------
    def on_fetch_ttl(self, fi_minutes):
        """
        apply the feed's <ttl> (time to live): never reload more often than the feed asks, and
        never less often than configured. Evaluated on every feed parsed, so a ttl that shrinks
        or disappears brings the interval back down (to the configured one at least)

        :param fi_minutes (int|str|None): ttl minutes (feedparser gives it as a string); None:
                                          the feed has no ttl
        """
        # logger
        M_LOG.info(">> on_fetch_ttl")

        # ttl in seconds (0: none)
        li_ttl_sec = 0

        # any ttl ?
        if fi_minutes:
            try:
                # 86400 = 24 hours is mentioned in the docs as maximum value
                li_ttl_sec = min(int(fi_minutes) * 60, 86400)

            # on error...
            except (TypeError, ValueError) as l_err:
                # logger
                M_LOG.error("SNewsfeedFetcher: feed ttl is no valid integer = %s for url %s (%s)", fi_minutes, self._s_url, l_err)

        # keep it, effective interval
        self._i_ttl_sec = li_ttl_sec
        self._update_interval()

    # -----------------------------------------------------------------------------------------
    def _update_interval(self):
        """
        effective reload interval: the configured one, or longer if the feed's ttl asks
        """
        # effective interval
        li_interval = max(self._i_base_interval, self._i_ttl_sec)

        # changed ?
        if li_interval != self._i_reload_interval:
            # set reload interval
            self._i_reload_interval = li_interval
            # logger
            M_LOG.warning("SNewsfeedFetcher: reload interval set to %d s (ttl %d s) for url: %s",
                          self._i_reload_interval, self._i_ttl_sec, self._s_url)

    # -----------------------------------------------------------------------------------------
    def on_receive(self, f_callback):
        """
        on receive callback
        """
        # logger
        M_LOG.info(">> on_receive")

        # set items received callback
        self._fnc_items_received_callback = f_callback

    # -----------------------------------------------------------------------------------------
    def run(self):
        """
        initiate fetch news
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

    # =========================================================================================
    # data
    # -----------------------------------------------------------------------------------------
    @property
    def lst_items(self) -> list:
        """fetcher items (replaced as a whole on each successful fetch)"""
        return self._lst_items

    # -----------------------------------------------------------------------------------------
    @property
    def i_reload_interval(self) -> int:
        """reload interval"""
        return self._i_reload_interval
    
    @i_reload_interval.setter
    def i_reload_interval(self, f_val: int):
        """reload interval: only accepts a SHORTER configured interval (same URL configured
        twice: the shortest one wins; the feed <ttl> may later make it longer, see on_fetch_ttl)"""
        if nd.DI_MIN_RELOAD <= f_val < self._i_base_interval:
            # configured interval for the update in seconds; the effective one follows, unless
            # the feed's ttl keeps it longer
            self._i_base_interval = f_val
            self._update_interval()

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # logger
    lg.setup()

    # instantiate class
    l_nff = SNewsfeedFetcher("https://feeds.folha.uol.com.br/ciencia/rss091.xml", 60, True)

    # errors (normally sent to the node helper)
    l_nff.on_error(lambda f, u, e: print("error:", u, e))

    # one fetch, in this thread (start() would run it in a daemon thread, killed on exit)
    llst_items = l_nff._fetch_get()

    print(f"{len(llst_items or [])} items", llst_items[0] if llst_items else "")

    # terminate
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
