"""Pruebas de la lectura de Google Sheets (con respuestas simuladas), la moderación y la API."""
import io
import json
import unittest
import urllib.error
from unittest import mock

import config
from services import hoja, rutas, sitios
from tests.test_rutas import Base, punto, red_cuadricula

ENC_FORM = ["Marca temporal", "Nombre del sitio", "Categoría", "Coordenadas (clic derecho en Google Maps y copiar)",
            "Dirección", "Descripción", "Horario", "Teléfono", "Página web", "Aprobado"]


def fila(nombre, cat="Parqueadero", coord="4.6490, -74.1450", aprobado=None, tel=None, web=None):
    f = [45000.5, nombre, cat, coord, None, "desc", None, tel, web, aprobado]
    while f and f[-1] is None:
        f.pop()                                       # la API de Google recorta las celdas vacías del final
    return f


class BaseGoogle(Base):
    def setUp(self):
        self.preparar(red_cuadricula())
        config.GOOGLE_SHEET_ID, config.GOOGLE_API_KEY = "ID_HOJA", "CLAVE"
        config.SHEETS_CACHE_SEGUNDOS = 20
        self.reloj = [1000.0]
        p = mock.patch.object(sitios, "_ahora", lambda: self.reloj[0])
        p.start(); self.addCleanup(p.stop)
        self.valores = [ENC_FORM, fila("Parqueadero A")]
        self.llamadas = []
        self.falla = None

        def falso(url):
            self.llamadas.append(url)
            if self.falla:
                raise self.falla
            return {"values": self.valores}
        p2 = mock.patch.object(hoja, "_http_get_json", falso)
        p2.start(); self.addCleanup(p2.stop)


class TestLecturaDeHoja(BaseGoogle):
    def test_entiende_encabezados_de_un_formulario_y_ordena(self):
        self.valores.append(fila("Droguería", "Salud", "4,6475, -74,1430", tel=3001234567.0, web="drogueria.com"))
        lista = sitios.listar()
        self.assertEqual([s["nombre"] for s in lista], ["Parqueadero A", "Droguería"])
        d = lista[1]
        self.assertEqual((d["telefono"], d["web"]), ("3001234567", "https://drogueria.com"))   # sin «.0»
        self.assertAlmostEqual(d["lat"], 4.6475); self.assertAlmostEqual(d["lon"], -74.143)     # comas decimales
        self.assertEqual([s["id"] for s in lista], [2, 3])                                       # id = nº de fila de la hoja

    def test_url_de_la_api_lleva_clave_y_pestana(self):
        config.GOOGLE_SHEET_ID = "https://docs.google.com/spreadsheets/d/ABC_123-x/edit#gid=0"
        sitios.listar()
        url = self.llamadas[0]
        self.assertIn("/spreadsheets/ABC_123-x/values/A%3AZ?", url)          # sin pestaña = primera
        self.assertIn("key=CLAVE", url); self.assertIn("UNFORMATTED_VALUE", url)

    def test_pestana_con_apostrofe(self):
        config.GOOGLE_SHEET_PESTANA = "Juan's hoja"
        try:
            hoja.leer_filas()
        finally:
            config.GOOGLE_SHEET_PESTANA = ""
        self.assertIn("%27Juan%27%27s%20hoja%27%21A%3AZ", self.llamadas[0])

    def test_formatos_de_coordenadas(self):
        c = sitios._coordenadas
        self.assertEqual(c("4.648300, -74.142900"), (4.6483, -74.1429))
        self.assertEqual(c("4.6483,-74.1429"), (4.6483, -74.1429))
        self.assertEqual(c("https://www.google.com/maps/place/X/@4.6483,-74.1429,17z/data=!3m1"), (4.6483, -74.1429))
        self.assertEqual(c("https://www.google.com/maps?q=4.6483,-74.1429"), (4.6483, -74.1429))
        self.assertIsNone(c("https://maps.app.goo.gl/abc123"))               # enlace corto: no se puede leer sin visitarlo
        self.assertIsNone(c("Cerca del parque"))

    def test_descartes_y_proteccion(self):
        self.valores += [fila("Sin coordenada", coord="no sé"),
                         fila("Muy lejos", coord="4.80, -74.14"),                        # ~17 km
                         fila("Error de tipeo", coord="46483, -74.1429"),
                         [],                                                              # fila vacía
                         fila("<script>alert(1)</script>", web="javascript:alert(1)", tel="x" * 100)]
        lista = sitios.listar()
        self.assertEqual([s["nombre"] for s in lista], ["Parqueadero A", "<script>alert(1)</script>"])   # se muestra como texto
        self.assertEqual(lista[1]["web"], ""); self.assertEqual(len(lista[1]["telefono"]), 40)
        st = sitios.resumen()["stats"]
        self.assertEqual((st["sin_coordenadas"], st["fuera_de_zona"], st["publicadas"]), (2, 1, 2))

    def test_categorias_con_distinta_escritura_se_unifican(self):
        self.valores += [fila("B", "parqueadero"), fila("C", "PARQUEADERO ")]
        self.assertEqual({s["categoria"] for s in sitios.listar()}, {"Parqueadero"})


