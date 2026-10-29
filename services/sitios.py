"""Sitios de interés.

Fuente principal: hoja de Google Sheets (services/hoja.py). Si no está configurada se usa el
Excel local data/sitios.xlsx. Todo pasa por el MISMO proceso de validación:

  hoja de cálculo → filas → entender encabezados → coordenadas → moderación → zona válida → sitio

Para que la hoja pueda llenarla el público, aquí se valida todo: coordenadas, distancia máxima al
conjunto, largo de los textos y enlaces. Nada se muestra «tal cual» en la página.
"""
import hashlib
import json
import logging
import math
import re
import threading
import time
import unicodedata

import config
from services import hoja, rutas

log = logging.getLogger(__name__)

# Encabezados que se reconocen. Los formularios de Google usan la pregunta como encabezado
# («Nombre del sitio», «Categoría», «Coordenadas (clic derecho en Google Maps…)»), por eso
# se acepta coincidencia exacta y, para palabras de 5+ letras, que el encabezado las contenga.
ALIAS = {
    "nombre": ["nombre", "name"],
    "categoria": ["categoria", "category", "tipo de sitio", "tipo de lugar", "tipo"],
    "latitud": ["latitud", "lat", "latitude"],
    "longitud": ["longitud", "lon", "lng", "long", "longitude"],
    "coordenadas": ["coordenadas", "coordenada", "coordinates", "google maps"],
    "direccion": ["direccion", "address"],
    "descripcion": ["descripcion", "description", "comentario", "detalle"],
    "horario": ["horario", "horarios", "hours"],
    "telefono": ["telefono", "celular", "phone", "tel"],
    "web": ["web", "sitio web", "pagina web", "website", "url", "pagina"],
    "aprobado": ["aprobado", "aprobada", "aprobar", "publicar", "visible"],
}
SI = {"si", "s", "x", "ok", "1", "true", "verdadero", "aprobado", "aprobada", "publicar", "yes"}
NO = {"no", "n", "0", "false", "falso", "oculto", "ocultar", "rechazado", "rechazada"}
LARGOS = {"nombre": 120, "categoria": 40, "direccion": 160, "descripcion": 600, "horario": 120, "telefono": 40, "web": 300}

_ahora = time.monotonic          # separado para poder controlar el tiempo en las pruebas
_lock = threading.Lock()
_estado = {"t": None, "values": None, "datos": [], "stats": {}, "fuente": "", "error": "", "actualizado": None, "clave_xlsx": None}


