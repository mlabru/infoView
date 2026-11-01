# -*- coding: utf-8 -*-
"""
infoView 1.0
View / utilities

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging

# pygame
import pygame as pg

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# smallest font size used when shrinking text to fit (px)
DI_MIN_FONT = 9

# fonts already created: (file, size) -> pg.font.Font
DDCT_FONTS = {}

# ---------------------------------------------------------------------------------------------
def font(fs_path: str, fi_size: int) -> pg.font.Font:
    """
    font of a size, cached (pg.font.Font is not cheap to create, sizes repeat)

    :param fs_path (str): font file
    :param fi_size (int): font size

    :returns (pg.font.Font): font
    """
    lt_key = (fs_path, int(fi_size))

    if lt_key not in DDCT_FONTS:
        DDCT_FONTS[lt_key] = pg.font.Font(fs_path, int(fi_size))

    return DDCT_FONTS[lt_key]

# ---------------------------------------------------------------------------------------------
def fit_size_by(fs_path: str, f_width, fi_max_w: int, fi_max_size: int, fi_min_size: int = DI_MIN_FONT) -> int:
    """
    biggest font size in [fi_min_size, fi_max_size] for which f_width(font) <= fi_max_w

    :param fs_path (str): font file
    :param f_width (callable): font -> width needed (e.g. widest of several lines)
    :param fi_max_w (int): available width (px)
    :param fi_max_size (int): preferred (max) size
    :param fi_min_size (int): min size (returned even if it doesn't fit)

    :returns (int): font size
    """
    # preferred size fits ? (the usual case)
    if f_width(font(fs_path, fi_max_size)) <= fi_max_w:
        return fi_max_size

    # binary search on the font size
    li_lo, li_hi = fi_min_size, fi_max_size

    while li_lo < li_hi:
        li_mid = (li_lo + li_hi + 1) // 2

        if f_width(font(fs_path, li_mid)) <= fi_max_w:
            li_lo = li_mid
        else:
            li_hi = li_mid - 1

    # return font size
    return li_lo

# ---------------------------------------------------------------------------------------------
def fit_size_all(fs_path: str, flst_texts: list, fi_max_w: int, fi_max_size: int, fi_min_size: int = DI_MIN_FONT) -> int:
    """
    one font size for several lines: the biggest in [fi_min_size, fi_max_size] for which every
    line fits fi_max_w (same size for all: uniform look)

    :returns (int): font size
    """
    return fit_size_by(fs_path, lambda f: max((f.size(t)[0] for t in flst_texts), default=0),
                       fi_max_w, fi_max_size, fi_min_size)

# ---------------------------------------------------------------------------------------------
def fit_size(fs_path: str, fs_sample: str, fi_max_w: int, fi_max_h: int,
             fi_min: int = 8, fi_max: int = 600) -> int:
    """
    biggest font size in [fi_min, fi_max] whose rendering of fs_sample fits fi_max_w x fi_max_h

    :param fs_path (str): font file
    :param fs_sample (str): widest text expected (e.g. "88:88")
    :param fi_max_w (int): available width (px)
    :param fi_max_h (int): available height (px)
    :param fi_min (int): min font size
    :param fi_max (int): max font size

    :returns (int): font size
    """
    # binary search on the font size
    li_lo, li_hi = fi_min, fi_max

    while li_lo < li_hi:
        li_mid = (li_lo + li_hi + 1) // 2

        # rendered size with this font size
        li_w, li_h = pg.font.Font(fs_path, li_mid).size(fs_sample)

        if (li_w <= fi_max_w) and (li_h <= fi_max_h):
            li_lo = li_mid
        else:
            li_hi = li_mid - 1

    # debug
    M_LOG.debug("fit_size %s %r in %dx%d: size %d", fs_path, fs_sample, fi_max_w, fi_max_h, li_lo)

    # return font size
    return li_lo

# ---------------------------------------------------------------------------------------------
def fit_text(f_font, fs_text: str, fi_max_w: int) -> str:
    """
    truncate text with an ellipsis so it fits a width

    :param f_font (pg.font.Font): font used to render the text
    :param fs_text (str): text
    :param fi_max_w (int): available width (px)

    :returns (str): text that fits
    """
    # already fits ?
    if f_font.size(fs_text)[0] <= fi_max_w:
        # nothing to do
        return fs_text

    # binary search for the longest prefix that fits with the ellipsis
    li_lo, li_hi = 0, len(fs_text)

    while li_lo < li_hi:
        li_mid = (li_lo + li_hi + 1) // 2

        if f_font.size(fs_text[:li_mid].rstrip() + "…")[0] <= fi_max_w:
            li_lo = li_mid
        else:
            li_hi = li_mid - 1

    # return truncated text
    return fs_text[:li_lo].rstrip() + "…"

# ---------------------------------------------------------------------------------------------
def fit_font(fs_path: str, fs_sample: str, fi_max_w: int, fi_max_h: int,
             fi_min: int = 8, fi_max: int = 600) -> pg.font.Font:
    """
    biggest font whose rendering of fs_sample fits fi_max_w x fi_max_h (see fit_size)

    :returns (pg.font.Font): font
    """
    # return font
    return pg.font.Font(fs_path, fit_size(fs_path, fs_sample, fi_max_w, fi_max_h, fi_min, fi_max))

# < the end >----------------------------------------------------------------------------------
