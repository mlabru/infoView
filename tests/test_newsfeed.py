# -*- coding: utf-8 -*-
"""
tests: newsfeed module — fetcher (local RSS server), error classification, model (filters,
navigation, display state), view (height per mode)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import copy
import threading
import time
import unittest

# pygame
import pygame as pg

# infoView
import infoview.core.config as cfg
import infoview.core.i18n as i18n
import infoview.core.net as hp
import infoview.core.state as gd
import infoview.core.timesync as ts
import infoview.ui.fonts as vu
import infoview.modules.newsfeed.config as nfc
import infoview.modules.newsfeed.fetcher as nff
import infoview.modules.newsfeed.helper as nfh
import infoview.modules.newsfeed.model as nfm
import infoview.modules.newsfeed.view as nfv

# tests
from tests import support

# < TestFetcher >------------------------------------------------------------------------------

class TestFetcher(unittest.TestCase):
    """SNewsfeedFetcher._fetch_get against local servers"""

    def setUp(self):
        self._lst_err = []

    def _fetcher(self, fs_url):
        l_ftc = nff.SNewsfeedFetcher(fs_url, 120, False)
        l_ftc.on_error(lambda f, u, e: self._lst_err.append(e))
        return l_ftc

    def test_parse_charset_dates_ttl(self):
        with support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS)}) as l_srv:
            l_ftc = self._fetcher(l_srv.url("/rss"))
            llst = l_ftc._fetch_get()

        # ISO-8859-1 decoded; the item without a date dropped; both date formats parsed
        self.assertEqual([x["title"] for x in llst], ["Notícia & acentuação", "Segunda"])
        self.assertEqual(llst[0]["timestamp"] - llst[1]["timestamp"], 3600)

        # <ttl>10</ttl> (minutes): reload interval 120 s -> 600 s
        self.assertEqual(l_ftc.i_reload_interval, 600)
        self.assertEqual(self._lst_err, [])

    def test_min_reload_interval(self):
        l_ftc = nff.SNewsfeedFetcher("http://x", 10, False)
        self.assertEqual(l_ftc.i_reload_interval, nfc.DI_MIN_RELOAD)

        # same URL configured again: a shorter interval wins, never below the minimum
        l_ftc = nff.SNewsfeedFetcher("http://x", 300, False)
        l_ftc.i_reload_interval = 30
        self.assertEqual(l_ftc.i_reload_interval, 300)
        l_ftc.i_reload_interval = 90
        self.assertEqual(l_ftc.i_reload_interval, 90)

    def test_http_error(self):
        with support.LocalServer({}) as l_srv:
            self.assertIsNone(self._fetcher(l_srv.url("/missing"))._fetch_get())

        self.assertEqual(self._lst_err, [{"code": "404", "message": "HTTP 404"}])

    def test_no_connection_and_timeout(self):
        self.assertIsNone(self._fetcher(support.closed_port_url("/rss"))._fetch_get())

        lf_timeout = nff.DF_FETCH_TIMEOUT
        try:
            nff.DF_FETCH_TIMEOUT = 1.
            with support.MuteServer() as l_srv:
                self.assertIsNone(self._fetcher(l_srv.url("/rss"))._fetch_get())
        finally:
            nff.DF_FETCH_TIMEOUT = lf_timeout

        self.assertEqual([x["code"] for x in self._lst_err], ["URLError", "URLError"])

    def test_not_a_feed(self):
        with support.LocalServer({"/html": (200, "text/html", b"<html><body>no feed</body></html>")}) as l_srv:
            self.assertIsNone(self._fetcher(l_srv.url("/html"))._fetch_get())

        self.assertEqual(len(self._lst_err), 1)

    def test_cycle_survives_listener_error(self):
        def lfn_boom(fs_url):
            raise RuntimeError("listener bug")

        with support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS)}) as l_srv:
            l_ftc = self._fetcher(l_srv.url("/rss"))
            l_ftc.on_receive(lfn_boom)

            # logged, not raised: the thread would keep polling (and retries sooner)
            self.assertFalse(l_ftc._cycle())

        self.assertEqual(len(l_ftc.lst_items), 2)

    def test_not_modified(self):
        llst_broadcasts = []

        with support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS, '"v1"')}) as l_srv:
            l_ftc = self._fetcher(l_srv.url("/rss"))
            l_ftc.on_receive(llst_broadcasts.append)

            # first: downloaded and broadcast
            self.assertTrue(l_ftc._cycle())
            llst_first = l_ftc.lst_items

            # second: If-None-Match -> 304, same items, broadcast again (the model filters the
            # items again: those that became too old leave the ticker)
            self.assertTrue(l_ftc._cycle())

        self.assertEqual(l_srv.dct_hits["/rss"], 2)
        self.assertIs(l_ftc.lst_items, llst_first)
        self.assertEqual(len(llst_broadcasts), 2)
        self.assertEqual(self._lst_err, [])

    def test_user_agent(self):
        # the app's own User-Agent (infoview/core/net.py), the same as the weather fetcher's
        with support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS)}) as l_srv:
            self._fetcher(l_srv.url("/rss"))._fetch_get()

        self.assertEqual(l_srv.lst_agents, [hp.DS_USER_AGENT])

    def test_ttl_follows_the_feed(self):
        l_ftc = nff.SNewsfeedFetcher("http://x", 300, False)

        # a longer ttl makes the interval longer ...
        l_ftc.on_fetch_ttl("20")
        self.assertEqual(l_ftc.i_reload_interval, 1200)

        # ... a shorter one brings it back down, never below the configured interval
        l_ftc.on_fetch_ttl("10")
        self.assertEqual(l_ftc.i_reload_interval, 600)
        l_ftc.on_fetch_ttl("1")
        self.assertEqual(l_ftc.i_reload_interval, 300)

        # ttl gone (or invalid): the configured interval
        l_ftc.on_fetch_ttl("20")
        l_ftc.on_fetch_ttl(None)
        self.assertEqual(l_ftc.i_reload_interval, 300)
        l_ftc.on_fetch_ttl("20")
        l_ftc.on_fetch_ttl("abc")
        self.assertEqual(l_ftc.i_reload_interval, 300)

        # capped at 24 h
        l_ftc.on_fetch_ttl(str(48 * 60))
        self.assertEqual(l_ftc.i_reload_interval, 86400)

    def test_shorter_interval_keeps_the_ttl(self):
        # same URL configured again with a shorter interval while the feed's ttl is longer
        l_ftc = nff.SNewsfeedFetcher("http://x", 300, False)
        l_ftc.on_fetch_ttl("10")
        l_ftc.i_reload_interval = 120
        self.assertEqual(l_ftc.i_reload_interval, 600)

        # the ttl disappears: the new configured interval
        l_ftc.on_fetch_ttl(None)
        self.assertEqual(l_ftc.i_reload_interval, 120)

    def test_response_too_big(self):
        li_max = hp.DI_MAX_BYTES
        try:
            hp.DI_MAX_BYTES = 100
            with support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS)}) as l_srv:
                self.assertIsNone(self._fetcher(l_srv.url("/rss"))._fetch_get())
        finally:
            hp.DI_MAX_BYTES = li_max

        self.assertEqual(self._lst_err[-1]["code"], "ValueError")

    def test_cycle_result(self):
        with support.LocalServer({"/rss": (200, "application/rss+xml", support.DBY_RSS)}) as l_srv:
            self.assertTrue(self._fetcher(l_srv.url("/rss"))._cycle())
            self.assertFalse(self._fetcher(l_srv.url("/missing"))._cycle())

    def test_broadcasts_serialized(self):
        gd.G_EVENTS.clear()
        l_nh = nfh.SNodeHelper()

        # two feeds (fake fetchers: only lst_items is read)
        class LFake:
            lst_items = []
        l_nh._fetchers = {"http://a": LFake(), "http://b": LFake()}

        # a slow listener that notices overlapping broadcasts
        ldct = {"inside": 0, "overlaps": 0, "calls": 0}

        def lfn_slow(fdct_payload):
            ldct["inside"] += 1
            ldct["overlaps"] += ldct["inside"] > 1
            time.sleep(.05)
            ldct["calls"] += 1
            ldct["inside"] -= 1

        gd.G_EVENTS.on("NEWS_ITEMS", lfn_slow)

        llst_threads = [threading.Thread(target=l_nh.broadcast_feeds, args=(u,)) for u in ("http://a", "http://b") * 3]
        for l_thr in llst_threads:
            l_thr.start()
        for l_thr in llst_threads:
            l_thr.join()

        gd.G_EVENTS.clear()
        self.assertEqual((ldct["calls"], ldct["overlaps"]), (6, 0))

    def test_error_classification(self):
        self.assertEqual(nfh.fetch_error_type({"code": "URLError"}), "MODULE_ERROR_NO_CONNECTION")
        self.assertEqual(nfh.fetch_error_type({"code": "401", "message": "Unauthorized"}), "MODULE_ERROR_UNAUTHORIZED")
        self.assertEqual(nfh.fetch_error_type({"code": "500", "message": "HTTP 500"}), "MODULE_ERROR_UNSPECIFIED")

# < TestModel >--------------------------------------------------------------------------------

DS_URL = "http://feed/1"

def _items(fi_n: int, **kw) -> list:
    """n news items, newest first, one hour apart"""
    lf_now = time.time()
    return [dict({"title": f"t{i}", "description": f"d{i}", "url": f"http://x/{i}",
                  "timestamp": lf_now - i * 3600}, **kw) for i in range(fi_n)]

class TestModel(unittest.TestCase):
    """SNewsFeed: filters, navigation and display state (no fetchers: items are injected)"""

    def setUp(self):
        gd.G_EVENTS.clear()

        # model with one known feed
        self._model = nfm.SNewsFeed()
        self._model._dct_config["feeds"] = [{"title": "Fonte", "url": DS_URL}]
        self._model._reset_details()

        # last article info sent to the view
        self._lst_info = []
        gd.G_EVENTS.on("ARTICLE_INFO_RESPONSE", self._lst_info.append)

    def tearDown(self):
        gd.G_EVENTS.clear()

    def _feed(self, fdct_feeds: dict):
        """new items, as a fetcher would send them, taken by the main thread at once"""
        self._model.generate_feed(fdct_feeds)
        self._model._apply_pending()

    def test_new_list_taken_by_the_main_thread(self):
        self._feed({DS_URL: _items(3)})
        gd.G_EVENTS.emit("ARTICLE_NEXT", {})

        # a fetcher thread builds a new list (a newer item on top) ...
        lnew = dict(_items(1)[0], title="newer", url="http://x/new", timestamp=time.time() + 60)
        l_thread = threading.Thread(target=self._model.generate_feed, args=({DS_URL: [lnew] + _items(3)},))
        l_thread.start()
        l_thread.join()

        # ... but the list and the active index are untouched until the main thread asks
        self.assertEqual((len(self._model._lst_news_items), self._model._i_active_item), (3, 1))

        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        self.assertEqual((len(self._model._lst_news_items), self._model._i_active_item), (4, 2))
        self.assertEqual(self._lst_info[-1]["title"], "t1")

    def test_article_being_read_not_replaced(self):
        llst = _items(5)
        self._feed({DS_URL: llst})
        self._model._i_active_item = 4

        # reading t4's full article
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual((self._lst_info[-1]["title"], self._lst_info[-1]["mode"]), ("t4", "full"))

        # t4 leaves the feed meanwhile: still t4 while reading
        self._model.generate_feed({DS_URL: llst[:3]})
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual((self._lst_info[-1]["title"], self._lst_info[-1]["mode"]), ("t4", "full"))

        # back to the titles: the new list is taken (t4 gone: the last item)
        gd.G_EVENTS.emit("ARTICLE_LESS_DETAILS", {})
        self.assertEqual((self._lst_info[-1]["title"], self._lst_info[-1]["mode"]), ("t2", "title"))
        self.assertEqual(len(self._model._lst_news_items), 3)

    def test_placeholder_reasons(self):
        i18n.DS_LANGUAGE = "pt_BR"

        # waiting, then a feed error, then a successful fetch (with no items left)
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        gd.G_EVENTS.emit("NEWSFEED_ERROR", {"error_type": "MODULE_ERROR_NO_CONNECTION"})
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        gd.G_EVENTS.emit("NEWSFEED_ERROR", {"error_type": "MODULE_ERROR_UNSPECIFIED"})
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        self._feed({DS_URL: []})
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})

        # no feeds configured
        self._model._dct_config["feeds"] = []
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})

        self.assertEqual([x["title"] for x in self._lst_info],
                         ["aguardando notícias", "notícias indisponíveis (sem conexão)",
                          "notícias indisponíveis (erro no feed)", "aguardando notícias", "nenhum feed configurado"])

    def test_sort_and_source(self):
        llst = _items(3)
        self._feed({DS_URL: list(reversed(llst)), "http://unknown": _items(2)})

        # newest first; unknown feeds ignored; source title added
        self.assertEqual([x["title"] for x in self._model._lst_news_items], ["t0", "t1", "t2"])
        self.assertEqual({x["sourceTitle"] for x in self._model._lst_news_items}, {"Fonte"})

    def test_fetcher_items_not_modified(self):
        llst = _items(2)
        lsrc = copy.deepcopy(llst)
        self._feed({DS_URL: llst})
        self.assertEqual(llst, lsrc)

    def test_filters(self):
        ldct = self._model._dct_config
        ldct["prohibitedWords"] = ["PROIBIDA"]
        ldct["maxNewsItems"] = 2
        ldct["ignoreOlderThan"] = 5 * 3600

        llst = _items(8)
        llst[1]["title"] = "notícia proibida"
        self._feed({DS_URL: llst})

        # t1 dropped (word, case insensitive), t5.. too old, then capped to 2
        self.assertEqual([x["title"] for x in self._model._lst_news_items], ["t0", "t2"])

    def test_start_end_tags(self):
        ldct = self._model._dct_config
        ldct.update(startTags=["AO VIVO: "], endTags=[" (vídeo)"], removeStartTags="title", removeEndTags="description")

        llst = _items(1, title="AO VIVO: jogo (vídeo)", description="AO VIVO: resumo (vídeo)")
        self._feed({DS_URL: llst})

        # title: only the start tag removed; description: only the end tag
        ldct_item = self._model._lst_news_items[0]
        self.assertEqual((ldct_item["title"], ldct_item["description"]), ("jogo (vídeo)", "AO VIVO: resumo"))

    def test_invalid_tag_target(self):
        with self.assertLogs("infoview.core.config", "WARNING"):
            ldct = cfg.merge(nfc.DDCT_DEFAULTS, {"removeStartTags": "both", "removeEndTags": "yes"}, "newsfeed", nfc.DDCT_RULES)
        self.assertEqual((ldct["removeStartTags"], ldct["removeEndTags"]), ("both", ""))

    def test_navigation_wraps(self):
        self._feed({DS_URL: _items(3)})

        for _ in range(3):
            gd.G_EVENTS.emit("ARTICLE_NEXT", {})
        self.assertEqual(self._model._i_active_item, 0)

        gd.G_EVENTS.emit("ARTICLE_PREVIOUS", {})
        self.assertEqual(self._lst_info[-1]["title"], "t2")

    def test_details_state_machine(self):
        self._feed({DS_URL: _items(3)})

        # titles -> description -> full article -> scroll down / up (never above 0)
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual((self._lst_info[-1]["mode"], self._lst_info[-1]["paused"]), ("description", True))

        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual(self._lst_info[-1]["mode"], "full")

        # the view lays the text out (scrollLength 0: the step is one page)
        gd.G_EVENTS.emit("ARTICLE_SCROLL_RANGE", {"max": 1000, "page": 300})

        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual(self._lst_info[-1]["scroll"], 300)

        gd.G_EVENTS.emit("ARTICLE_SCROLL_UP", {})
        gd.G_EVENTS.emit("ARTICLE_SCROLL_UP", {})
        self.assertEqual(self._lst_info[-1]["scroll"], 0)

        # back to titles: rotation resumes
        gd.G_EVENTS.emit("ARTICLE_LESS_DETAILS", {})
        self.assertEqual((self._lst_info[-1]["mode"], self._lst_info[-1]["paused"]), ("title", False))

    def test_scroll_limited_to_the_text(self):
        self._feed({DS_URL: _items(1)})
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        gd.G_EVENTS.emit("ARTICLE_SCROLL_RANGE", {"max": 700, "page": 312})

        # many downs: stops at the end of the text
        for _ in range(6):
            gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual(self._lst_info[-1]["scroll"], 700)

        # the first up already moves
        gd.G_EVENTS.emit("ARTICLE_SCROLL_UP", {})
        self.assertEqual(self._lst_info[-1]["scroll"], 700 - 312)

        # a fixed step (scrollLength) still applies, inside the same limits
        self._model._dct_config["scrollLength"] = 100
        gd.G_EVENTS.emit("ARTICLE_SCROLL_UP", {})
        self.assertEqual(self._lst_info[-1]["scroll"], 700 - 312 - 100)

    def test_active_article_kept_on_refresh(self):
        llst = _items(3)
        self._feed({DS_URL: llst})

        # reading t1's description
        gd.G_EVENTS.emit("ARTICLE_NEXT", {})
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual(self._lst_info[-1]["title"], "t1")

        # refresh: a newer item on top
        lnew = dict(llst[0], title="newer", url="http://x/new", timestamp=llst[0]["timestamp"] + 60)
        self._feed({DS_URL: [lnew] + llst})

        # the full article is still t1's
        gd.G_EVENTS.emit("ARTICLE_MORE_DETAILS", {})
        self.assertEqual((self._lst_info[-1]["title"], self._lst_info[-1]["mode"]), ("t1", "full"))

    def test_index_limited_when_the_list_shrinks(self):
        llst = _items(5)
        self._feed({DS_URL: llst})
        self._model._i_active_item = 4

        # t4 is gone and the list is shorter: the last item, not the "waiting" placeholder
        self._feed({DS_URL: llst[:2]})
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        self.assertEqual(self._lst_info[-1]["title"], "t1")

        # no items at all
        self._feed({DS_URL: []})
        self.assertEqual(self._model._i_active_item, 0)

    def test_toggle_full_on_last_item_wraps(self):
        self._feed({DS_URL: _items(2)})
        self._model._i_active_item = 1

        gd.G_EVENTS.emit("ARTICLE_TOGGLE_FULL", {})   # description
        gd.G_EVENTS.emit("ARTICLE_TOGGLE_FULL", {})   # full article
        gd.G_EVENTS.emit("ARTICLE_TOGGLE_FULL", {})   # full: next item (wraps), titles again

        self.assertEqual((self._model._i_active_item, self._lst_info[-1]["mode"]), (0, "title"))

    def test_placeholder_without_items(self):
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        self.assertEqual((self._lst_info[-1]["date"], self._lst_info[-1]["mode"]), (0, "title"))

    def test_details_on_placeholder_dont_block_new_items(self):
        # ▼ (or Enter) tapped while "waiting for articles" (e.g. at boot, no network yet)
        for ls_action in ("ARTICLE_MORE_DETAILS", "ARTICLE_TOGGLE_FULL"):
            with self.subTest(ls_action):
                self.setUp()
                gd.G_EVENTS.emit(ls_action, {})

                # nothing to detail: still the titles, rotation not paused
                self.assertEqual((self._lst_info[-1]["date"], self._lst_info[-1]["mode"],
                                  self._lst_info[-1]["paused"]), (0, "title", False))

                # items arrive: taken at the view's next request (not stuck on "waiting")
                self._model.generate_feed({DS_URL: _items(2)})
                gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
                self.assertEqual(self._lst_info[-1]["title"], "t0")
                self.tearDown()

    def test_placeholder_all_filtered(self):
        i18n.DS_LANGUAGE = "pt_BR"

        # items received, all older than ignoreOlderThan
        self._model._dct_config["ignoreOlderThan"] = 3600
        self._feed({DS_URL: _items(3, timestamp=time.time() - 2 * 3600)})
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        self.assertEqual(self._lst_info[-1]["title"], "nenhuma notícia recente")

        # a recent item: shown
        self._feed({DS_URL: _items(1)})
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})
        self.assertEqual(self._lst_info[-1]["title"], "t0")

# < TestView >---------------------------------------------------------------------------------

class TestView(unittest.TestCase):
    """SNewsFeedView: surface height per display mode"""

    @classmethod
    def setUpClass(cls):
        pg.init()

    def setUp(self):
        gd.G_EVENTS.clear()

    def tearDown(self):
        gd.G_EVENTS.clear()

    def _view_with(self, fs_mode, fs_descr="uma descrição curta"):
        l_view = nfv.SNewsFeedView(800, 416, 156)
        l_view.on_article_info_response({"title": "título", "source": "Fonte", "date": time.time(),
                                         "description": fs_descr, "url": "http://x/1",
                                         "mode": fs_mode, "scroll": 0, "paused": fs_mode != "title"})
        l_view.update()
        return l_view

    def test_heights(self):
        self.assertEqual(self._view_with("title").i_height, nfv.DI_SURFACE_HEIGHT)
        # description: at least the min height (covers the weather strip)
        self.assertEqual(self._view_with("description").i_height, 156)
        # full article: the whole reading pane
        self.assertEqual(self._view_with("full").i_height, 416)

    def test_scroll_range_one_page(self):
        llst_range = []
        gd.G_EVENTS.on("ARTICLE_SCROLL_RANGE", llst_range.append)

        self._view_with("full", "palavra " * 600)

        # body 416 - 60 = 356 px = 13 lines of 26 px: one page = 12 lines (one line repeats)
        self.assertEqual(llst_range[-1]["page"], 12 * nfv.DI_LINE_HEIGHT)
        self.assertGreater(llst_range[-1]["max"], 0)

        # short text: nothing to scroll
        self._view_with("full", "curta")
        self.assertEqual(llst_range[-1]["max"], 0)

    def test_no_redraw_for_the_same_answer(self):
        # waiting for articles: the view asks again every DF_WAITING_RETRY, same placeholder
        nfm.SNewsFeed()
        l_view = nfv.SNewsFeedView(800, 416, 156)
        l_view.start()
        self.assertFalse(l_view.update())

        l_view._tm_last_update -= nfv.DF_WAITING_RETRY + .1
        self.assertFalse(l_view.update())

        # the only article, faded out, answered again (rotation): redrawn
        ldct_art = {"title": "título", "source": "Fonte", "date": time.time(), "description": "",
                    "url": "", "mode": "title", "scroll": 0, "paused": False}
        l_view.on_article_info_response(ldct_art)
        self.assertTrue(l_view.update())

        l_view._i_alpha = 255
        l_view.on_article_info_response(dict(ldct_art))
        self.assertTrue(l_view.update())

    def test_details_timeout(self):
        llst_less = []
        gd.G_EVENTS.on("ARTICLE_LESS_DETAILS", llst_less.append)

        l_view = self._view_with("description")
        l_view._dct_config["detailsTimeout"] = 60

        # recent touch: stays
        l_view._tm_last_update -= 59
        l_view.update()
        self.assertEqual(llst_less, [])

        # untouched for the timeout: back to titles
        l_view._tm_last_update -= 2
        l_view.update()
        self.assertEqual(len(llst_less), 1)

        # 0 = never
        l_view = self._view_with("full")
        l_view._dct_config["detailsTimeout"] = 0
        l_view._tm_last_update -= 3600
        l_view.update()
        self.assertEqual(len(llst_less), 1)

    def test_long_title_shrinks_before_cutting(self):
        llst_cuts = []
        lfn_fit = vu.fit_text

        def lfn_record(f, t, w):
            ls_fit = lfn_fit(f, t, w)
            if ls_fit != t:
                llst_cuts.append(t)
            return ls_fit

        try:
            vu.fit_text = lfn_record
            # ~60 characters: too wide at 32 px, fits at a smaller size
            ls_long = "Governo anuncia novo pacote de medidas para conter a inflação"
            l_view = self._view_with("title")
            l_view._dct_article["title"] = ls_long
            l_view._v_rebuild_surface = True
            l_view.update()
            self.assertEqual(llst_cuts, [])

            # far too long even at the smallest size: cut with "…"
            l_view._dct_article["title"] = ls_long * 3
            l_view._v_rebuild_surface = True
            l_view.update()
            self.assertEqual(llst_cuts, [ls_long * 3])
        finally:
            vu.fit_text = lfn_fit

    def test_html_to_plain_text(self):
        self.assertEqual(nfv.SNewsFeedView._plain_text('o <a href="x">Halloween</a> , e <b>mais</b>. Fim &amp; ok'),
                         "o Halloween, e mais. Fim & ok")

    def test_article_age(self):
        l_view = self._view_with("title")

        for lf_ago, ls_age in ((0, "agora mesmo"), (61, "há 1 minuto"), (3 * 3600 + 5, "há 3 horas"),
                               (2 * 86400 + 5, "há 2 dias"), (-600, "agora mesmo")):
            l_view._dct_article["date"] = time.time() - lf_ago
            self.assertEqual(l_view._article_age(), ls_age)

        l_view._dct_article["date"] = 0
        self.assertEqual(l_view._article_age(), "")

        # system clock not synchronized yet: the age would be wrong, not shown
        l_view._dct_article["date"] = time.time() - 3600
        try:
            ts.GV_SYNCED = False
            self.assertEqual(l_view._article_age(), "")
        finally:
            ts.GV_SYNCED = True

# < the end >----------------------------------------------------------------------------------
