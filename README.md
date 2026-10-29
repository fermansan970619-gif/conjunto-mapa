# Portal de sitios de interés – Terra Castilla PH

Mapa interactivo con los sitios de interés cercanos al conjunto (parqueaderos, centros comerciales, salud…), distancia calculada con **Dijkstra** desde el punto central del conjunto y una página para recoger opiniones con un **Google Form**.

100 % open source, sin APIs de pago ni base de datos: los sitios viven en una **hoja de Google Sheets** que se llena con un formulario, y el mapa se actualiza solo (guía en `GUIA_GOOGLE_SHEETS.md`).

## 1. Inicio rápido

Requisitos: **Python 3.10+**.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                      # abre http://127.0.0.1:5000
```

## 2. Lista de pendientes antes de presentarlo

| # | Qué falta | Dónde |
|---|---|---|
| 1 | **Coordenadas del punto central** (mejor la portería principal) y `CONJUNTO_CENTRO_CONFIRMADO = True` | `config.py` |
| 2 | **Descargar las calles** (una vez, con internet): `python descargar_red.py` | terminal |
| 3 | **Conectar Google Sheets + Form** (pasos en `GUIA_GOOGLE_SHEETS.md`) | variables de entorno |
| 4 | **URL del Google Form de opinión** | `config.py` → `GOOGLE_FORM_URL` |

Sin el paso 3 el portal usa el Excel local `data/sitios.xlsx` (3 sitios de ejemplo). Sin el paso 2 muestra solo la distancia en línea recta. Con el punto central provisional, el mapa avisa que es una versión de prueba.

> **Orden importante:** primero el paso 1 y luego el 2. La red de calles se descarga alrededor del punto central; si cambia el punto, repita `python descargar_red.py`. Puede comprobar todo en `/estado`.

## 3. Estructura

```
conjunto-mapa/
├── app.py                  ← Páginas y API (Flask)
├── config.py               ← TODO lo ajustable: punto central, formulario, rutas de archivos
├── descargar_red.py        ← Baja las calles de OpenStreetMap (una vez)
├── services/
│   ├── rutas.py            ← Grafo + algoritmo de Dijkstra
│   ├── hoja.py             ← Lee Google Sheets (API v4)
│   └── sitios.py           ← Valida, modera y cachea los sitios
├── templates/              ← HTML (mapa, opina, estado)
├── static/                 ← CSS (paleta de marca), JS del mapa, logos, Leaflet
├── data/
│   ├── sitios.xlsx         ← Respaldo local si Google no está configurado
│   ├── plantilla_hoja_google.csv ← Encabezados para crear la hoja a mano
│   ├── sitios_copia.json   ← Última lectura buena de Google (se crea sola)
│   └── red_vial.json       ← Se genera con descargar_red.py
├── GUIA_GOOGLE_SHEETS.md   ← Paso a paso de Google
└── tests/                  ← Pruebas automáticas
```

## 4. Sitios de interés (Google Sheets)

El flujo recomendado es **Google Form → hoja de Google → mapa** (guía completa en `GUIA_GOOGLE_SHEETS.md`):

- El servidor consulta la hoja como máximo **cada 20 s** (`SHEETS_CACHE_SEGUNDOS`), sin importar cuántos visitantes haya, y el mapa pregunta por cambios cada 20 s (`ACTUALIZAR_CADA_SEG`). Un registro nuevo aparece en unos 20–40 s, con un aviso en pantalla.
- Si Google falla, se sigue mostrando la última lectura buena (en memoria y en `data/sitios_copia.json`).
- Variables de entorno: `GOOGLE_SHEET_ID` (o la URL completa), `GOOGLE_API_KEY` (**secreta**), `GOOGLE_SHEET_PESTANA` (opcional) y `ENLACE_AGREGAR_SITIO` (botón «Agregar un sitio»).

**Columnas** (se reconocen por el nombre, también si son preguntas de un formulario como «Nombre del sitio»): `nombre`, `categoria`, **`coordenadas`** (texto «4.6483, -74.1429», o un enlace largo de Google Maps) o bien `latitud` y `longitud`, `direccion`, `descripcion`, `horario`, `telefono`, `web` y `aprobado`.

**Moderación** (`REQUIERE_APROBACION` en `config.py`): `False` publica todo al instante y oculta lo marcado **NO**; `True` publica solo lo marcado **SÍ**. Siempre se descartan filas sin coordenadas válidas o a más de 15 km del conjunto, y los textos y enlaces se limpian antes de mostrarse.

Íconos por categoría: diccionario `ICONOS` al inicio de `static/js/mapa.js`.

## 5. Cómo se calcula la distancia (Dijkstra)

1. `descargar_red.py` baja de OpenStreetMap las calles en un radio (`RADIO_RED_M`, por defecto 2.500 m) alrededor del conjunto.
2. `services/rutas.py` las convierte en un **grafo**: cada esquina es un nodo y cada tramo de calle una arista con su largo en metros.
3. **Dijkstra** se ejecuta una vez desde el punto central hacia toda la red y el resultado queda en memoria. Cada sitio solo consulta ese resultado, así que responder es instantáneo.
4. La ruta final es: punto central → calle más cercana → camino más corto → calle más cercana al sitio → sitio. Se dibuja en el mapa y se muestra la distancia y un tiempo estimado.

Hay dos modos: **a pie** (usa todas las calles y senderos, ignora sentidos únicos) y **en carro** (solo vías para vehículos y respeta los sentidos únicos). La ruta óptima se decide por **distancia**; el tiempo se estima con velocidades fijas (4,8 km/h a pie y 25 km/h en carro, editables en `MODOS` de `rutas.py`).

## 6. Página «¿Qué deberíamos colocar?» (Google Form)

1. En Google Forms cree el formulario (ideas de preguntas: ¿qué sitios le gustaría ver en el mapa?, ¿qué información del conjunto le sería útil?, ¿qué le falta o le confunde?).
2. Pulse **Enviar → pestaña `<>` (Insertar HTML)**.
3. Del código copie solo la dirección que está dentro de `src="…"`; empieza por `https://docs.google.com/forms/d/e/…/viewform?embedded=true`.
4. Péguela en `config.py`:
   ```python
   GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/XXXX/viewform?embedded=true"
   ```
   o defina la variable de entorno `GOOGLE_FORM_URL`.

