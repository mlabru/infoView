# -*- coding: utf-8 -*-
"""
infoView 1.0
HTTP helper shared by the fetchers (newsfeed, weather)

urllib with a network timeout and the same error classification for every fetcher.

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging
import urllib.error
import urllib.request

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < constants >--------------------------------------------------------------------------------

# default User-Agent
DS_USER_AGENT = "infoView/1.0 (+ambient information display)"

# max response size (bytes): a feed or a forecast is far smaller; a bigger answer (wrong URL,
# broken server) must not fill the Raspberry Pi's memory
DI_MAX_BYTES = 5 * 1024 * 1024

# after a failed fetch, try again after this time (sec), doubling on each new failure, never
# later than the normal interval: at boot the network (Wi-Fi) is often not up yet
DI_RETRY_FIRST = 30

# ---------------------------------------------------------------------------------------------
def retry_delay(fi_failures: int, ff_interval: float) -> float:
    """
    time until the next fetch of a polling loop

    :param fi_failures (int): consecutive failed fetches (0: the last one worked)
    :param ff_interval (float): normal interval (sec)

    :returns (float): ff_interval after a success; DI_RETRY_FIRST, 2x, 4x, ... (at most
                      ff_interval) after 1, 2, 3, ... failures
    """
    # last one worked ?
    if fi_failures < 1:
        return ff_interval

    # exponent limited (the interval caps it long before)
    return min(DI_RETRY_FIRST * 2 ** min(fi_failures - 1, 16), ff_interval)

# ---------------------------------------------------------------------------------------------
def http_get(fs_url: str, ff_timeout: float, fdct_headers: dict = None):
    """
    download a URL (exceptions are not caught: see error_info)

    :param fs_url (str): URL
    :param ff_timeout (float): network timeout (sec)
    :param fdct_headers (dict): extra request headers

    :returns (tuple): (contents (bytes), or None if not modified: HTTP 304, only after a
                      conditional request with If-None-Match / If-Modified-Since;
                      headers that matter (dict, see _headers))

    :raises ValueError: response bigger than DI_MAX_BYTES (other errors: see error_info)
    """
    # logger
    M_LOG.info(">> http_get: %s", fs_url)

    # request (default User-Agent, overridable)
    l_request = urllib.request.Request(fs_url, headers={"User-Agent": DS_USER_AGENT, **(fdct_headers or {})})

    try:
        # download
        with urllib.request.urlopen(l_request, timeout=ff_timeout) as l_resp:
            # contents, at most DI_MAX_BYTES (one more byte tells it's bigger)
            lby_data = l_resp.read(DI_MAX_BYTES + 1)

            if len(lby_data) > DI_MAX_BYTES:
                raise ValueError(f"response bigger than {DI_MAX_BYTES} bytes: {fs_url}")

            # contents + headers
            return lby_data, _headers(l_resp)

    # HTTP error: it holds the open response, close it before passing the error on (otherwise
    # each failed fetch leaks a connection until the garbage collector finds it)
    except urllib.error.HTTPError as l_err:
        l_err.close()

        # not modified (conditional request): not an error, nothing downloaded
        if 304 == l_err.code:
            return None, _headers(l_err)

        raise

# ---------------------------------------------------------------------------------------------
def _headers(f_resp) -> dict:
    """
    response headers that matter: to the parsers (charset, base URL) and to the next conditional
    request (cache validators)

    :param f_resp: response (or HTTPError)

    :returns (dict): content-type, content-location (final URL), etag, last-modified ("" if absent)
    """
    return {"content-type": f_resp.headers.get("Content-Type", ""),
            "content-location": f_resp.geturl(),
            "etag": f_resp.headers.get("ETag", ""),
            "last-modified": f_resp.headers.get("Last-Modified", "")}

# ---------------------------------------------------------------------------------------------
def error_info(f_err: Exception) -> dict:
    """
    classify a download / parse error

    :param f_err (Exception): error

    :returns (dict): {"code", "message"}: HTTPError -> HTTP status (401: "Unauthorized");
                     other OSError (DNS, no connection, timeout) -> "URLError"; else type name
    """
    # HTTP error ?
    if isinstance(f_err, urllib.error.HTTPError):
        return {"code": str(f_err.code), "message": "Unauthorized" if 401 == f_err.code else f"HTTP {f_err.code}"}

    # network error ?
    if isinstance(f_err, OSError):
        return {"code": "URLError", "message": str(f_err)}

    # anything else
    return {"code": type(f_err).__name__, "message": str(f_err)}

# < the end >----------------------------------------------------------------------------------
