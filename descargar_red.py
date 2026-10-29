"""Descarga las calles de OpenStreetMap alrededor del conjunto (se hace UNA vez).

Uso:
    python descargar_red.py              # usa config.CONJUNTO_CENTRO y config.RADIO_RED_M
    python descargar_red.py --radio 3000

Necesita internet. Repita el comando si cambia el punto central en config.py.
"""
import argparse

import config
from services import rutas

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--radio", type=int, default=config.RADIO_RED_M, help="radio en metros (por defecto %(default)s)")
args = p.parse_args()

lat, lon = config.CONJUNTO_CENTRO
print(f"Descargando calles en {args.radio} m alrededor de ({lat}, {lon})… puede tardar un minuto.")
if not config.CONJUNTO_CENTRO_CONFIRMADO:
    print("⚠ Aviso: el punto central en config.py todavía está marcado como PROVISIONAL.")
try:
    red = rutas.descargar_red(radio=args.radio)
except rutas.RedNoDisponible as e:
    raise SystemExit(f"Error: {e}")
print(f"Listo: {len(red['nodos'])} esquinas y {len(red['vias'])} tramos guardados en {config.RED_VIAL_JSON}")
