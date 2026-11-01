# -*- coding: utf-8 -*-
"""
infoView 1.0
i18n: user-visible texts and date format per language

language: DS_LANGUAGE in infoview/core/settings.py ("pt_BR" by default, or the IVW_LANGUAGE environment
variable). Codes are normalized ("pt-BR", "pt_br" -> "pt_BR"; "pt" -> "pt_BR";
"en_US" -> "en"); an unknown language falls back to the default ("pt_BR"); a text missing in a
translation falls back to English, then to its key.

Day and month names live here (no locale.setlocale: it's process wide and needs the system
locale installed, which a Raspberry Pi image often doesn't have).

2026.oct  mlabru  initial release (Linux/Python)
"""
# < imports >----------------------------------------------------------------------------------

# python library
import logging

# infoView
import infoview.core.settings as df

# < logging >----------------------------------------------------------------------------------

M_LOG = logging.getLogger(__name__)
M_LOG.setLevel(logging.WARNING)

# < texts >------------------------------------------------------------------------------------

# language of the texts missing in a translation
DS_FALLBACK = "en"

# language used when the configured one is unknown (the default of settings.DS_LANGUAGE)
DS_DEFAULT = "pt_BR"

# language base code -> supported language (e.g. "pt" -> "pt_BR")
DDCT_BASE = {"pt": "pt_BR", "en": "en"}

# texts per language. Plurals: (singular, plural), chosen by tr_n()
DDCT_TEXTS = {
    "en": {
        # clock
        "date": "{weekday}, {month} {day}, {year}",
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"],
        # clock
        "clock.unsynced": "setting the clock…",
        # newsfeed
        "nf.waiting": "waiting for articles",
        "nf.no_feeds": "no feeds configured",
        "nf.all_filtered": "no recent news",
        "nf.unavailable": "news unavailable ({reason})",
        "nf.no_connection": "no connection",
        "nf.unauthorized": "access denied",
        "nf.bad_url": "invalid feed address",
        "nf.feed_error": "feed error",
        "nf.source": "Newsfeed",
        "nf.just_now": "just now",
        "nf.minutes_ago": ("{n} minute ago", "{n} minutes ago"),
        "nf.hours_ago": ("{n} hour ago", "{n} hours ago"),
        "nf.days_ago": ("{n} day ago", "{n} days ago"),
        # weather
        "wt.waiting": "waiting for weather",
        "wt.unavailable": "weather unavailable ({reason})",
        "wt.no_connection": "no connection",
        "wt.not_found": "place not found: {place}",
        "wt.http_error": "HTTP error {code}",
        "wt.bad_response": "invalid response",
        "wt.old": "data {n} min old",
        "wt.feels_inline": "feels {value}",
        "wt.wind_inline": "Wind {value}",
        "wt.gusts_inline": "gusts {value}",
        "wt.rain_inline": "Rain today {value}",
        "wt.humidity_inline": "humidity {value}",
        "wt.feels": "Feels like",
        "wt.wind": "Wind",
        "wt.gusts": "Gusts",
        "wt.rain": "Rain today",
        "wt.rain_prob": "Chance of rain",
        "wt.humidity": "Humidity",
        "wt.compass": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
        # WMO weather codes
        "wmo.0": "Clear sky", "wmo.1": "Mainly clear", "wmo.2": "Partly cloudy", "wmo.3": "Overcast",
        "wmo.45": "Fog", "wmo.48": "Rime fog",
        "wmo.51": "Light drizzle", "wmo.53": "Drizzle", "wmo.55": "Dense drizzle",
        "wmo.56": "Freezing drizzle", "wmo.57": "Freezing drizzle",
        "wmo.61": "Light rain", "wmo.63": "Rain", "wmo.65": "Heavy rain",
        "wmo.66": "Freezing rain", "wmo.67": "Freezing rain",
        "wmo.71": "Light snow", "wmo.73": "Snow", "wmo.75": "Heavy snow", "wmo.77": "Snow grains",
        "wmo.80": "Rain showers", "wmo.81": "Rain showers", "wmo.82": "Violent showers",
        "wmo.85": "Snow showers", "wmo.86": "Snow showers",
        "wmo.95": "Thunderstorm", "wmo.96": "Thunderstorm, hail", "wmo.99": "Thunderstorm, hail",
        "wmo.unknown": "—",
    },
    "pt_BR": {
        # clock
        "date": "{weekday}, {day} de {month} de {year}",
        "weekdays": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
                     "sábado", "domingo"],
        "months": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                   "setembro", "outubro", "novembro", "dezembro"],
        # clock
        "clock.unsynced": "acertando o relógio…",
        # newsfeed
        "nf.waiting": "aguardando notícias",
        "nf.no_feeds": "nenhum feed configurado",
        "nf.all_filtered": "nenhuma notícia recente",
        "nf.unavailable": "notícias indisponíveis ({reason})",
        "nf.no_connection": "sem conexão",
        "nf.unauthorized": "acesso negado",
        "nf.bad_url": "endereço de feed inválido",
        "nf.feed_error": "erro no feed",
        "nf.source": "Notícias",
        "nf.just_now": "agora mesmo",
        "nf.minutes_ago": ("há {n} minuto", "há {n} minutos"),
        "nf.hours_ago": ("há {n} hora", "há {n} horas"),
        "nf.days_ago": ("há {n} dia", "há {n} dias"),
        # weather
        "wt.waiting": "aguardando dados do tempo",
        "wt.unavailable": "tempo indisponível ({reason})",
        "wt.no_connection": "sem conexão",
        "wt.not_found": "local não encontrado: {place}",
        "wt.http_error": "erro HTTP {code}",
        "wt.bad_response": "resposta inválida",
        "wt.old": "atualizado há {n} min",
        "wt.feels_inline": "sensação {value}",
        "wt.wind_inline": "Vento {value}",
        "wt.gusts_inline": "rajadas {value}",
        "wt.rain_inline": "Chuva hoje {value}",
        "wt.humidity_inline": "umidade {value}",
        "wt.feels": "Sensação",
        "wt.wind": "Vento",
        "wt.gusts": "Rajadas",
        "wt.rain": "Chuva hoje",
        "wt.rain_prob": "Chance de chuva",
        "wt.humidity": "Umidade",
        "wt.compass": ["N", "NE", "L", "SE", "S", "SO", "O", "NO"],
        # WMO weather codes
        "wmo.0": "Céu limpo", "wmo.1": "Poucas nuvens", "wmo.2": "Parcialmente nublado",
        "wmo.3": "Nublado",
        "wmo.45": "Nevoeiro", "wmo.48": "Nevoeiro com geada",
        "wmo.51": "Garoa fraca", "wmo.53": "Garoa", "wmo.55": "Garoa forte",
        "wmo.56": "Garoa congelante", "wmo.57": "Garoa congelante",
        "wmo.61": "Chuva fraca", "wmo.63": "Chuva", "wmo.65": "Chuva forte",
        "wmo.66": "Chuva congelante", "wmo.67": "Chuva congelante",
        "wmo.71": "Neve fraca", "wmo.73": "Neve", "wmo.75": "Neve forte", "wmo.77": "Grãos de neve",
        "wmo.80": "Pancadas de chuva", "wmo.81": "Pancadas de chuva", "wmo.82": "Pancadas fortes",
        "wmo.85": "Pancadas de neve", "wmo.86": "Pancadas de neve",
        "wmo.95": "Trovoada", "wmo.96": "Trovoada com granizo", "wmo.99": "Trovoada com granizo",
        "wmo.unknown": "—",
    },
}

