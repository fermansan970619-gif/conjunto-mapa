"""Rutas óptimas con el algoritmo de Dijkstra sobre la red vial de OpenStreetMap.

Idea general:
  1. descargar_red() baja las calles alrededor del conjunto (una sola vez) y las guarda.
  2. Con esas calles se arma un GRAFO: cada esquina es un nodo y cada tramo de calle
     una arista con su longitud en metros.
  3. Se ejecuta Dijkstra UNA vez desde el punto central hacia toda la red (queda en
     memoria). Después, cada sitio de interés solo consulta ese resultado.
  4. La ruta final = punto central → calle más cercana → camino óptimo → calle más
     cercana al sitio → sitio.
"""
import heapq
import json
import math
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config

OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

# Velocidades solo para estimar el tiempo (la ruta óptima se decide por distancia)
MODOS = {
    "a_pie": {"etiqueta": "A pie", "kmh": 4.8},
    "carro": {"etiqueta": "En carro", "kmh": 25.0},
}
SIN_ACCESO_A_PIE = {"motorway", "motorway_link", "proposed", "construction", "raceway", "bus_guideway", "escape"}
VIAS_CARRO = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
              "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "service", "living_street"}
ETIQUETAS_UTILES = ("highway", "oneway", "junction", "access", "foot", "motor_vehicle")


class RedNoDisponible(Exception):
    """Falta la red vial, está dañada o se descargó para otro punto."""


class SinRuta(Exception):
    """No hay camino entre el punto central y el sitio."""


