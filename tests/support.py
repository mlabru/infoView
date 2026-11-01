# -*- coding: utf-8 -*-
"""
infoView tests: shared helpers

- LocalServer: HTTP server on 127.0.0.1 (random port) answering fixed routes, in a thread;
- MuteServer: accepts connections and never answers (network timeout tests);
- closed_port_url(): URL of a local port nobody listens on (connection refused);
- RSS / Open-Meteo sample payloads.

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import http.server
import json
import socket
import threading

# < LocalServer >------------------------------------------------------------------------------

class LocalServer:
    """
    HTTP server with fixed routes: {"/path": (status, content_type, body_bytes[, etag])}; any
    other path gets 404. The path is matched without the query string. A route with an etag
    sends it and answers 304 (no body) to a request with that If-None-Match. Requests are
    counted per path (.dct_hits); their User-Agent headers are kept (.lst_agents). Use as a
    context manager.
    """
    # -----------------------------------------------------------------------------------------
    def __init__(self, fdct_routes: dict):
        """
        :param fdct_routes (dict): path -> (status, content type, body)
        """
        # routes
        ldct_routes = fdct_routes

        # requests per path
        self.dct_hits = ldct_hits = {}
        # User-Agent of each request
        self.lst_agents = llst_agents = []

        # request handler
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                ls_path = self.path.split("?")[0]
                ldct_hits[ls_path] = ldct_hits.get(ls_path, 0) + 1
                llst_agents.append(self.headers.get("User-Agent", ""))
                lt_route = ldct_routes.get(ls_path)

                if lt_route is None:
                    self.send_error(404)
                    return

                li_status, ls_type, lby_body = lt_route[:3]
                ls_etag = lt_route[3] if len(lt_route) > 3 else ""

                # unchanged since the client's copy ?
                if ls_etag and (self.headers.get("If-None-Match") == ls_etag):
                    self.send_response(304)
                    self.send_header("ETag", ls_etag)
                    self.end_headers()
                    return

                self.send_response(li_status)
                self.send_header("Content-Type", ls_type)
                self.send_header("Content-Length", str(len(lby_body)))
                if ls_etag:
                    self.send_header("ETag", ls_etag)
                self.end_headers()
                self.wfile.write(lby_body)

            def log_message(self, *args):
                pass

        # server (random free port)
        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thr = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self):
        self._thr.start()
        return self

    def __exit__(self, *args):
        self._srv.shutdown()
        self._srv.server_close()

    def url(self, fs_path: str) -> str:
        """full URL of a path on this server"""
        return f"http://127.0.0.1:{self._srv.server_port}{fs_path}"

# < MuteServer >-------------------------------------------------------------------------------

class MuteServer:
    """
    accepts TCP connections and never answers (the client must time out). Context manager.
    """
    def __enter__(self):
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._conns = []
        threading.Thread(target=self._accept, daemon=True).start()
        return self

    def _accept(self):
        try:
            while True:
                self._conns.append(self._sock.accept()[0])
        except OSError:
            pass

    def __exit__(self, *args):
        for l_conn in self._conns:
            l_conn.close()
        self._sock.close()

    def url(self, fs_path: str = "/") -> str:
        """URL that will never answer"""
        return f"http://127.0.0.1:{self._sock.getsockname()[1]}{fs_path}"

# ---------------------------------------------------------------------------------------------
def closed_port_url(fs_path: str = "/") -> str:
    """
    URL of a local port nobody listens on (connection refused -> URLError)
    """
    with socket.socket() as l_sock:
        l_sock.bind(("127.0.0.1", 0))
        li_port = l_sock.getsockname()[1]

    return f"http://127.0.0.1:{li_port}{fs_path}"

# < sample payloads >--------------------------------------------------------------------------

# RSS in ISO-8859-1 with a <ttl> of 10 minutes; one item without a date (must be dropped)
DBY_RSS = """<?xml version="1.0" encoding="ISO-8859-1"?>
<rss version="2.0"><channel><title>Teste</title><ttl>10</ttl>
<item><title>Notícia &amp; acentuação</title><description>&lt;p&gt;Olá &lt;b&gt;mundo&lt;/b&gt;&lt;/p&gt;</description>
<pubDate>Fri, 30 Oct 2026 23:00:00 -0300</pubDate><link>http://x/1</link></item>
<item><title>Segunda</title><description>texto</description>
<pubDate>30 Oct 2026 22:00:00 -0300</pubDate><link>http://x/2</link></item>
<item><title>Sem data</title><description>descartada</description></item>
</channel></rss>""".encode("iso-8859-1")

# Open-Meteo geocoding answer
DBY_GEOCODING = json.dumps({"results": [{"name": "Cidade Teste", "admin1": "Estado Teste",
                                         "latitude": -22.5, "longitude": -45.5}]}).encode()

# Open-Meteo forecast answer (the fields infoview/modules/weather/fetcher.py requests)
DBY_FORECAST = json.dumps({
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h", "precipitation": "mm"},
    "current": {"time": "2026-10-31T12:00", "temperature_2m": 23.4, "apparent_temperature": 25.1,
                "relative_humidity_2m": 70, "precipitation": 0.2, "weather_code": 2,
                "wind_speed_10m": 12.3, "wind_direction_10m": 45, "wind_gusts_10m": 20.0, "is_day": 1},
    "daily": {"temperature_2m_max": [27.0], "temperature_2m_min": [15.0],
              "precipitation_sum": [2.2], "precipitation_probability_max": [40]}}).encode()

# < the end >----------------------------------------------------------------------------------