# ---------------------------------------------------------------------------------------------
def normalize(fs_lang: str) -> str:
    """
    language code -> supported language ("pt-BR" / "pt_br" / "pt" -> "pt_BR"; unknown -> DS_DEFAULT)

    :param fs_lang (str): language code

    :returns (str): supported language
    """
    # "pt-br" -> "pt_br"
    ls_lang = (fs_lang or "").strip().replace("-", "_")

    # exact (case insensitive) ?
    for ls_key in DDCT_TEXTS:
        if ls_key.lower() == ls_lang.lower():
            return ls_key

    # base language ("pt_PT" -> "pt" -> "pt_BR") ?
    ls_base = DDCT_BASE.get(ls_lang.split("_")[0].lower(), None)

    if ls_base:
        return ls_base

    # unknown: the default language, like the other invalid settings
    M_LOG.error("unsupported language %r, using %r", fs_lang, DS_DEFAULT)
    return DS_DEFAULT

# current language (settings.DS_LANGUAGE: default "pt_BR", or IVW_LANGUAGE), normalized
DS_LANGUAGE = normalize(df.DS_LANGUAGE)

# ---------------------------------------------------------------------------------------------
def _text(fs_key: str):
    """
    raw text for the current language (fallback: English, then the key itself)
    """
    return DDCT_TEXTS[DS_LANGUAGE].get(fs_key, DDCT_TEXTS[DS_FALLBACK].get(fs_key, fs_key))

# ---------------------------------------------------------------------------------------------
def tr(fs_key: str, **kwargs) -> str:
    """
    translated text, formatted with kwargs

    :param fs_key (str): text key (e.g. "wt.waiting")

    :returns (str): text
    """
    return _text(fs_key).format(**kwargs) if kwargs else _text(fs_key)

# ---------------------------------------------------------------------------------------------
def tr_n(fs_key: str, fi_n: int, **kwargs) -> str:
    """
    translated text with singular / plural by fi_n (also available as {n})

    :param fs_key (str): text key (value: (singular, plural))
    :param fi_n (int): count

    :returns (str): text
    """
    lt_forms = _text(fs_key)

    return lt_forms[0 if 1 == fi_n else 1].format(n=fi_n, **kwargs)

# ---------------------------------------------------------------------------------------------
def tr_list(fs_key: str) -> list:
    """
    translated list (e.g. weekdays, months, compass points)
    """
    return _text(fs_key)

# ---------------------------------------------------------------------------------------------
def format_date(fdt) -> str:
    """
    full date for the current language, first letter capitalized
    ("Saturday, October 31, 2026" / "Sábado, 31 de outubro de 2026")

    :param fdt (datetime.date): date

    :returns (str): date text
    """
    ls_date = tr("date", weekday=tr_list("weekdays")[fdt.weekday()], month=tr_list("months")[fdt.month - 1],
                 day=fdt.day, year=fdt.year)

    return ls_date[:1].upper() + ls_date[1:]

# ---------------------------------------------------------------------------------------------
def date_samples(fi_year: int = 2026) -> list:
    """
    candidate longest dates (every weekday with every month, two-digit day), to fit a font

    :returns (list): date texts
    """
    llst = [tr("date", weekday=ls_wd, month=ls_mo, day=28, year=fi_year)
            for ls_wd in tr_list("weekdays") for ls_mo in tr_list("months")]

    # same capitalization as format_date
    return [ls[:1].upper() + ls[1:] for ls in llst]

# < the end >----------------------------------------------------------------------------------