Si la URL no es de Google Forms, la página muestra solo un botón de enlace, sin incrustar nada.

## 7. Dependencias

| Librería | Uso | Licencia |
|---|---|---|
| Flask | Servidor web | BSD‑3 |
| pandas + openpyxl | Solo para el Excel local de respaldo | BSD‑3 / MIT |
| waitress *(opcional)* | Servidor de producción | ZPL‑2.1 |
| Leaflet 1.9.4 *(incluida en `static/vendor`)* | Mapa | BSD‑2 |
| OpenStreetMap (calles y mosaicos) | Datos del mapa | ODbL (atribución incluida) |
| API de Google Sheets (módulo `urllib` estándar) | Leer la hoja | Servicio gratuito de Google |

El algoritmo de Dijkstra está escrito en el propio proyecto (módulo estándar `heapq`), sin librerías de grafos.

## 8. Publicación

```bash
pip install waitress
waitress-serve --listen=0.0.0.0:8000 app:app
```

Defina las variables de entorno de Google en el servidor (nunca en el código ni en GitHub). Ponga el sitio detrás de **HTTPS** (Caddy o Nginx con Let's Encrypt, gratuitos). Copie también `data/red_vial.json` al servidor, o ejecute `descargar_red.py` allí. La página `/estado` muestra si Google, las rutas y el punto central están bien, sin revelar claves.

## 9. Pruebas

```bash
python -m unittest -v
```

Verifican Dijkstra con una red de calles de tamaño conocido (distancias exactas, atajos peatonales, sentidos únicos), la lectura de Google Sheets con respuestas simuladas (encabezados de formulario, coordenadas en varios formatos, moderación, caché, respaldo cuando Google falla, traducción de errores), la API y la seguridad de los enlaces y del formulario.

## 10. Limitaciones

- **Calidad del mapa:** la ruta es tan buena como los datos de OpenStreetMap en la zona. Si falta una calle o un sendero, la ruta puede rodear de más. Se puede corregir en openstreetmap.org (es colaborativo).
- **Alcance del cálculo:** mide distancia por calles; no considera tráfico, semáforos, pendientes, escaleras ni cierres.
- **Sitios fuera de la red:** si un sitio queda a más de 400 m de una calle descargada (`MAX_CONECTOR_M`) o fuera del radio, se informa y se muestra solo la distancia en línea recta.
- **Internet:** `descargar_red.py` (una vez) y los mosaicos del mapa (cada visita) la necesitan. La descarga usa el servicio público Overpass: úselo con moderación.
- **Pendiente de validar en su entorno:** la descarga real desde Overpass y la lectura real de Google Sheets no pudieron ejecutarse durante el desarrollo (sin acceso a internet); el resto está probado con datos y respuestas simuladas. Si fallan, `/estado` y el script muestran el motivo.
- **«Tiempo real»:** hay un retraso de unos 20–40 segundos, no es instantáneo.
- **Hoja pública de lectura:** cualquiera con el enlace puede ver la hoja; no recolecte datos personales en el formulario.

## 11. Solución de problemas

| Problema | Solución |
|---|---|
| Panel dice «Falta descargar la red vial» | Ejecute `python descargar_red.py` (con internet). |
| «La red vial se descargó para otro punto central» | Cambió `CONJUNTO_CENTRO`: repita `python descargar_red.py`. |
| «El punto central queda lejos de una calle» | Revise las coordenadas (latitud primero, longitud después; en Colombia la longitud es negativa). |
| Un sitio no aparece | Mire `/estado`: cuenta las filas descartadas y por qué (coordenadas, lejanía, oculta o sin aprobar). |
| `/estado` muestra un error de Google | Ver la tabla de errores en `GUIA_GOOGLE_SHEETS.md`. |
| Mapa gris | Falta internet para los mosaicos de OpenStreetMap. |
| La página de opinión dice «pendiente» | Pegue la URL del formulario en `GOOGLE_FORM_URL`. |