# ------------------------------- utilidades --------------------------------- #
def _norm(s):
    t = unicodedata.normalize("NFD", str(s).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _texto(v, defecto=""):
    """Celda → texto limpio. Maneja vacíos, números enteros (3001234567.0) y caracteres de control."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return defecto
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(v)).strip()
    return t or defecto


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def _coordenadas(texto):
    """Extrae (lat, lon) de lo que la gente pega: «4.6483, -74.1429», «4,6483, -74,1429» o un enlace largo de Google Maps."""
    t = _texto(texto)
    if not t:
        return None
    if "http" in t.lower():
        for patron in (r"@(-?\d+\.\d+),(-?\d+\.\d+)", r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
                       r"[?&](?:q|query|ll)=(-?\d+\.\d+)(?:,|%2C)(-?\d+\.\d+)"):
            m = re.search(patron, t)
            if m:
                return float(m.group(1)), float(m.group(2))
        return None
    numeros = re.findall(r"-?\d+(?:[.,]\d+)?", t)
    if len(numeros) == 2:
        return float(numeros[0].replace(",", ".")), float(numeros[1].replace(",", "."))
    return None


def _url(v):
    """Solo enlaces http(s); evita javascript: y similares."""
    s = _texto(v)
    if re.match(r"^https?://", s, re.I):
        return s
    return "https://" + s if s and "." in s and " " not in s and ":" not in s else ""


def _mapear(encabezados):
    """{campo: posición de la columna}. Primero coincidencia exacta y luego parcial; una columna no se usa dos veces."""
    heads = [_norm(h) for h in encabezados]
    asignado, usadas = {}, set()
    for exacta in (True, False):
        for campo, alias in ALIAS.items():
            if campo in asignado:
                continue
            for i, h in enumerate(heads):
                if i in usadas:
                    continue
                if (h in alias) if exacta else any(len(a) >= 5 and a in h for a in alias):
                    asignado[campo] = i
                    usadas.add(i)
                    break
    return asignado


# ------------------------------- validación --------------------------------- #
def procesar(values, desde_hoja):
    """Convierte las filas de la hoja en sitios válidos. Devuelve (sitios, estadísticas)."""
    stats = {"leidas": 0, "publicadas": 0, "ocultas": 0, "sin_coordenadas": 0, "fuera_de_zona": 0}
    if not values:
        return [], stats
    col = _mapear(values[0])
    clat, clon = config.CONJUNTO_CENTRO
    canon, sitios = {}, []

    for n, fila in enumerate(values[1:], start=2):                      # n = número de fila en la hoja (id estable)
        def g(campo):
            i = col.get(campo)
            return fila[i] if i is not None and i < len(fila) else None

        if not any(_texto(c) for c in fila):
            continue
        stats["leidas"] += 1

        if desde_hoja:                                                  # moderación solo para lo que llega de la hoja
            marca = _norm(_texto(g("aprobado")))
            if (config.REQUIERE_APROBACION and marca not in SI) or (not config.REQUIERE_APROBACION and marca in NO):
                stats["ocultas"] += 1
                continue

        lat, lon = _num(g("latitud")), _num(g("longitud"))
        if lat is None or lon is None:
            par = _coordenadas(g("coordenadas"))
            lat, lon = par if par else (None, None)
        if lat is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            stats["sin_coordenadas"] += 1
            continue
        if rutas.distancia_m(clat, clon, lat, lon) > config.MAX_DISTANCIA_SITIO_KM * 1000:
            stats["fuera_de_zona"] += 1
            continue

        t = {c: _texto(g(c))[:m] for c, m in LARGOS.items()}
        cat = t["categoria"] or "Otros"
        cat = canon.setdefault(_norm(cat), cat[:1].upper() + cat[1:])    # «parqueadero» y «Parqueadero» = misma categoría
        sitios.append({
            "id": n, "nombre": t["nombre"] or "Sin nombre", "categoria": cat, "lat": lat, "lon": lon,
            "direccion": t["direccion"], "descripcion": t["descripcion"], "horario": t["horario"],
            "telefono": t["telefono"], "web": _url(t["web"]),
            "linea_recta_m": round(rutas.distancia_m(clat, clon, lat, lon)),
        })
    stats["publicadas"] = len(sitios)
    return sitios, stats


# ----------------------------- fuentes de datos ----------------------------- #
def _valores_xlsx(ruta):
    import pandas as pd
    df = pd.read_excel(ruta, dtype=object)
    df = df.astype(object).where(df.notna(), None)
    return [[str(c) for c in df.columns]] + df.values.tolist()


def _guardar_copia(values):
    try:
        destino = config.SITIOS_COPIA_JSON
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps({"values": values}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(destino)
    except OSError:
        log.exception("No se pudo guardar la copia local de la hoja")


def _leer_copia():
    try:
        return json.loads(config.SITIOS_COPIA_JSON.read_text(encoding="utf-8"))["values"]
    except (OSError, ValueError, KeyError):
        return None


def _aplicar(values, fuente, error, desde_hoja):
    datos, stats = procesar(values, desde_hoja)
    _estado.update(datos=datos, stats=stats, fuente=fuente, error=error)


def _refrescar_hoja():
    ttl = config.SHEETS_CACHE_SEGUNDOS
    if _estado["t"] is not None and _ahora() - _estado["t"] < ttl:
        return
    with _lock:
        ahora = _ahora()
        if _estado["t"] is not None and ahora - _estado["t"] < ttl:       # otro hilo ya actualizó
            return
        try:
            values = hoja.leer_filas()
            _guardar_copia(values)
            _estado.update(t=ahora, values=values, actualizado=time.time())
            _aplicar(values, "Google Sheets", "", True)
        except hoja.HojaError as e:
            _estado["t"] = ahora - max(0, ttl - config.SHEETS_REINTENTO_SEGUNDOS)   # reintenta pronto
            values = _estado["values"] or _leer_copia()                  # último dato bueno (memoria o disco)
            if values:
                _estado["values"] = values
                _aplicar(values, "Copia local (Google no respondió)", str(e), True)
            else:
                _estado.update(datos=[], stats={}, fuente="Sin datos", error=str(e))


def _refrescar_xlsx():
    try:
        clave = (str(config.SITIOS_XLSX), config.SITIOS_XLSX.stat().st_mtime, tuple(config.CONJUNTO_CENTRO))
    except FileNotFoundError:
        _estado.update(datos=[], stats={}, fuente="Sin datos", error=f"No existe {config.SITIOS_XLSX.name}", clave_xlsx=None)
        return
    if _estado["clave_xlsx"] == clave:
        return
    try:
        _aplicar(_valores_xlsx(config.SITIOS_XLSX), "Excel local", "", False)
    except Exception:
        log.exception("No se pudo leer %s", config.SITIOS_XLSX)
        _estado.update(datos=[], stats={}, fuente="Sin datos", error="No se pudo leer el Excel local.")
    _estado.update(clave_xlsx=clave, actualizado=time.time())


# ---------------------------------- API ------------------------------------- #
def listar():
    """Sitios publicados. Consulta a Google como máximo cada SHEETS_CACHE_SEGUNDOS."""
    (_refrescar_hoja if hoja.configurada() else _refrescar_xlsx)()
    return _estado["datos"]


def obtener(sitio_id):
    return next((s for s in listar() if s["id"] == sitio_id), None)


def version(lista):
    """Huella de los datos: el navegador solo redibuja si cambia."""
    return hashlib.sha1(json.dumps(lista, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def resumen():
    """Estado para la página /estado (sin datos sensibles)."""
    listar()
    act = _estado["actualizado"]
    return {"fuente": _estado["fuente"], "error": _estado["error"], "stats": dict(_estado["stats"]),
            "hace_s": round(time.time() - act) if act else None, "google": hoja.configurada(),
            "requiere_aprobacion": config.REQUIERE_APROBACION}
