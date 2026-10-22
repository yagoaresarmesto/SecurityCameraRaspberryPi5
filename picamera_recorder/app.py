"""Application Factory: HTTP delega en un servicio recibido."""
from flask import Flask, Response, jsonify, render_template, request
from .config import RAIZ
from .sistema import estado_sistema
from .rutas_grabaciones import crear_rutas_grabaciones

def crear_app(servicio):
    app = Flask(__name__, template_folder=str(RAIZ / "templates"),
                static_folder=str(RAIZ / "static"))
    @app.get("/")
    def inicio():
        return render_template("index.html")
    @app.get("/estado")
    def estado():
        datos = dict(servicio.estado())
        datos["sistema"] = estado_sistema()
        respuesta = jsonify(datos)
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta
    @app.post("/api/movimiento/sensibilidad")
    def sensibilidad():
        origen = request.headers.get("Origin")
        if (request.headers.get("X-PiCameraRecorder") != "1"
                or request.headers.get("Sec-Fetch-Site") == "cross-site"
                or (origen is not None and origen.rstrip("/") != request.host_url.rstrip("/"))):
            return jsonify(error="Solicitud no permitida."), 403
        movimiento = getattr(servicio, "movimiento", None)
        if movimiento is None: return jsonify(error="Detección no disponible."), 503
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict) or not isinstance(datos.get("sensibilidad"), str):
            return jsonify(error="Sensibilidad no válida."), 400
        try: return jsonify(movimiento.nivel(datos["sensibilidad"]))
        except ValueError: return jsonify(error="Sensibilidad no válida."), 400

    @app.get("/directo")
    def directo():
        return Response(servicio.directo(),
                        mimetype="multipart/x-mixed-replace; boundary=frame",
                        headers={"Cache-Control": "no-store"})
    app.register_blueprint(crear_rutas_grabaciones(servicio.catalogo, servicio.optimizador, getattr(getattr(servicio, "movimiento", None), "eventos", None)))
    return app
