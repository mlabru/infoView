# -*- coding: utf-8 -*-
"""
infoView 1.0
Newsfeed / View

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import copy
import html
import logging
import re
import sys
import time

# pygame
import pygame as pg

# infoView
import infoview.core.logsetup as lg
import infoview.core.state as gd
import infoview.core.settings as df
import infoview.core.i18n as i18n
import infoview.core.timesync as ts
import infoview.ui.fonts as vu

# newsfeed
import infoview.modules.newsfeed.config as nd

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# surface size (title only: source line + title line)
DI_SURFACE_HEIGHT = 60
DI_SURFACE_WIDTH = 800

# default max surface height (full article)
DI_MAX_HEIGHT = 400

# left/right margin for text (px)
DI_TEXT_MARGIN = 20

# description / full article text: font size, line height and bottom padding (px)
DI_TEXT_FONT_SIZE = 20

# title line: preferred font size, and the smallest one before a long title is cut with "…"
DI_TITLE_FONT_SIZE = 32
DI_TITLE_MIN_FONT_SIZE = 22
DI_LINE_HEIGHT = 26
DI_BOTTOM_PAD = 8

# lines of description shown in "description" mode
DI_DESCR_LINES = 3

# html tags inside feed descriptions
DRE_HTML_TAG = re.compile(r"<[^>]+>")
# space left before punctuation by a removed tag ("<a>França</a> ,")
DRE_SPACE_PUNCT = re.compile(r"\s+([,.;:!?)])")

# while waiting for articles, ask again every (sec)
DF_WAITING_RETRY = 1.

# fade out starts at this fraction of updateInterval
DF_FADE_START = .7
# fade out speed (alpha units per second: 255 in ~2.5 s)
DF_FADE_SPEED = 100.

# < SNewsFeedView >----------------------------------------------------------------------------

class SNewsFeedView:
    """
    newsfeed ticker: source + age line and title; grows upwards for the description / full
    article (mode, scroll and pause come from SNewsFeed in ARTICLE_INFO_RESPONSE); rotates the
    article every updateInterval with a fade out (time based), except while paused
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fi_width: int = DI_SURFACE_WIDTH, fi_max_height: int = DI_MAX_HEIGHT,
                 fi_min_details_height: int = 0):
        """
        constructor

        :param fi_width (int): surface width (usually the screen width)
        :param fi_max_height (int): max surface height, used when showing the full article
        :param fi_min_details_height (int): min height when showing details (e.g. to cover a whole
                                            strip above the ticker instead of cutting it in half)
        """
        # logger
        M_LOG.info(">> constructor")

        # surface width
        self._i_width: int = fi_width
        # max surface height
        self._i_max_height: int = max(fi_max_height, DI_SURFACE_HEIGHT)
        # min surface height with details
        self._i_min_details_height: int = min(fi_min_details_height, self._i_max_height)
        # current surface height (grows with description / full article)
        self._i_height: int = 0

        # last time mesured
        self._tm_last_update = time.perf_counter()

        # config dictionary (own copy, read only here)
        self._dct_config: dict = copy.deepcopy(nd.DDCT_CONFIG)

        # rebuild text surface ?
        self._v_rebuild_surface: bool = True

        # article rotation paused ? (user is reading description / full article)
        self._v_paused: bool = False

        # current article
        self._dct_article: dict = {}

        # events callback
        gd.G_EVENTS.on("ARTICLE_INFO_RESPONSE", self.on_article_info_response)

        # fonts
        self._fnt_l1 = pg.font.Font(df.DS_FONT_TEXT, 16)
        self._fnt_tx = pg.font.Font(df.DS_FONT_TEXT, DI_TEXT_FONT_SIZE)

        # create newsfeed, text and fade surfaces
        self._resize(DI_SURFACE_HEIGHT)

        # fully transparent
        self._i_alpha = 0

        # request first article
        gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})

    # -----------------------------------------------------------------------------------------
    def _article_age(self):
        """
        return article age string
        """
        # logger
        M_LOG.info(">> _article_age")

        # article timestamp
        lf_date = self._dct_article.get("date", 0)

        # no date (e.g. "waiting for articles" placeholder), or the system clock is not
        # synchronized yet (the age would be wrong: see infoview/core/timesync.py) ?
        if (not lf_date) or (not ts.GV_SYNCED):
            # no age to show
            return ""

        # age in minutes (a date in the future, e.g. clock/timezone skew, counts as "now")
        li_min = int(max(0., time.time() - lf_date) / 60)

        # less than one minute ?
        if li_min < 1:
            # article age
            return i18n.tr("nf.just_now")

        # less than one hour ?
        if li_min < 60:
            # article age
            return i18n.tr_n("nf.minutes_ago", li_min)

        # hours
        li_hour = li_min // 60

        # less than one day ?
        if li_hour < 24:
            # article age
            return i18n.tr_n("nf.hours_ago", li_hour)

        # days
        li_day = li_hour // 24

        # return article age
        return i18n.tr_n("nf.days_ago", li_day)

    # -----------------------------------------------------------------------------------------
    def _article_next(self):
        """
        return next article
        """
        # logger
        M_LOG.info(">> _article_next")

        # showing a real article (not the "waiting" placeholder, which has no date) ?
        # (otherwise the first article received would be skipped)
        if self._dct_article.get("date", 0):
            # next article (the model answers with ARTICLE_INFO_RESPONSE)
            gd.G_EVENTS.emit("ARTICLE_NEXT", {})

        # else,...
        else:
            # request article (articles may have arrived meanwhile)
            gd.G_EVENTS.emit("ARTICLE_INFO_REQUEST", {})

        # reset timer (even if no answer came)
        self._tm_last_update = time.perf_counter()

    # -----------------------------------------------------------------------------------------
    def _build_nf_surface(self, ff_dt: float):
        """
        build newsfeed surface (only when something changed)

        :param ff_dt (float): time elapsed since the current article was shown (sec)

        :returns (bool): True if the surface changed
        """

        # fade out start (sec)
        lf_fade_ini = self._dct_config["updateInterval"] * DF_FADE_START

        # fade alpha for this moment (0 until fade start, then grows with time up to 255;
        # no fade while the rotation is paused, the article stays on screen)
        li_alpha = 0 if (ff_dt < lf_fade_ini) or self._v_paused else \
                   min(int((ff_dt - lf_fade_ini) * DF_FADE_SPEED), 255)

        # rebuild text surface ?
        if self._v_rebuild_surface:
            # build text surface
            self._build_text_surface()

        # nothing changed since last frame ?
        elif li_alpha == self._i_alpha:
            # keep current surface
            return False

        # logger
        M_LOG.info(">> _build_nf_surface")

        # save alpha
        self._i_alpha = li_alpha

        # display the text (opaque, covers the whole surface)
        self._srf_nf.blit(self._srf_text, (0, 0))

        # fading out ?
        if li_alpha:
            # set fade alpha
            self._srf_fade.set_alpha(li_alpha)
            # apply fade over surface
            self._srf_nf.blit(self._srf_fade, (0, 0))

        # surface changed
        return True

    # -----------------------------------------------------------------------------------------
    def _build_text_surface(self):
        """
        build surface
        """
        # logger
        M_LOG.info(">> _build_text_surface")

        assert self._dct_article

        # debug
        M_LOG.debug("dct_article: %s", self._dct_article)

        # display mode ("title", "description" or "full")
        ls_mode = self._dct_article.get("mode", "title")

        # body lines (description / full article text), already wrapped
        llst_lines = self._body_lines(ls_mode)

        # surface height for this mode
        if "title" == ls_mode:
            # source line + title line only
            li_height = DI_SURFACE_HEIGHT

        # else,...
        else:
            # header + body lines (limited, the full article scrolls); the full article uses all
            # the space available (clean reading pane, nothing of the clock showing around it)
            li_height = self._i_max_height if "full" == ls_mode else \
                        min(max(DI_SURFACE_HEIGHT + len(llst_lines) * DI_LINE_HEIGHT + DI_BOTTOM_PAD,
                                self._i_min_details_height),
                            self._i_max_height)

        # height changed ?
        if li_height != self._i_height:
            # recreate surfaces
            self._resize(li_height)

        # fill surface with black
        self._srf_text.fill(df.DCLR_BG)

        # details panel over the clock: thin top border
        if "title" != ls_mode:
            pg.draw.line(self._srf_text, df.DCLR_ACCENT_DIM, (0, 0), (self._i_width, 0), 2)

        # source & age line >>>

        # build text of source line (source, age)
        ls_srce = self._dct_article.get("source", None) or \
                  self._dct_article.get("url", None) or ""
        # article age (empty if the article has no date)
        ls_age = self._article_age()
        # build text of source line (source, age)
        ls_srce = f"{ls_srce}, {ls_age}" if ls_age else ls_srce
        # render with selected font
        lsrf_srce = self._fnt_l1.render(self._fit_text(self._fnt_l1, ls_srce), True, df.DCLR_ACCENT)

        # text rectangle
        lrct_srce = lsrf_srce.get_rect(center=(self._i_width / 2, 10))
        # copy to text surface
        self._srf_text.blit(lsrf_srce, lrct_srce)

        # title line >>>

        # build text of title line
        ls_title = self._dct_article.get("title", None) or \
                   self._dct_article.get("description", None) or ""
        # render with selected font
        # font: the preferred size, smaller for a long title (down to DI_TITLE_MIN_FONT_SIZE);
        # only a title that doesn't fit even then is cut (the whole text is in the details)
        lfnt_title = vu.font(df.DS_FONT_TEXT, vu.fit_size_all(df.DS_FONT_TEXT, [ls_title], self._i_width - 2 * DI_TEXT_MARGIN,
                                                              DI_TITLE_FONT_SIZE, DI_TITLE_MIN_FONT_SIZE))

        lsrf_title = lfnt_title.render(self._fit_text(lfnt_title, ls_title), True, df.DCLR_TEXT_BRIGHT)

        # text rectangle
        lrct_title = lsrf_title.get_rect(center=(self._i_width / 2, 35))
        # copy to text surface
        self._srf_text.blit(lsrf_title, lrct_title)

        # body (description / full article) >>>

        # body area
        lrct_body = pg.Rect(0, DI_SURFACE_HEIGHT, self._i_width, li_height - DI_SURFACE_HEIGHT)

        # max scroll: last line at the bottom of the body area
        li_scroll_max = max(0, len(llst_lines) * DI_LINE_HEIGHT + DI_BOTTOM_PAD - lrct_body.height)

        # full article: tell the model how far it can scroll and one page (the visible lines
        # minus one, so the last line of a page is the first of the next: nothing is skipped)
        if "full" == ls_mode:
            gd.G_EVENTS.emit("ARTICLE_SCROLL_RANGE",
                             {"max": li_scroll_max,
                              "page": max(1, lrct_body.height // DI_LINE_HEIGHT - 1) * DI_LINE_HEIGHT})

        # any body ?
        if llst_lines and (lrct_body.height > 0):
            # scroll position (asked by the model, limited to the text)
            li_scroll = min(max(0, int(self._dct_article.get("scroll", 0))), li_scroll_max)

            # draw only inside the body area
            self._srf_text.set_clip(lrct_body)

            # for all lines...
            for li_line, (ls_line, lclr_line) in enumerate(llst_lines):
                # line position
                li_y = lrct_body.top + li_line * DI_LINE_HEIGHT - li_scroll

                # visible ?
                if (li_y + DI_LINE_HEIGHT > lrct_body.top) and (li_y < lrct_body.bottom):
                    # render line
                    self._srf_text.blit(self._fnt_tx.render(ls_line, True, lclr_line), (DI_TEXT_MARGIN, li_y))

            # draw anywhere again
            self._srf_text.set_clip(None)

        # reset flag rebuild surface
        self._v_rebuild_surface = False

    # -----------------------------------------------------------------------------------------
    def _body_lines(self, fs_mode: str) -> list:
        """
        body text lines for a display mode

        :param fs_mode (str): "title", "description" or "full"

        :returns (list): [(line, color), ...] already wrapped to the surface width
        """
        # title only ?
        if "title" == fs_mode:
            # no body
            return []

        # description as plain text
        ls_descr = self._plain_text(self._dct_article.get("description", None) or "")

        # wrapped description
        llst_descr = self._wrap_text(self._fnt_tx, ls_descr)

        # description mode ?
        if "description" == fs_mode:
            # more lines than shown ?
            if len(llst_descr) > DI_DESCR_LINES:
                # cut and mark the last shown line
                llst_descr = llst_descr[:DI_DESCR_LINES]
                llst_descr[-1] = self._fit_text(self._fnt_tx, llst_descr[-1] + " …")

            # return description lines
            return [(ls_line, df.DCLR_TEXT) for ls_line in llst_descr]

        # full article: whole description + link (the article web page itself can't be shown)
        llst_lines = [(ls_line, df.DCLR_TEXT) for ls_line in llst_descr]

        # article URL
        ls_url = self._dct_article.get("url", None) or ""

        # any URL ?
        if ls_url:
            # blank line + URL
            llst_lines += [("", df.DCLR_TEXT_DIM)] + \
                          [(ls_line, df.DCLR_TEXT_DIM) for ls_line in self._wrap_text(self._fnt_tx, ls_url)]

        # return lines
        return llst_lines

    # -----------------------------------------------------------------------------------------
    @staticmethod
    def _plain_text(fs_text: str) -> str:
        """
        convert a feed description (may contain html) to plain text

        :param fs_text (str): text

        :returns (str): plain text, whitespace collapsed
        """
        # remove tags, decode entities, collapse whitespace
        ls_text = " ".join(html.unescape(DRE_HTML_TAG.sub(" ", fs_text)).split())

        # no space before punctuation
        return DRE_SPACE_PUNCT.sub(r"\1", ls_text)

    # -----------------------------------------------------------------------------------------
    def _wrap_text(self, f_font, fs_text: str) -> list:
        """
        word wrap text to the surface width (minus margins)

        :param f_font (pg.font.Font): font used to render the text
        :param fs_text (str): text

        :returns (list): lines
        """
        # available width
        li_max = self._i_width - 2 * DI_TEXT_MARGIN

        # lines
        llst_lines = []
        # current line
        ls_line = ""

        # for all words...
        for ls_word in fs_text.split():
            # line with this word
            ls_try = f"{ls_line} {ls_word}" if ls_line else ls_word

            # fits ?
            if f_font.size(ls_try)[0] <= li_max:
                # keep going
                ls_line = ls_try
                continue

            # close current line
            if ls_line:
                llst_lines.append(ls_line)

            # word alone (truncated if wider than the whole line)
            ls_line = self._fit_text(f_font, ls_word)

        # last line
        if ls_line:
            llst_lines.append(ls_line)

        # return lines
        return llst_lines

    # -----------------------------------------------------------------------------------------
    def _resize(self, fi_height: int):
        """
        (re)create the newsfeed, text and fade surfaces with a new height

        :param fi_height (int): surface height
        """
        # save height
        self._i_height = fi_height

        # create newsfeed surface
        self._srf_nf = pg.Surface((self._i_width, fi_height))

        # create text surface
        self._srf_text = pg.Surface((self._i_width, fi_height))

        # create fade surface
        self._srf_fade = pg.Surface((self._i_width, fi_height))

        # fill surface with black
        self._srf_fade.fill(df.DCLR_BG)

    # -----------------------------------------------------------------------------------------
    def _fit_text(self, f_font, fs_text: str) -> str:
        """
        truncate text with an ellipsis so it fits the surface width (minus margins)

        :param f_font (pg.font.Font): font used to render the text
        :param fs_text (str): text

        :returns (str): text that fits
        """
        # return text that fits
        return vu.fit_text(f_font, fs_text, self._i_width - 2 * DI_TEXT_MARGIN)

    # -----------------------------------------------------------------------------------------
    def get_surface(self):
        """
        return surface
        """
        # logger
        M_LOG.info(">> get_surface")

        # return surface
        return self._srf_nf

    # -----------------------------------------------------------------------------------------
    def on_article_info_response(self, fdct_payload: dict):
        """
        article info response callback

        :param fdct_payload (dict): article data
        """
        # logger
        M_LOG.info(">> on_article_info_response")

        # check input
        assert fdct_payload

        # restart the display time (also the details timeout: a button was pressed)
        self._tm_last_update = time.perf_counter()

        # same article, same display, nothing faded (the "waiting" placeholder asked again every
        # DF_WAITING_RETRY, ▲ at the top) ? the surface on screen is right: no redraw
        if (fdct_payload == self._dct_article) and (0 == self._i_alpha):
            return

        # save article (and how to display it)
        self._dct_article = fdct_payload

        # article rotation paused (user is reading description / full article) ?
        self._v_paused = bool(fdct_payload.get("paused", False))

        # new content: rebuild the surface, no fade
        self._v_rebuild_surface = True
        self._i_alpha = 0

    # -----------------------------------------------------------------------------------------
    def start(self):
        """
        start view (draw the first frame)
        """
        # logger
        M_LOG.info(">> start")

        # reset timer
        self._tm_last_update = time.perf_counter()

        # draw the first frame
        self.update()

    # -----------------------------------------------------------------------------------------
    def update(self):
        """
        called by the main thread every frame: advance article on time and redraw if needed

        :returns (bool): True if the surface changed
        """
        # elapsed time (sec)
        lf_dt = time.perf_counter() - self._tm_last_update

        # time to show the next article ? (not while the user is reading details; while
        # waiting for articles, ask again more often)
        lf_interval = self._dct_config["updateInterval"] if self._dct_article.get("date", 0) else DF_WAITING_RETRY

        if (not self._v_paused) and (lf_dt >= lf_interval):
            # next article (resets timer)
            self._article_next()

            # elapsed time (sec)
            lf_dt = 0.

        # details untouched for too long (every button press restarts the time) ? back to the
        # titles: on a kiosk nobody may be reading anymore, and the panel covers the clock
        elif self._v_paused and self._dct_config["detailsTimeout"] and (lf_dt >= self._dct_config["detailsTimeout"]):
            # the model resets the details and answers (resets timer)
            gd.G_EVENTS.emit("ARTICLE_LESS_DETAILS", {})

            # elapsed time (sec)
            lf_dt = 0.

        # build newsfeed surface
        return self._build_nf_surface(lf_dt)

    # =========================================================================================
    # data
    # =========================================================================================

    # -----------------------------------------------------------------------------------------
    @property
    def i_height(self) -> int:
        """surface height (changes with the display mode)"""
        return self._i_height

# ---------------------------------------------------------------------------------------------
# this is the bootstrap process

if "__main__" == __name__:
    # logger
    lg.setup()

    # initialize pygame library
    pg.init()

    # icon to the NewsFeed frame
    l_icon = pg.image.load(df.DS_ICON_APP)
    pg.display.set_icon(l_icon)

    # size of the window
    lscreen = pg.display.set_mode((DI_SURFACE_WIDTH, DI_SURFACE_HEIGHT))

    # caption
    pg.display.set_caption("NewsFeed")

    # keep things running
    gd.GV_KEEP_RUN = True

    # the view needs the model (articles) and the node helper (fetchers), as in infoview/app.py
    import infoview.modules.newsfeed.model as nfm
    import infoview.modules.newsfeed.helper as nfh

    l_nf = nfm.SNewsFeed()
    l_nh = nfh.SNodeHelper()
    l_nf.start()

    # create view
    lview = SNewsFeedView()

    # start viewer
    lview.start()

    # caps the main loop so it doesn't redraw faster than needed
    l_clock = pg.time.Clock()

    try:
        # for ever....
        while gd.GV_KEEP_RUN:
            # for all events
            for l_evt in pg.event.get():
                # quit ?
                if pg.QUIT == l_evt.type:
                    # stop things
                    gd.GV_KEEP_RUN = False

            # asked to stop while handling events above ?
            if not gd.GV_KEEP_RUN:
                # don't touch the display again, just leave
                break

            # update view
            lview.update()

            # build screen
            lscreen.blit(lview.get_surface(), (0, 0))

            # update the time displayed
            pg.display.update()

            # yield to the scheduler, no need to redraw faster than this
            l_clock.tick(30)

        # quit
        pg.quit()

    # on error...
    except KeyboardInterrupt:
        # stop things
        gd.GV_KEEP_RUN = False

        # logger
        logging.warning("Interrupted.")

    # terminate
    sys.exit(0)

# < the end >----------------------------------------------------------------------------------
    