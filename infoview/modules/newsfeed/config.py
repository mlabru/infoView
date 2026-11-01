# -*- coding: utf-8 -*-
"""
infoView 1.0
Newsfeed / configuration

DDCT_DEFAULTS: the code defaults (every key is used by the code; times in seconds).
DDCT_RULES: limits / accepted values of the user's values (a value out of them: the default).
DDCT_CONFIG: the effective configuration = defaults + [newsfeed] section of the user's config
file (infoView.toml, see infoview/core/config.py), validated. The code reads only DDCT_CONFIG.

2022.nov  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging

# infoView
import infoview.core.config as cfg

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < module data >------------------------------------------------------------------------------

# code defaults
DDCT_DEFAULTS = {# feeds: title (shown as the news source) and URL; optional per feed:
                 # "reloadInterval" (sec). The charset comes from the HTTP header or
                 # the XML declaration (e.g. ISO-8859-1 feeds work as is)
                 "feeds": [{"title": "New York Times",
                            "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"},
                           {"title": "UOL Mundo",
                            "url": "https://feeds.folha.uol.com.br/mundo/rss091.xml"},
                           {"title": "UOL Ciência",
                            "url": "https://feeds.folha.uol.com.br/ciencia/rss091.xml"}],
                 # show the description under the title by default (still rotating)
                 "showDescription": False,
                 # fetch each feed every (sec); a feed <ttl> may make it longer
                 "reloadInterval": 2 * 60,
                 # show each article for (sec)
                 "updateInterval": 10,
                 # max items in the ticker, the newest of all feeds (0: unlimited). 50 x
                 # updateInterval 10 s = one round in ~8 min: new items (on top) are shown
                 # soon; unlimited, 3 feeds of up to 100 items take ~36 min
                 "maxNewsItems": 50,
                 # drop items older than ignoreOlderThan (sec)
                 "ignoreOldItems": True,
                 "ignoreOlderThan": 7 * 24 * 60 * 60,
                 # remove these prefixes (startTags) / suffixes (endTags) from: "title" |
                 # "description" | "both" | "" (none), as in MagicMirror²
                 "removeStartTags": "",
                 "removeEndTags": "",
                 "startTags": [],
                 "endTags": [],
                 # drop items whose title contains any of these words (case insensitive)
                 "prohibitedWords": [],
                 # full article: scroll step (px) of the down / up buttons; 0 = one page
                 # (the visible text height minus one line, so no line is skipped)
                 "scrollLength": 0,
                 # description / full article untouched for this long (sec): back to the
                 # titles, rotation resumes (nobody may be reading anymore); 0 = never
                 "detailsTimeout": 120,
                 # log items that can't be parsed (no title or no date)
                 "logFeedWarnings": False,
}  # DDCT_DEFAULTS

# where start / end tags are removed
DLST_TAG_TARGETS = ["", "title", "description", "both"]

# shortest reload interval of a feed (sec)
DI_MIN_RELOAD = 60

# limits / accepted values (see cfg.merge)
DDCT_RULES = {"reloadInterval": {"min": DI_MIN_RELOAD},
              # the fade out takes ~2.5 s
              "updateInterval": {"min": 5},
              "maxNewsItems": {"min": 0},
              "ignoreOlderThan": {"min": 60},
              "removeStartTags": {"choices": DLST_TAG_TARGETS},
              "removeEndTags": {"choices": DLST_TAG_TARGETS},
              "startTags": {"items": str},
              "endTags": {"items": str},
              "prohibitedWords": {"items": str},
              "scrollLength": {"min": 0},
              "detailsTimeout": {"min": 0}}

# ---------------------------------------------------------------------------------------------
def _valid_feeds(flst_feeds: list) -> list:
    """
    keep only well formed feeds: a table with a "url" (text), optional "title" (text) and
    "reloadInterval" (integer, at least DI_MIN_RELOAD); the others are logged and dropped

    :param flst_feeds (list): feeds from the config

    :returns (list): valid feeds
    """
    llst = []

    for li_i, l_feed in enumerate(flst_feeds):
        # reload interval (optional)
        l_reload = l_feed.get("reloadInterval", DI_MIN_RELOAD) if isinstance(l_feed, dict) else None

        # well formed ?
        if isinstance(l_feed, dict) and isinstance(l_feed.get("url"), str) and l_feed["url"] and \
           isinstance(l_feed.get("title", ""), str) and \
           isinstance(l_reload, int) and not isinstance(l_reload, bool) and (l_reload >= DI_MIN_RELOAD):
            llst.append(l_feed)

        else:
            M_LOG.warning("config: newsfeed.feeds[%d] = %r ignored (expected {url = \"...\", title = \"...\"},"
                          " reloadInterval >= %d)", li_i, l_feed, DI_MIN_RELOAD)

    return llst

# effective configuration
DDCT_CONFIG = cfg.merge(DDCT_DEFAULTS, cfg.section("newsfeed"), "newsfeed", DDCT_RULES)
DDCT_CONFIG["feeds"] = _valid_feeds(DDCT_CONFIG["feeds"])

# < the end >----------------------------------------------------------------------------------