class TestModeracion(BaseGoogle):
    def test_sin_aprobacion_se_publica_todo_salvo_NO(self):
        config.REQUIERE_APROBACION = False
        self.valores += [fila("Oculto", aprobado="NO"), fila("Visible", aprobado="sí")]
        self.assertEqual([s["nombre"] for s in sitios.listar()], ["Parqueadero A", "Visible"])

    def test_con_aprobacion_solo_se_publica_lo_aprobado(self):
        config.REQUIERE_APROBACION = True
        self.valores += [fila("Aprobado", aprobado="SÍ"), fila("Pendiente", aprobado=None), fila("Rechazado", aprobado="no")]
        self.assertEqual([s["nombre"] for s in sitios.listar()], ["Aprobado"])
        self.assertEqual(sitios.resumen()["stats"]["ocultas"], 3)


class TestCacheYRespaldo(BaseGoogle):
    def test_no_consulta_a_google_en_cada_visita(self):
        for _ in range(5):
            sitios.listar()
        self.assertEqual(len(self.llamadas), 1)
        self.reloj[0] += 21
        self.valores.append(fila("Nuevo"))
        self.assertEqual(len(sitios.listar()), 2)                            # ya venció la caché: aparece el registro nuevo
        self.assertEqual(len(self.llamadas), 2)

    def test_si_google_falla_se_mantiene_el_ultimo_dato_bueno(self):
        self.assertEqual(len(sitios.listar()), 1)
        self.reloj[0] += 21
        self.falla = hoja.HojaError("La hoja no es pública. Compártala…")
        self.assertEqual(len(sitios.listar()), 1)
        r = sitios.resumen()
        self.assertIn("Copia local", r["fuente"]); self.assertIn("no es pública", r["error"])
        self.reloj[0] += 11                                                  # reintenta a los 10 s, no a los 20
        self.falla = None
        self.valores.append(fila("Recuperado"))
        self.assertEqual(len(sitios.listar()), 2)
        self.assertEqual(sitios.resumen()["error"], "")

    def test_arranque_con_google_caido_usa_la_copia_en_disco(self):
        sitios.listar()                                                      # guarda copia
        sitios._estado.update(t=None, values=None, datos=[])                 # simula reinicio del servidor
        self.falla = hoja.HojaError("sin conexión")
        self.assertEqual(len(sitios.listar()), 1)

    def test_arranque_con_google_caido_y_sin_copia(self):
        self.falla = hoja.HojaError("sin conexión")
        self.assertEqual(sitios.listar(), [])
        self.assertEqual(sitios.resumen()["fuente"], "Sin datos")


