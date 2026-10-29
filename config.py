"""Configuración central del portal. Edite SOLO este archivo para ajustar lo principal."""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()  # carga variables de entorno desde .env si existe

BASE_DIR = Path(__file__).resolve().parent

NOMBRE_CONJUNTO = "Terra Castilla PH"
SUBTITULO = "Sitios de interés cerca del conjunto"

CONJUNTO_CENTRO = (4.634510740227775, -74.15552672691143)
CONJUNTO_CENTRO_CONFIRMADO = False
MAPA_ZOOM = 15

# --- Red vial para el cálculo de rutas (Dijkstra) ----------------------------
RED_VIAL_JSON = BASE_DIR / "data" / "red_vial.json"   # se genera con descargar_red.py
RADIO_RED_M = 2500          # radio de calles a descargar alrededor del conjunto
MAX_CONECTOR_M = 400        # un sitio a más de esto de una calle se considera fuera de la red
AVISO_CONECTOR_M = 150      # a partir de aquí se avisa que la distancia es aproximada

# --- Datos de los sitios -----------------------------------------------------
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")                # ⚠ SECRETA: defínala como variable de entorno
GOOGLE_SHEET_PESTANA = os.getenv("GOOGLE_SHEET_PESTANA")  # nombre de la pestaña; vacío = la primera
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")            # ⚠ SECRETA: defínala como variable de entorno
SHEETS_CACHE_SEGUNDOS = 20      # cada cuántos segundos como máximo se consulta a Google (sin importar cuántos visitantes haya)
SHEETS_REINTENTO_SEGUNDOS = 10  # si Google falla, cuándo reintentar
SHEETS_TIMEOUT = 10             # segundos de espera por Google
ACTUALIZAR_CADA_SEG = 20        # cada cuántos segundos el mapa pregunta si hay sitios nuevos

SITIOS_XLSX = BASE_DIR / "data" / "sitios.xlsx"                  # respaldo local
SITIOS_COPIA_JSON = BASE_DIR / "data" / "sitios_copia.json"      # última lectura buena de Google (se crea sola)

REQUIERE_APROBACION = True
MAX_DISTANCIA_SITIO_KM = 15 

ENLACE_AGREGAR_SITIO = os.environ.get("ENLACE_AGREGAR_SITIO", "")

GOOGLE_FORM_URL = os.environ.get("GOOGLE_FORM_URL", "https://forms.gle/wRdgJ25xEnnwB7WK8")
