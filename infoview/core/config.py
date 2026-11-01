# -*- coding: utf-8 -*-
"""
infoView 1.0
infoview.core.config: user configuration file

The user's settings live OUTSIDE the code, in a TOML file that is not versioned:

    1. the file named by the IVW_CONFIG environment variable, if set;
    2. otherwise <project root>/infoView.toml (git-ignored; start from infoView.example.toml).

A missing file is fine (code defaults are used). Precedence, lowest to highest:

    code defaults  <  config file  <  IVW_* environment variables (general settings only)

Sections: [general] (core/settings.py), [weather] (modules/weather/config.py), [newsfeed]
(modules/newsfeed/config.py). merge() validates the file against the code defaults: unknown keys
(typos) and values of the wrong type are logged and ignored - never silently used. Optional rules
per key (minimum / maximum, accepted values, type of the list items) catch values of the right
type that make no sense (e.g. a negative interval); the default is used instead.

TOML parser: tomllib (Python >= 3.11), else tomli (pip install tomli); without either the file
is ignored, with an error in the log.

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import copy
import logging
import os

# TOML parser
try:
    import tomllib as toml

except ModuleNotFoundError:
    try:
        import tomli as toml

    except ModuleNotFoundError:
        toml = None

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# project root (this file is <root>/infoview/core/config.py)
DS_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# configuration file: IVW_CONFIG, or <root>/infoView.toml
DS_CONFIG_FILE = os.environ.get("IVW_CONFIG", "") or os.path.join(DS_ROOT_DIR, "infoView.toml")

# ---------------------------------------------------------------------------------------------
def load(fs_path: str) -> dict:
    """
    read a TOML configuration file

    :param fs_path (str): file path

    :returns (dict): its contents, {} if the file doesn't exist or can't be read (error logged)
    """
    # no file: code defaults
    if not os.path.isfile(fs_path):
        # an explicitly named file must exist
        if os.environ.get("IVW_CONFIG", ""):
            M_LOG.error("config file %s (IVW_CONFIG) not found: using defaults", fs_path)

        return {}

    # no parser ?
    if toml is None:
        M_LOG.error("config file %s ignored: needs Python >= 3.11 (tomllib) or 'pip install tomli'", fs_path)
        return {}

    try:
        # parse
        with open(fs_path, "rb") as l_fp:
            ldct = toml.load(l_fp)

    # on error...
    except (OSError, toml.TOMLDecodeError) as l_err:
        M_LOG.error("config file %s ignored: %s", fs_path, l_err)
        return {}

    # logger
    M_LOG.warning("config file: %s", fs_path)

    # contents
    return ldct

# ---------------------------------------------------------------------------------------------
def merge(fdct_defaults: dict, fdct_user: dict, fs_where: str, fdct_rules: dict = None) -> dict:
    """
    defaults overridden by the user's values, validated against the defaults: a key that is not
    in the defaults, or a value whose type differs from the default's, is logged and ignored.
    Nested tables are merged key by key; lists replace the default list.

    Type rules: int is accepted where the default is float; a default of None (weather
    latitude / longitude: "not set") accepts a number.

    Value rules (fdct_rules, optional): {key: {"min": n, "max": n, "choices": [...], "items": type}};
    for a nested table, {key: {subkey: {...}}}. A list item of another type than "items" is
    dropped (the rest of the list is kept); a value out of [min, max] or not in choices is
    logged and the default is kept.

    :param fdct_defaults (dict): code defaults (not modified)
    :param fdct_user (dict): values from the config file section
    :param fs_where (str): section name, for the log messages (e.g. "weather")
    :param fdct_rules (dict): value rules per key (see above)

    :returns (dict): new dict with the effective values
    """
    # no rules
    fdct_rules = fdct_rules or {}

    # start from a copy of the defaults
    ldct = copy.deepcopy(fdct_defaults)

    # for all user values...
    for ls_key, l_val in fdct_user.items():
        # where, for the messages
        ls_name = f"{fs_where}.{ls_key}"

        # unknown key (typo, or a setting that doesn't exist) ?
        if ls_key not in ldct:
            M_LOG.warning("config: unknown key %s ignored (valid: %s)", ls_name, ", ".join(sorted(ldct)))
            continue

        # default value and rules
        l_def = ldct[ls_key]
        ldct_rule = fdct_rules.get(ls_key, {})

        # nested table ?
        if isinstance(l_def, dict):
            if isinstance(l_val, dict):
                ldct[ls_key] = merge(l_def, l_val, ls_name, ldct_rule)
            else:
                M_LOG.warning("config: %s must be a table, ignored", ls_name)
            continue

        # same type as the default ?
        if not _type_ok(l_def, l_val):
            M_LOG.warning("config: %s = %r has the wrong type (expected %s), ignored",
                          ls_name, l_val, type(l_def).__name__)
            continue

        # list: only items of the expected type
        if isinstance(l_val, list) and ("items" in ldct_rule):
            l_val = _valid_items(l_val, ldct_rule["items"], ls_name)

        # value out of the rules ?
        ls_why = _rule_error(l_val, ldct_rule)

        if ls_why:
            M_LOG.warning("config: %s = %r ignored (%s), using %r", ls_name, l_val, ls_why, l_def)
            continue

        # ok
        ldct[ls_key] = copy.deepcopy(l_val)

    # effective values
    return ldct

# ---------------------------------------------------------------------------------------------
def _type_ok(f_default, f_value) -> bool:
    """
    value acceptable where the default is f_default ? (see merge)
    """
    # bool is a subclass of int: check it first, and exactly
    if isinstance(f_default, bool) or isinstance(f_value, bool):
        return isinstance(f_default, bool) and isinstance(f_value, bool)

    # no default value (None: "not set", e.g. latitude): a number
    if f_default is None:
        return isinstance(f_value, (int, float))

    # int where a float is expected
    if isinstance(f_default, float):
        return isinstance(f_value, (int, float))

    # same type
    return isinstance(f_value, type(f_default))

# ---------------------------------------------------------------------------------------------
def _valid_items(flst_val: list, f_type: type, fs_name: str) -> list:
    """
    list items of type f_type (the others are logged and dropped)
    """
    llst = []

    for li_i, l_item in enumerate(flst_val):
        # expected type (bool is not an int) ?
        if isinstance(l_item, f_type) and (f_type is bool or not isinstance(l_item, bool)):
            llst.append(l_item)

        else:
            M_LOG.warning("config: %s[%d] = %r ignored (expected %s)", fs_name, li_i, l_item, f_type.__name__)

    return llst

# ---------------------------------------------------------------------------------------------
def _rule_error(f_val, fdct_rule: dict) -> str:
    """
    value against its rules (see merge)

    :returns (str): why the value is not accepted, "" if it is
    """
    # accepted values ?
    if ("choices" in fdct_rule) and (f_val not in fdct_rule["choices"]):
        return "expected one of " + ", ".join(repr(l_c) for l_c in fdct_rule["choices"])

    # limits
    if ("min" in fdct_rule) and (f_val < fdct_rule["min"]):
        return f"minimum {fdct_rule['min']}"

    if ("max" in fdct_rule) and (f_val > fdct_rule["max"]):
        return f"maximum {fdct_rule['max']}"

    # ok
    return ""

# ---------------------------------------------------------------------------------------------
def section(fs_name: str) -> dict:
    """
    one section of the configuration file ({} if absent or not a table)

    :param fs_name (str): "general", "weather" or "newsfeed"

    :returns (dict): section values
    """
    l_sec = DDCT_USER.get(fs_name, {})

    # not a table ?
    if not isinstance(l_sec, dict):
        M_LOG.warning("config: [%s] must be a table, ignored", fs_name)
        return {}

    return l_sec

# < module data >------------------------------------------------------------------------------

# the configuration file, read once at import
DDCT_USER = load(DS_CONFIG_FILE)

# unknown sections (typos)
for _ls_sec in sorted(set(DDCT_USER) - {"general", "weather", "newsfeed"}):
    M_LOG.warning("config: unknown section [%s] ignored (valid: general, weather, newsfeed)", _ls_sec)

# < the end >----------------------------------------------------------------------------------