class TestErroresDeGoogle(unittest.TestCase):
    def mensaje(self, codigo, texto):
        return hoja._mensaje(codigo, {"message": texto})

    def test_mensajes_utiles(self):
        self.assertIn("clave de API no es válida", self.mensaje(400, "API key not valid. Please pass a valid API key."))
        self.assertIn("pestaña", self.mensaje(400, "Unable to parse range: Hoja9!A:Z"))
        self.assertIn("no está habilitada", self.mensaje(403, "Google Sheets API has not been used in project 1234 before or it is disabled."))
        self.assertIn("no es pública", self.mensaje(403, "The caller does not have permission"))
        self.assertIn("restricciones", self.mensaje(403, "Requests from referer <empty> are blocked."))
        self.assertIn("GOOGLE_SHEET_ID", self.mensaje(404, "Requested entity was not found."))
        self.assertNotIn("1234", self.mensaje(403, "Google Sheets API has not been used in project 1234 before"))   # no filtra datos internos

    def test_http_error_se_traduce(self):
        cuerpo = io.BytesIO(json.dumps({"error": {"code": 403, "message": "The caller does not have permission"}}).encode())
        err = urllib.error.HTTPError("https://x", 403, "Forbidden", {}, cuerpo)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(hoja.HojaError) as cm:
                hoja._http_get_json("https://x?key=SECRETA")
        self.assertIn("no es pública", str(cm.exception)); self.assertNotIn("SECRETA", str(cm.exception))

    def test_sin_red(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sin red")):
            with self.assertRaises(hoja.HojaError):
                hoja._http_get_json("https://x")


class TestAPIyPaginas(BaseGoogle):
    def setUp(self):
        super().setUp()
        from app import app
        self.c = app.test_client()

    def test_api_con_version_y_sin_cache(self):
        r = self.c.get("/api/sitios")
        d = r.get_json()
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        v1 = d["version"]
        self.reloj[0] += 21; self.valores.append(fila("Otro"))
        v2 = self.c.get("/api/sitios").get_json()
        self.assertNotEqual(v1, v2["version"]); self.assertEqual(len(v2["sitios"]), 2)
        self.assertEqual(self.c.get("/api/sitios").get_json()["version"], v2["version"])     # sin cambios, misma huella

    def test_ruta_ok_y_errores(self):
        self.valores.append(fila("Tienda", coord="{}, {}".format(*punto(3, 2))))
        self.assertAlmostEqual(self.c.get("/api/sitios/3/ruta").get_json()["distancia_m"], 500, delta=5)
        self.assertEqual(self.c.get("/api/sitios/99/ruta").status_code, 404)
        self.assertEqual(self.c.get("/api/sitios/3/ruta?modo=moto").status_code, 400)

    def test_paginas(self):
        for url in ("/", "/opina", "/estado"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/admin").status_code, 404)

    def test_estado_no_filtra_secretos(self):
        self.falla = hoja.HojaError("La hoja no es pública.")
        sitios._estado.update(t=None)
        html = self.c.get("/estado").get_data(as_text=True)
        self.assertIn("no es pública", html)
        for secreto in ("CLAVE", "ID_HOJA"):
            self.assertNotIn(secreto, html)

    def test_boton_agregar_solo_con_https(self):
        config.ENLACE_AGREGAR_SITIO = "https://forms.gle/abc"
        self.assertIn("Agregar un sitio", self.c.get("/").get_data(as_text=True))
        config.ENLACE_AGREGAR_SITIO = "javascript:alert(1)"
        self.assertNotIn("Agregar un sitio", self.c.get("/").get_data(as_text=True))

    def test_opina_solo_incrusta_google_forms(self):
        config.GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/ABC/viewform?embedded=true"
        self.assertIn("<iframe", self.c.get("/opina").get_data(as_text=True))
        config.GOOGLE_FORM_URL = "https://sitio-malicioso.com/form"
        self.assertNotIn("<iframe", self.c.get("/opina").get_data(as_text=True))
        config.GOOGLE_FORM_URL = ""
        self.assertIn("pendiente de conectar", self.c.get("/opina").get_data(as_text=True))


class TestExcelLocal(Base):
    def test_respaldo_excel_cuando_no_hay_google(self):
        import pandas as pd
        self.preparar(red_cuadricula())
        pd.DataFrame([["Tienda", "Salud", "4.6490, -74.1450", "no"]], columns=["nombre", "categoria", "coordenadas", "aprobado"]).to_excel(config.SITIOS_XLSX, index=False)
        lista = sitios.listar()
        self.assertEqual([s["nombre"] for s in lista], ["Tienda"])           # la moderación solo aplica a la hoja de Google
        self.assertEqual(sitios.resumen()["fuente"], "Excel local")


if __name__ == "__main__":
    unittest.main()
