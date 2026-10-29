"""Portal de sitios de interés (Flask).  Ejecutar: python app.py → http://127.0.0.1:5000"""
from flask import Flask, abort, jsonify, render_template, request

import config
from services import rutas, sitios

app = Flask(__name__)


@app.context_processor
def globales():
    return {"conjunto": config.NOMBRE_CONJUNTO, "subtitulo": config.SUBTITULO}


@app.after_request
def cabeceras(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"          # el mapa siempre pide datos frescos
    return resp


def _https(url):
    url = (url or "").strip()
    return url if url.startswith("https://") else ""


# --------------------------------- Páginas --------------------------------- #
@app.route("/")
def mapa():
    return render_template("mapa.html", zoom=config.MAPA_ZOOM, centro_confirmado=config.CONJUNTO_CENTRO_CONFIRMADO,
                           refresco=config.ACTUALIZAR_CADA_SEG, enlace_agregar=_https(config.ENLACE_AGREGAR_SITIO))


@app.route("/opina")
def opina():
    url = config.GOOGLE_FORM_URL.strip()
    embed = url if url.startswith("https://docs.google.com/forms/") else ""        # solo se incrusta Google Forms
    return render_template("opina.html", form_embed=embed, form_enlace=_https(url))


@app.route("/estado")
def estado():
    return render_template("estado.html", s=sitios.resumen(), red=rutas.estado_red(),
                           centro=config.CONJUNTO_CENTRO, confirmado=config.CONJUNTO_CENTRO_CONFIRMADO,
                           cache=config.SHEETS_CACHE_SEGUNDOS)


# ----------------------------------- API ----------------------------------- #
@app.route("/api/sitios")
def api_sitios():
    lista = sitios.listar()
    lat, lon = config.CONJUNTO_CENTRO
    return jsonify({"centro": {"lat": lat, "lon": lon, "nombre": config.NOMBRE_CONJUNTO,
                               "confirmado": config.CONJUNTO_CENTRO_CONFIRMADO},
                    "version": sitios.version(lista), "sitios": lista})


@app.route("/api/sitios/<int:sitio_id>/ruta")
def api_ruta(sitio_id):
    """Ruta óptima (Dijkstra) del punto central al sitio. ?modo=a_pie | carro"""
    sitio = sitios.obtener(sitio_id)
    if not sitio:
        abort(404)
    modo = request.args.get("modo", "a_pie")
    if modo not in rutas.MODOS:
        return jsonify(error="Modo inválido. Use a_pie o carro."), 400
    try:
        return jsonify(rutas.calcular_ruta(sitio["lat"], sitio["lon"], modo))
    except rutas.RedNoDisponible as e:
        return jsonify(error=str(e), linea_recta_m=sitio["linea_recta_m"]), 503
    except rutas.SinRuta as e:
        return jsonify(error=str(e), linea_recta_m=sitio["linea_recta_m"]), 422


@app.errorhandler(404)
def no_encontrado(_):
    if request.path.startswith("/api/"):
        return jsonify(error="No encontrado"), 404
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)      # debug solo en desarrollo; en producción use waitress
