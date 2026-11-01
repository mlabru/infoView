# -*- coding: utf-8 -*-
"""
infoView 1.0
Newsfeed / Model

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import copy
import logging
import sys
import time

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.i18n as i18n

# newsfeed
import infoview.modules.newsfeed.config as nd
import infoview.modules.newsfeed.helper as nh

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < module data >------------------------------------------------------------------------------

# feed error type (NEWSFEED_ERROR, see helper.fetch_error_type) -> reason text (i18n key)
DDCT_ERROR_TEXTS = {"MODULE_ERROR_NO_CONNECTION": "nf.no_connection",
                    "MODULE_ERROR_UNAUTHORIZED": "nf.unauthorized",
                    "MODULE_ERROR_MALFORMED_URL": "nf.bad_url"}

# < SNewsFeed >--------------------------------------------------------------------------------

class SNewsFeed:
    """
    newsfeed logic (no rendering): keeps the filtered / sorted list of news items received from
    the node helper (NEWS_ITEMS), the active article and how it is displayed (title /
    description / full article, scroll, rotation paused), and answers the view through events
    (ARTICLE_INFO_REQUEST -> ARTICLE_INFO_RESPONSE; ARTICLE_* actions from buttons / keys).
    Port of the MagicMirror² newsfeed module (frontend side).

    Threads: NEWS_ITEMS arrives in a fetcher thread, which only builds the new list and leaves
    it in _lst_pending (one reference assignment); the main thread (view requests, buttons)
    takes it in _apply_pending, so the list and the active article index are only ever changed
    by the main thread. Not while the user reads a description / full article: the article
    being read could have left the feed (the next button press would show another one).
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self):
        """
        constructor
        """
        # logger
        M_LOG.info(">> constructor")

        # module name (log messages)
        self.name: str = "NewsFeed"

        # config dictionary (own copy, read only)
        self._dct_config: dict = copy.deepcopy(nd.DDCT_CONFIG)

        # news items list (main thread) / newest list built by a fetcher thread, not taken yet
        self._lst_news_items: list = []
        self._lst_pending: list = self._lst_news_items

        # current active item
        self._i_active_item: int = 0
        # last feed error type (NEWSFEED_ERROR), shown while there are no items; None after a
        # successful fetch
        self._s_error_type = None
        # the last list received had items, but the filters (age, prohibited words) dropped
        # them all: the placeholder says so instead of "waiting"
        self._v_all_filtered: bool = False
        # scroll position (px) and its range in the full article: max and page step (px), told
        # by the view when it lays the text out (ARTICLE_SCROLL_RANGE); 0 until then
        self._i_scroll_position: int = 0
        self._i_scroll_max: int = 0
        self._i_scroll_page: int = 0

        # is showing description / full article flags (run time state, not configuration)
        self._v_is_showing_description: bool = False
        self._v_show_full_article: bool = False
        # user asked for details (description / full article): article rotation is paused
        self._v_details_requested: bool = False

        # events callback
        gd.G_EVENTS.on("ARTICLE_INFO_REQUEST", self.on_article_info_request)
        gd.G_EVENTS.on("ARTICLE_LESS_DETAILS", self.on_article_less_details)
        gd.G_EVENTS.on("ARTICLE_MORE_DETAILS", self.on_article_more_details)
        gd.G_EVENTS.on("ARTICLE_NEXT", self.on_article_next)
        gd.G_EVENTS.on("ARTICLE_PREVIOUS", self.on_article_previous)
        gd.G_EVENTS.on("ARTICLE_SCROLL_RANGE", self.on_article_scroll_range)
        gd.G_EVENTS.on("ARTICLE_SCROLL_UP", self.on_article_scroll_up)
        gd.G_EVENTS.on("ARTICLE_TOGGLE_FULL", self.on_article_toggle_full)
        gd.G_EVENTS.on("NEWSFEED_ERROR", self.on_newsfeed_error)
        gd.G_EVENTS.on("NEWS_ITEMS", self.on_news_items)

    # -----------------------------------------------------------------------------------------
    def _filter_items(self, flst_items: list):
        """
        filter items
    
        :param flst_items (list): list of items
        """
        # logger
        M_LOG.info(">> _filter_items")

        # check for prohibited words ?
        if self._dct_config["prohibitedWords"]:
            # remove items with prohibited words in it
            flst_items = [litem for litem in flst_items if not self._prohibited_words(litem)]

        # for all items...
        for ldct_item in flst_items:
            # remove start tags from title ?
            if self._dct_config["removeStartTags"] in ["title", "both"]:
                # for all start tags...
                for ls_tag in self._dct_config["startTags"]:
                    # remove selected tags from the beginning of rss feed items
                    ldct_item["title"] = ldct_item["title"].removeprefix(ls_tag)

            # remove start tags from description ?
            # (always: the description may be shown on demand later)
            if self._dct_config["removeStartTags"] in ["description", "both"]:
                # for all start tags...
                for ls_tag in self._dct_config["startTags"]:
                    # remove selected tags from the beginning of rss feed items
                    ldct_item["description"] = ldct_item["description"].removeprefix(ls_tag)

            # remove end tags from title ?
            if self._dct_config["removeEndTags"] in ["title", "both"]:
                # for all end tags...
                for ls_tag in self._dct_config["endTags"]:
                    # remove selected tags from the end of rss feed items
                    ldct_item["title"] = ldct_item["title"].removesuffix(ls_tag)

            # remove end tags from description ?
            if self._dct_config["removeEndTags"] in ["description", "both"]:
                # for all end tags...
                for ls_tag in self._dct_config["endTags"]:
                    # remove selected tags from the end of rss feed items
                    ldct_item["description"] = ldct_item["description"].removesuffix(ls_tag)

        # limit number of items ? (done last, after filtering, so the cap
        # reflects the actual number of items that survived the filters)
        if self._dct_config.get("maxNewsItems", 0) > 0:
            # slice items
            flst_items = flst_items[: self._dct_config["maxNewsItems"]]

        # return
        return flst_items

    # -----------------------------------------------------------------------------------------
    def generate_feed(self, fdct_feeds: dict):
        """
        generate an ordered list of items for this configured module (fetcher thread: the list
        is only left for the main thread, see _apply_pending)
    
        :param fdct_feeds (dict): a dictionary with feeds returned by the node helper
        """
        # logger
        M_LOG.info(">> generate_feed")

        # any item received at all ? (before the filters)
        lv_received = any(fdct_feeds.values())

        # get all feeds from all sources
        llst_news_items = self._get_feeds_list(fdct_feeds)

        # order list by timestamp
        llst_news_items = sorted(llst_news_items, key=lambda d: d["timestamp"], reverse=True) 

        # filter items
        llst_news_items = self._filter_items(llst_news_items)

        # a fetch succeeded: no error to explain an empty ticker anymore
        self._s_error_type = None
        # items received but none left after the filters ?
        self._v_all_filtered = lv_received and not llst_news_items

        # leave it for the main thread (atomic reference assignment)
        self._lst_pending = llst_news_items
        M_LOG.debug("new list: %d items", len(llst_news_items))

    # -----------------------------------------------------------------------------------------
    def _apply_pending(self):
        """
        main thread: take the newest list built by a fetcher thread, if there is one, and keep
        showing the same article (new items on top shift it down; the list may be shorter now).
        Not while details are shown: taken when back to the titles or on the next / previous
        article (they reset the details before answering)
        """
        # local reference (a fetcher thread may leave a newer one at any time)
        llst_new = self._lst_pending

        # nothing new, or the user is reading (keep the article being read) ?
        if (llst_new is self._lst_news_items) or self._v_details_requested:
            return

        # active article in the new list, then the list
        self._i_active_item = self._index_of_active(llst_new)
        self._lst_news_items = llst_new

    # -----------------------------------------------------------------------------------------
    def _has_items(self) -> bool:
        """
        main thread: any article to show ? (takes the newest list first)

        :returns (bool): True if there is at least one news item
        """
        # newest list first
        self._apply_pending()

        return bool(self._lst_news_items)

    # -----------------------------------------------------------------------------------------
    def _index_of_active(self, flst_new: list) -> int:
        """
        index of the active article in a new list of items

        :param flst_new (list): new (filtered, sorted) list of items

        :returns (int): the active article's index in the new list if it is still there, else the
                        current index limited to the new list (0 if the list is empty)
        """
        # empty list ?
        if not flst_new:
            return 0

        # the old list
        llst_old = self._lst_news_items

        # an active article ?
        if -1 < self._i_active_item < len(llst_old):
            # its identity
            ls_key = self._item_key(llst_old[self._i_active_item])

            # still in the new list ?
            for li_index, ldct_item in enumerate(flst_new):
                if ls_key == self._item_key(ldct_item):
                    return li_index

        # gone (or none): same position, inside the new list
        return min(self._i_active_item, len(flst_new) - 1)

    # -----------------------------------------------------------------------------------------
    def _item_key(self, fdct_item: dict) -> str:
        """
        identity of a news item: its URL, or its title if it has no URL

        :param fdct_item (dict): news item

        :returns (str): key
        """
        return self._item_url(fdct_item) or fdct_item["title"]

    # -----------------------------------------------------------------------------------------
    def _step(self, fi_delta: int):
        """
        move the active article, wrapping around (0 if the list is empty)

        :param fi_delta (int): +1 next, -1 previous
        """
        # newest list first
        self._apply_pending()
        llst_items = self._lst_news_items

        # new active article
        self._i_active_item = (self._i_active_item + fi_delta) % len(llst_items) if llst_items else 0

    # -----------------------------------------------------------------------------------------
    def _scroll_step(self) -> int:
        """
        scroll step of the down / up buttons in the full article

        :returns (int): scrollLength (px) if set, else one page as told by the view
        """
        return self._dct_config["scrollLength"] or self._i_scroll_page

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _item_url(fdct_item: dict) -> str:
        """
        get item url

        :param fdct_item (dict): news item

        :returns (str): item URL
        """
        # return URL (always text: the fetcher stores it as a string)
        return fdct_item["url"]

    # -----------------------------------------------------------------------------------------
    def _get_feeds_list(self, fdct_feeds: dict):
        """
        get all feeds from all sources

        :param fdct_feeds (dict): feeds from fetchers

        :returns (list): list with ll feeds from all sources        
        """
        # logger
        M_LOG.info(">> _get_feeds_list")

        # list of all feeds
        llst_news_items = []

        # map url -> feed config, built once so lookups below are O(1)
        # instead of a linear scan per source (and per item, for the title)
        ldct_feed_by_url = {ldct_feed["url"]: ldct_feed
                             for ldct_feed in self._dct_config["feeds"] if ldct_feed.get("url")}

        # for all sources...
        for ls_srce_url, ldct_srce_items in fdct_feeds.items():
            # feed config for this source
            ldct_feed = ldct_feed_by_url.get(ls_srce_url)

            # not subscribed ?
            if ldct_feed is None:
                # next source
                continue

            # source title (computed once per source, not once per item)
            ls_source_title = ldct_feed.get("title", None) or ""

            # for all items...
            for ldct_srce_item in ldct_srce_items:
                # own copy of the item + source title (the fetcher's items are shared and
                # re-sent on every broadcast, so they must not be modified here)
                ldct_item = dict(ldct_srce_item, sourceTitle=ls_source_title)

                # item age in seconds (timestamp already parsed by the fetcher)
                li_age_sec = time.time() - ldct_item["timestamp"]

                # accept any age ?
                if not (self._dct_config["ignoreOldItems"] and (li_age_sec > self._dct_config["ignoreOlderThan"])):
                    # save item on list
                    llst_news_items.append(ldct_item)

        # return
        return llst_news_items

    # -----------------------------------------------------------------------------------------
    def _article_mode(self) -> str:
        """
        current article display mode

        :returns (str): "title", "description" or "full"
        """
        # full article ?
        if self._v_show_full_article:
            return "full"

        # description or just the title
        return "description" if self._v_is_showing_description else "title"

    # -----------------------------------------------------------------------------------------
    def _emit_article_info(self):
        """
        send the active article (and how to display it) to the view
        """
        # newest list first
        self._apply_pending()
        llst_items = self._lst_news_items

        # valid request ?
        if -1 < self._i_active_item < len(llst_items):
            # active item
            ldct_item = llst_items[self._i_active_item]

            # emit article info
            gd.G_EVENTS.emit("ARTICLE_INFO_RESPONSE",
                {"title": ldct_item["title"],
                 "source": ldct_item["sourceTitle"],
                 "date": ldct_item["timestamp"],
                 "description": ldct_item["description"],
                 "url": self._item_url(ldct_item),
                 "mode": self._article_mode(),
                 "scroll": self._i_scroll_position,
                 "paused": self._v_details_requested})

        # else,...
        else:
            # emit article info
            gd.G_EVENTS.emit("ARTICLE_INFO_RESPONSE",
                {"title": self._placeholder_text(),
                 "source": i18n.tr("nf.source"),
                 "date": 0,
                 "description": "",
                 "url": "",
                 "mode": "title",
                 "scroll": 0,
                 "paused": False})

    # -----------------------------------------------------------------------------------------
    def _placeholder_text(self) -> str:
        """
        text shown while there are no items: why, when known

        :returns (str): "no feeds configured", "news unavailable (<reason>)" after a feed error,
                        "no recent news" when the filters dropped every item, else "waiting for
                        articles"
        """
        # no (valid) feed in the config ?
        if not self._dct_config["feeds"]:
            return i18n.tr("nf.no_feeds")

        # items received, all dropped by the filters (ignoreOldItems, prohibitedWords) ?
        if self._v_all_filtered:
            return i18n.tr("nf.all_filtered")

        # local reference (set by a fetcher thread)
        ls_error = self._s_error_type

        # no error (yet) ?
        if not ls_error:
            return i18n.tr("nf.waiting")

        # reason
        return i18n.tr("nf.unavailable", reason=i18n.tr(DDCT_ERROR_TEXTS.get(ls_error, "nf.feed_error")))

    # -----------------------------------------------------------------------------------------
    def _reset_details(self):
        """
        back to the configured display (titles, or titles + description), no scroll, resume
        rotation (MagicMirror² resetDescrOrFullArticleAndTimer)
        """
        # configured description display
        self._v_is_showing_description = self._dct_config["showDescription"]
        # no full article
        self._v_show_full_article = False
        # no scroll (range unknown until the view lays a full article out again)
        self._i_scroll_position = 0
        self._i_scroll_max = 0
        self._i_scroll_page = 0
        # rotation resumes
        self._v_details_requested = False

    # -----------------------------------------------------------------------------------------
    def on_article_info_request(self, fdct_payload: dict):
        """
        article info request callback

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_info_request")

        # emit article info
        self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_article_less_details(self, fdct_payload: dict):
        """
        article less details callback: back to titles

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_less_details")

        # reset article details
        self._reset_details()

        # debug
        M_LOG.debug("%s - showing only article titles again.", self.name)

        # update view
        self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_article_more_details(self, fdct_payload: dict):
        """
        the first time show article summary, on second time show full article, then scroll down

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_more_details")

        # no article (the "waiting" placeholder) ? nothing to detail: otherwise the details
        # would be "requested" with nothing shown, and the new items would never be taken
        if not self._has_items():
            pass

        # full article is already showing ?
        elif self._v_show_full_article:
            # so scrolling down, not past the end of the text
            self._i_scroll_position = min(self._i_scroll_position + self._scroll_step(), self._i_scroll_max)

            # debug
            M_LOG.debug("%s - ARTICLE_MORE_DETAILS, scroll position: %d", self.name, self._i_scroll_position)

        # else,...
        else:
            # show description / full article
            self.show_full_article()

        # update view
        self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_article_next(self, fdct_payload: dict):
        """
        article next callback

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_next")

        # index before the move (debug)
        li_before = self._i_active_item

        # advance to the next item, wrapping around
        self._step(+1)

        # reset article details
        self._reset_details()

        # debug
        M_LOG.debug("%s - going from article #%d to #%d (of %d)", self.name, li_before, self._i_active_item, len(self._lst_news_items))

        # update view
        self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_article_previous(self, fdct_payload: dict):
        """
        article previous callback

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_previous")

        # index before the move (debug)
        li_before = self._i_active_item

        # go back to the previous item, wrapping around
        self._step(-1)

        # reset article details
        self._reset_details()

        # debug
        M_LOG.debug("%s - going from article #%d to #%d (of %d)", self.name, li_before, self._i_active_item, len(self._lst_news_items))

        # update view
        self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_article_scroll_range(self, fdct_payload: dict):
        """
        the view laid the full article out: how far it can scroll and one page. Only stored (no
        new ARTICLE_INFO_RESPONSE: it comes from the view while it draws)

        :param fdct_payload (dict): {"max": px, "page": px}
        """
        # logger
        M_LOG.info(">> on_article_scroll_range")

        # range
        self._i_scroll_max = max(0, int(fdct_payload["max"]))
        self._i_scroll_page = max(0, int(fdct_payload["page"]))

        # current position inside it (the view already draws it clamped)
        self._i_scroll_position = min(self._i_scroll_position, self._i_scroll_max)

    # -----------------------------------------------------------------------------------------
    def on_article_scroll_up(self, fdct_payload: dict):
        """
        article scroll up callback

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_scroll_up")

        # full article is already showing ?
        if self._v_show_full_article:
            # so scrolling up (not above the top)
            self._i_scroll_position = max(0, self._i_scroll_position - self._scroll_step())

            # debug
            M_LOG.debug("%s - ARTICLE_SCROLL_UP, scroll position: %d", self.name, self._i_scroll_position)

            # update view
            self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_article_toggle_full(self, fdct_payload: dict):
        """
        article toggle full callback

        :param fdct_payload (dict): not used
        """
        # logger
        M_LOG.info(">> on_article_toggle_full")

        # no article (the "waiting" placeholder) ? nothing to show in full (see
        # on_article_more_details)
        if not self._has_items():
            pass

        # full article is already showing ?
        elif self._v_show_full_article:
            # next item, wrapping around
            self._step(+1)

            # reset article details
            self._reset_details()

        # else,...
        else:
            # show full article
            self.show_full_article()

        # update view
        self._emit_article_info()

    # -----------------------------------------------------------------------------------------
    def on_newsfeed_error(self, fdct_payload: dict):
        """
        a feed could not be fetched (NEWSFEED_ERROR from the node helper; fetcher thread, or
        the main thread for a malformed URL). Logged and kept: the ticker keeps showing the
        items it has (a failed feed keeps its previous items); without items it is the reason
        shown (see _placeholder_text)

        :param fdct_payload (dict): {"error_type": "MODULE_ERROR_..."}
        """
        # log
        M_LOG.warning("%s - feed error: %s", self.name, fdct_payload.get("error_type", "?"))

        # keep it (atomic reference assignment)
        self._s_error_type = fdct_payload.get("error_type", "MODULE_ERROR_UNSPECIFIED")

    # -----------------------------------------------------------------------------------------
    def on_news_items(self, fdct_payload: dict):
        """
        on news items callback

        :param fdct_payload (dict): payload
        """
        # logger
        M_LOG.info(">> on_news_items")

        # generate feed 
        self.generate_feed(fdct_payload)

    # -----------------------------------------------------------------------------------------
    def _prohibited_words(self, fdct_item: dict) -> bool:
        """
        item title contains any of the configured prohibited words ? (case insensitive)

        :param fdct_item (dict): item

        :returns (bool): True if the item must be dropped
        """
        # logger
        M_LOG.info(">> _prohibited_words")

        # lowercase once instead of once per prohibited word
        ls_title_lower = fdct_item["title"].lower()

        # return True if any word from title is in prohibited words list
        return any(lword.lower() in ls_title_lower for lword in self._dct_config["prohibitedWords"])

    # -----------------------------------------------------------------------------------------
    def register_feeds(self):
        """
        registers the feeds to be used by the backend
        """
        # logger
        M_LOG.info(">> register_feeds")

        # for all sources...
        for ldct_feed in self._dct_config["feeds"]:
            # debug
            M_LOG.debug("feed source: %s", ldct_feed)
            # ask the node helper for a fetcher for this feed
            gd.G_EVENTS.emit("ADD_FEED", {"feed": ldct_feed,
                                          "config": self._dct_config})

    # -----------------------------------------------------------------------------------------
    def show_full_article(self):
        """
        toggle between article description and full article (MagicMirror² showFullArticle)
        """
        # logger
        M_LOG.info(">> show_full_article")

        # toggle is showing description flag
        self._v_is_showing_description = not self._v_is_showing_description

        # toggle show full article
        self._v_show_full_article = not self._v_is_showing_description

        # pause article rotation while the user reads
        self._v_details_requested = True

        # debug
        M_LOG.debug("%s - showing %s", self.name,
                    "article description" if self._v_is_showing_description else "full article")

    # -----------------------------------------------------------------------------------------
    def start(self):
        """
        define start sequence
        """
        # logger
        M_LOG.info(">> start")

        # debug
        M_LOG.debug("Starting module: %s", self.name)

        # init attributes
        self._lst_news_items = []
        self._lst_pending = self._lst_news_items
        self._i_active_item = 0

        # configured display (descriptions or not), no scroll, rotation running
        self._reset_details()

        # registers the feeds to be used by the backend
        self.register_feeds()


# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:

    # logger
    lg.setup()

    try:
        # instantiate class
        l_nf = SNewsFeed()
        # instantiate class (listens to ADD_FEED, emitted by l_nf.start())
        l_nh = nh.SNodeHelper()

        # start
        l_nf.start()

        # give the fetcher threads time for their first fetch (daemons: they die with the process)
        time.sleep(15)

        # active article, as the view would get it
        gd.G_EVENTS.on("ARTICLE_INFO_RESPONSE", lambda p: print({k: p[k] for k in ("source", "title", "mode")}))
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        print(len(l_nf._lst_news_items), "items")

    # on error...
    except KeyboardInterrupt:
        # logger
        logging.warning("Interrupted.")
    
    # terminate
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