def distancia_m(lat1, lon1, lat2, lon2):
    """Distancia en línea recta sobre la esfera (fórmula de Haversine), en metros."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


# ----------------------------- descarga de la red --------------------------- #
def _reducir(crudo, lat, lon, radio):
    """Deja solo lo necesario de la respuesta de Overpass (nodos usados y etiquetas útiles)."""
    nodos = {e["id"]: [e["lat"], e["lon"]] for e in crudo.get("elements", []) if e.get("type") == "node"}
    vias = []
    for e in crudo.get("elements", []):
        tags = e.get("tags") or {}
        if e.get("type") != "way" or "highway" not in tags:
            continue
        nds = [n for n in e.get("nodes", []) if n in nodos]
        if len(nds) >= 2:
            vias.append({"nodos": nds, "tags": {k: tags[k] for k in ETIQUETAS_UTILES if k in tags}})
    usados = {n for v in vias for n in v["nodos"]}
    return {"centro": [lat, lon], "radio": radio, "nodos": {str(n): nodos[n] for n in usados}, "vias": vias}


def descargar_red(lat=None, lon=None, radio=None, destino=None):
    """Descarga las calles de OpenStreetMap (Overpass API) y las guarda en un JSON."""
    lat, lon = (lat, lon) if lat is not None else config.CONJUNTO_CENTRO
    radio = radio or config.RADIO_RED_M
    destino = Path(destino or config.RED_VIAL_JSON)
    consulta = f'[out:json][timeout:90];way["highway"](around:{radio},{lat},{lon});(._;>;);out body qt;'
    cuerpo = urllib.parse.urlencode({"data": consulta}).encode()
    ultimo_error = None
    for url in OVERPASS_URLS:
        try:
            req = urllib.request.Request(url, data=cuerpo, headers={"User-Agent": "portal-mapa-conjunto/1.0"})
            with urllib.request.urlopen(req, timeout=150) as r:
                crudo = json.load(r)
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            ultimo_error = e
    else:
        raise RedNoDisponible(f"No se pudo descargar la red vial: {ultimo_error}")
    red = _reducir(crudo, lat, lon, radio)
    if not red["vias"]:
        raise RedNoDisponible("La descarga no trajo calles. Verifique las coordenadas del conjunto.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(red), encoding="utf-8")
    tmp.replace(destino)
    return red


# ----------------------------------- grafo ---------------------------------- #
def _permitida(tags, modo):
    hw = tags.get("highway")
    if modo == "a_pie":
        return hw not in SIN_ACCESO_A_PIE and tags.get("foot") != "no"
    return hw in VIAS_CARRO and tags.get("access") != "no" and tags.get("motor_vehicle") != "no"


def _sentido(tags):
    """1 = solo en el sentido del dibujo, -1 = solo al revés, 0 = doble sentido."""
    ow = str(tags.get("oneway", "")).lower()
    if ow in ("yes", "true", "1") or tags.get("junction") in ("roundabout", "circular"):
        return 1
    return -1 if ow == "-1" else 0


def dijkstra(grafo, origen):
    """Camino más corto desde `origen` a todos los nodos alcanzables.

    Devuelve (dist, prev): dist[n] = metros mínimos hasta n; prev[n] = nodo anterior
    en el mejor camino (sirve para reconstruir la ruta).
    """
    dist, prev = {origen: 0.0}, {}
    cola = [(0.0, origen)]
    while cola:
        d, u = heapq.heappop(cola)
        if d > dist.get(u, math.inf):          # entrada vieja: ya hay un camino mejor
            continue
        for v, peso in grafo.get(u, ()):
            nd = d + peso
            if nd < dist.get(v, math.inf):
                dist[v], prev[v] = nd, u
                heapq.heappush(cola, (nd, v))
    return dist, prev


class Red:
    def __init__(self, datos):
        self.centro = tuple(datos["centro"])
        self.nodos = {int(k): tuple(v) for k, v in datos["nodos"].items()}
        self.vias = datos["vias"]
        self._grafos, self._arboles = {}, {}
        self._lock = threading.Lock()

    def grafo(self, modo):
        if modo not in self._grafos:
            g = {}
            for via in self.vias:
                tags = via["tags"]
                if not _permitida(tags, modo):
                    continue
                sentido = _sentido(tags) if modo == "carro" else 0     # a pie ignora los sentidos únicos
                for a, b in zip(via["nodos"], via["nodos"][1:]):
                    d = distancia_m(*self.nodos[a], *self.nodos[b])
                    g.setdefault(a, [])
                    g.setdefault(b, [])
                    if sentido >= 0:
                        g[a].append((b, d))
                    if sentido <= 0:
                        g[b].append((a, d))
            self._grafos[modo] = g
        return self._grafos[modo]

    def cercanos(self, lat, lon, candidatos, n=1):
        """Los n nodos más cercanos a (lat, lon) entre `candidatos` (aproximación plana, suficiente a escala de barrio)."""
        k = math.cos(math.radians(lat))
        return heapq.nsmallest(n, candidatos, key=lambda i: (self.nodos[i][0] - lat) ** 2 + ((self.nodos[i][1] - lon) * k) ** 2)

    def arbol(self, modo, lat, lon):
        """Dijkstra desde el punto central (se calcula una vez por modo y queda en memoria)."""
        with self._lock:
            if modo not in self._arboles:
                g = self.grafo(modo)
                if not g:
                    raise SinRuta("No hay calles transitables en este modo dentro de la red descargada.")
                # El punto central podría caer en un tramo aislado (ej. una vía privada sin conexión):
                # se prueban las 8 esquinas más cercanas y se queda con la mejor conectada.
                mejor = None
                for nodo in self.cercanos(lat, lon, g.keys(), 8):
                    dist, prev = dijkstra(g, nodo)
                    if mejor is None or len(dist) > len(mejor["dist"]) * 1.05:
                        mejor = {"origen": nodo, "dist": dist, "prev": prev}
                self._arboles[modo] = mejor
            return self._arboles[modo]


_cache = {"clave": None, "red": None}


def cargar_red():
    ruta = Path(config.RED_VIAL_JSON)
    if not ruta.exists():
        raise RedNoDisponible("Falta descargar la red vial. Ejecute: python descargar_red.py")
    clave = (str(ruta), ruta.stat().st_mtime, tuple(config.CONJUNTO_CENTRO))
    if _cache["clave"] != clave:
        try:
            red = Red(json.loads(ruta.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError) as e:
            raise RedNoDisponible(f"El archivo de red vial está dañado ({e}). Vuelva a ejecutar descargar_red.py") from e
        if distancia_m(*red.centro, *config.CONJUNTO_CENTRO) > 100:
            raise RedNoDisponible("La red vial se descargó para otro punto central. Vuelva a ejecutar descargar_red.py")
        _cache.update(clave=clave, red=red)
    return _cache["red"]


def estado_red():
    try:
        red = cargar_red()
        return {"disponible": True, "nodos": len(red.nodos), "tramos": len(red.vias), "mensaje": "Red vial lista."}
    except RedNoDisponible as e:
        return {"disponible": False, "nodos": 0, "tramos": 0, "mensaje": str(e)}


# ----------------------------------- ruta ----------------------------------- #
def calcular_ruta(lat, lon, modo="a_pie"):
    """Ruta óptima (Dijkstra) desde el punto central del conjunto hasta (lat, lon)."""
    if modo not in MODOS:
        raise ValueError(f"Modo desconocido: {modo}")
    red = cargar_red()
    clat, clon = config.CONJUNTO_CENTRO
    arbol = red.arbol(modo, clat, clon)

    destino = red.cercanos(lat, lon, arbol["dist"].keys(), 1)[0]    # solo nodos alcanzables
    conector_ini = distancia_m(clat, clon, *red.nodos[arbol["origen"]])
    conector_fin = distancia_m(lat, lon, *red.nodos[destino])
    if conector_ini > config.MAX_CONECTOR_M:
        raise SinRuta("El punto central del conjunto queda lejos de una calle de la red descargada. Revise sus coordenadas.")
    if conector_fin > config.MAX_CONECTOR_M:
        raise SinRuta("Este sitio queda fuera del área de calles descargada.")

    camino = [destino]
    while camino[-1] != arbol["origen"]:
        camino.append(arbol["prev"][camino[-1]])
    camino.reverse()

    puntos = [[clat, clon]] + [list(red.nodos[n]) for n in camino] + [[lat, lon]]
    total = sum(distancia_m(*a, *b) for a, b in zip(puntos, puntos[1:]))
    aviso = ""
    if max(conector_ini, conector_fin) > config.AVISO_CONECTOR_M:
        aviso = "Uno de los extremos queda algo lejos de la calle más cercana; la distancia es aproximada."
    return {
        "modo": modo, "metodo": "Dijkstra", "distancia_m": round(total),
        "duracion_min": round(total / 1000 / MODOS[modo]["kmh"] * 60, 1),
        "linea_recta_m": round(distancia_m(clat, clon, lat, lon)),
        "ruta": [[round(a, 6), round(b, 6)] for a, b in puntos], "aviso": aviso,
    }
