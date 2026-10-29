"""Pruebas del cálculo de rutas y de la API.  Ejecutar:  python -m unittest -v"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import config
from services import rutas, sitios

LAT0, LON0, PASO = 4.65, -74.14, 100          # cuadrícula de calles cada 100 m, centrada en (LAT0, LON0)
DLAT = PASO / 111320
DLON = PASO / (111320 * math.cos(math.radians(LAT0)))


def punto(i, j):
    return LAT0 + i * DLAT, LON0 + j * DLON


def red_cuadricula(n=5, extra_vias=(), fila0_sentido_unico_oeste=False):
    """Calles N-S y E-O cada 100 m. Nodo (i,j): i = filas al norte, j = columnas al este."""
    ids, nodos, nid = {}, {}, 1
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            ids[(i, j)] = nid
            nodos[str(nid)] = list(punto(i, j))
            nid += 1
    vias = []
    for i in range(-n, n + 1):
        ruta = [ids[(i, j)] for j in range(-n, n + 1)]
        tags = {"highway": "residential"}
        if i == 0 and fila0_sentido_unico_oeste:
            ruta.reverse()                                  # se dibuja de este a oeste…
            tags["oneway"] = "yes"                          # …y solo se puede ir en ese sentido
        vias.append({"nodos": ruta, "tags": tags})
    for j in range(-n, n + 1):
        vias.append({"nodos": [ids[(i, j)] for i in range(-n, n + 1)], "tags": {"highway": "residential"}})
    for (a, b, tags) in extra_vias:
        vias.append({"nodos": [ids[a], ids[b]], "tags": tags})
    return {"centro": [LAT0, LON0], "radio": 2000, "nodos": nodos, "vias": vias}


class Base(unittest.TestCase):
    def preparar(self, red, hay_red=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        claves = ("RED_VIAL_JSON", "CONJUNTO_CENTRO", "SITIOS_XLSX", "SITIOS_COPIA_JSON", "GOOGLE_SHEET_ID", "GOOGLE_API_KEY",
                  "REQUIERE_APROBACION", "SHEETS_CACHE_SEGUNDOS", "GOOGLE_FORM_URL", "ENLACE_AGREGAR_SITIO")
        self.viejo = {k: getattr(config, k) for k in claves}
        self.addCleanup(lambda: [setattr(config, k, v) for k, v in self.viejo.items()])
        config.RED_VIAL_JSON = d / "red.json"
        config.CONJUNTO_CENTRO = (LAT0, LON0)
        config.SITIOS_XLSX = d / "sitios.xlsx"
        config.SITIOS_COPIA_JSON = d / "copia.json"
        config.GOOGLE_SHEET_ID = config.GOOGLE_API_KEY = ""
        sitios._estado.update(t=None, values=None, datos=[], stats={}, fuente="", error="", actualizado=None, clave_xlsx=None)
        if hay_red:
            config.RED_VIAL_JSON.write_text(json.dumps(red), encoding="utf-8")
        rutas._cache.update(clave=None, red=None)


class TestDijkstra(Base):
    def test_distancia_en_cuadricula(self):
        """A (3 norte, 2 este) por calles hay 5 cuadras = 500 m (no la diagonal de ~361 m)."""
        self.preparar(red_cuadricula())
        r = rutas.calcular_ruta(*punto(3, 2), modo="a_pie")
        self.assertAlmostEqual(r["distancia_m"], 500, delta=5)
        self.assertLess(r["linea_recta_m"], 400)
        self.assertEqual(r["ruta"][0], [round(LAT0, 6), round(LON0, 6)])

    def test_atajo_peatonal(self):
        """Un sendero diagonal solo lo usa quien va a pie; en carro se mantiene la ruta por calles."""
        sendero = [((0, 0), (3, 3), {"highway": "footway"})]
        self.preparar(red_cuadricula(extra_vias=sendero))
        a_pie = rutas.calcular_ruta(*punto(3, 3), modo="a_pie")["distancia_m"]
        carro = rutas.calcular_ruta(*punto(3, 3), modo="carro")["distancia_m"]
        self.assertAlmostEqual(a_pie, math.hypot(300, 300), delta=5)      # ≈ 424 m
        self.assertAlmostEqual(carro, 600, delta=5)

    def test_sentido_unico_solo_afecta_al_carro(self):
        """Si la calle de salida es de un solo sentido (hacia el oeste), el carro debe rodear."""
        self.preparar(red_cuadricula(fila0_sentido_unico_oeste=True))
        a_pie = rutas.calcular_ruta(*punto(0, 3), modo="a_pie")["distancia_m"]
        carro = rutas.calcular_ruta(*punto(0, 3), modo="carro")["distancia_m"]
        self.assertAlmostEqual(a_pie, 300, delta=5)
        self.assertAlmostEqual(carro, 500, delta=5)                       # sube, cruza y baja

    def test_dijkstra_elige_el_menor_entre_alternativas(self):
        grafo = {1: [(2, 10), (3, 1)], 2: [(4, 1)], 3: [(2, 1), (4, 20)], 4: []}
        dist, prev = rutas.dijkstra(grafo, 1)
        self.assertEqual(dist[4], 3)                       # 1→3→2→4 = 1+1+1
        self.assertEqual(prev[4], 2)

    def test_sitio_fuera_de_la_red(self):
        self.preparar(red_cuadricula())
        with self.assertRaises(rutas.SinRuta):
            rutas.calcular_ruta(LAT0 + 0.05, LON0, modo="a_pie")          # ~5,5 km al norte

    def test_sin_red_descargada(self):
        self.preparar(None, hay_red=False)
        with self.assertRaises(rutas.RedNoDisponible):
            rutas.calcular_ruta(*punto(1, 1))

    def test_red_de_otro_punto_central(self):
        self.preparar(red_cuadricula())
        config.CONJUNTO_CENTRO = (LAT0 + 0.01, LON0)
        with self.assertRaises(rutas.RedNoDisponible):
            rutas.calcular_ruta(*punto(1, 1))


if __name__ == "__main__":
    unittest.main()
