"""Lectura de una hoja de Google Sheets con la API v4 y una clave de API.

Requisitos (ver GUIA_GOOGLE_SHEETS.md):
  · API de Google Sheets habilitada en un proyecto de Google Cloud + clave de API.
  · Hoja compartida como «Cualquier persona con el enlace → Lector».
La clave se usa SOLO en el servidor: el navegador nunca la ve.
"""
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

import config

log = logging.getLogger(__name__)
API = "https://sheets.googleapis.com/v4/spreadsheets"


class HojaError(Exception):
    """Error al leer la hoja. El mensaje está escrito para mostrarse tal cual al administrador."""


def id_hoja(valor):
    """Acepta el ID o la URL completa de la hoja y devuelve el ID."""
    m = re.search(r"/d/([A-Za-z0-9_-]+)", valor or "")
    return m.group(1) if m else (valor or "").strip()


def configurada():
    return bool(id_hoja(config.GOOGLE_SHEET_ID) and config.GOOGLE_API_KEY.strip())


def _mensaje(codigo, error):
    """Traduce el error de Google a una causa y una solución (sin datos internos como el nº de proyecto)."""
    msg = (error.get("message") or "").lower()
    if codigo == 400 and "api key" in msg:
        return "La clave de API no es válida. Revise GOOGLE_API_KEY."
    if codigo == 400 and "unable to parse range" in msg:
        return "No se encontró la pestaña indicada. Revise GOOGLE_SHEET_PESTANA (debe coincidir con el nombre exacto)."
    if codigo == 403 and ("has not been used" in msg or "disabled" in msg):
        return "La API de Google Sheets no está habilitada en su proyecto de Google Cloud."
    if codigo == 403 and ("referer" in msg or "ip address" in msg or "blocked" in msg):
        return "La clave de API tiene restricciones de aplicación que bloquean a este servidor."
    if codigo == 403:
        return "La hoja no es pública. Compártala como «Cualquier persona con el enlace → Lector»."
    if codigo == 404:
        return "No se encontró la hoja. Revise GOOGLE_SHEET_ID."
    if codigo == 429:
        return "Se superó la cuota de Google Sheets; se reintentará en unos segundos."
    return f"Google respondió con un error ({codigo})."


def _http_get_json(url):
    """GET a Google. Nunca se registra la URL porque contiene la clave."""
    req = urllib.request.Request(url, headers={"User-Agent": "portal-mapa-conjunto/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=config.SHEETS_TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            error = json.loads(e.read().decode("utf-8", "replace")).get("error", {})
        except Exception:
            error = {}
        log.warning("Google Sheets respondió %s: %s", e.code, error.get("message", ""))
        raise HojaError(_mensaje(e.code, error)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HojaError("No hay conexión con Google (red caída o tiempo de espera agotado).") from None
    except json.JSONDecodeError:
        raise HojaError("Google devolvió una respuesta inesperada.") from None


def leer_filas():
    """Devuelve la hoja como lista de filas; la primera es el encabezado. Las filas pueden venir más cortas."""
    pestana = config.GOOGLE_SHEET_PESTANA.strip().replace("'", "''")
    rango = f"'{pestana}'!A:Z" if pestana else "A:Z"                 # sin nombre = primera pestaña
    params = urllib.parse.urlencode({"key": config.GOOGLE_API_KEY.strip(), "majorDimension": "ROWS",
                                     "valueRenderOption": "UNFORMATTED_VALUE"})   # números sin formato regional
    url = f"{API}/{urllib.parse.quote(id_hoja(config.GOOGLE_SHEET_ID), safe='')}/values/{urllib.parse.quote(rango, safe='')}?{params}"
    values = _http_get_json(url).get("values") or []
    if not values:
        raise HojaError("La hoja está vacía: agregue la fila de encabezados y los datos.")
    return values
