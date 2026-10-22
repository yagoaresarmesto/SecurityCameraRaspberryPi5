"""Blueprint de consulta de grabaciones. El catalogo controla el acceso al disco."""
from datetime import date
from threading import Lock

from flask import Blueprint, abort, jsonify, request, url_for

from .almacenamiento import SESION, VIDEO
from .http_video import responder_video
from .importantes import GrabacionProtegida

ARCHIVOS_POR_PAGINA = 30


def cambio_permitido():
    origen = request.headers.get("Origin")
    return (request.headers.get("X-PiCameraRecorder") == "1"
            and request.headers.get("Sec-Fetch-Site") != "cross-site"
            and (origen is None or origen.rstrip("/") == request.host_url.rstrip("/")))


def filtros_consulta():
    fecha = request.args.get("fecha", "")
    sesion = request.args.get("sesion", "")
    pagina = int(request.args.get("pagina", "1"))
    if pagina < 1:
        raise ValueError("Pagina no valida")
    if fecha and date.fromisoformat(fecha).isoformat() != fecha:
        raise ValueError("Fecha no valida")
    if sesion and not SESION.fullmatch(sesion):
        raise ValueError("Sesion no valida")
    return fecha, sesion, pagina


def enlaces_video(item, preparador):
    if item["en_curso"]:
        return
    sesion, nombre = item["sesion"], item["archivo"]
    preparando = preparador is not None and not preparador.preparado(sesion, nombre)
    item["preparando"] = preparando
    item["preparacion_error"] = preparador.errores.get((sesion, nombre)) if preparador else None
    base = url_for("grabaciones.video", sesion=sesion, nombre=nombre)
    item["descarga"] = base + "?descargar=1"
    if not preparando:
        item["url"] = base


def crear_rutas_grabaciones(catalogo, preparador=None, eventos=None):
    rutas = Blueprint("grabaciones", __name__)
    bloqueo_borrado = preparador.bloqueo if preparador is not None else Lock()

    @rutas.delete("/api/grabaciones/<sesion>/<nombre>")
    def eliminar(sesion, nombre):
        # Una web ajena no puede enviar esta cabecera sin permiso CORS.
        if not cambio_permitido():
            return jsonify(error="Solicitud de borrado no permitida."), 403
        try:
            liberados = catalogo.eliminar(sesion, nombre, bloqueo_borrado)
        except BlockingIOError:
            return jsonify(error="No se puede eliminar el archivo que sigue en curso."), 409
        except GrabacionProtegida:
            return jsonify(error="Este vídeo es importante. Quita la estrella antes de eliminarlo."), 409
        except FileNotFoundError:
            return jsonify(error="La grabación ya no está disponible."), 404
        except OSError:
            return jsonify(error="No se pudo eliminar la grabación. Revisa los permisos y el disco."), 500
        return jsonify(eliminado=True, bytes_liberados=liberados)

    @rutas.put("/api/grabaciones/<sesion>/<nombre>/importante")
    def importancia(sesion, nombre):
        if not cambio_permitido():
            return jsonify(error="Solicitud no permitida."), 403
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict) or type(datos.get('importante')) is not bool:
            return jsonify(error="Indica si el vídeo es importante."), 400
        try:
            catalogo.marcar_importante(sesion, nombre, datos['importante'], bloqueo_borrado)
        except FileNotFoundError:
            return jsonify(error="La grabación ya no está disponible."), 404
        except OSError:
            return jsonify(error="No se pudo guardar la estrella. Revisa los permisos y el disco."), 500
        respuesta = jsonify(importante=datos['importante'])
        respuesta.headers['Cache-Control'] = 'no-store'
        return respuesta


    @rutas.get("/api/grabaciones/<sesion>/<nombre>/movimiento")
    def movimiento_video(sesion, nombre):
        if not SESION.fullmatch(sesion) or not VIDEO.fullmatch(nombre):
            return jsonify(error="Grabación no válida."), 404
        if not any(v['sesion']==sesion and v['archivo']==nombre for v in catalogo.listar()):
            return jsonify(error="La grabación ya no está disponible."), 404
        try:
            datos = eventos.listar(sesion,nombre) if eventos else {'disponible': False, 'eventos': [], 'total': 0}
        except OSError:
            return jsonify(error="No se pueden consultar los eventos."), 503
        respuesta = jsonify(datos)
        respuesta.headers['Cache-Control'] = 'no-store'
        return respuesta

    @rutas.get("/api/grabaciones")
    def listar():
        try:
            fecha, sesion, pagina = filtros_consulta()
        except ValueError:
            return jsonify(error="Filtro o pagina no valido."), 400
        todos = catalogo.listar()
        sesiones = sorted({v["sesion"] for v in todos if not fecha or v["fecha"] == fecha}, reverse=True)
        filtrados = [v for v in todos if (not fecha or v["fecha"] == fecha)
                     and (not sesion or v["sesion"] == sesion)]
        paginas = max(1, (len(filtrados) + ARCHIVOS_POR_PAGINA - 1) // ARCHIVOS_POR_PAGINA)
        pagina = min(pagina, paginas)
        inicio = (pagina - 1) * ARCHIVOS_POR_PAGINA
        items = filtrados[inicio:inicio + ARCHIVOS_POR_PAGINA]
        for item in items:
            enlaces_video(item, preparador)
        respuesta = jsonify(items=items, total=len(filtrados), pagina=pagina,
                            paginas=paginas, sesiones=sesiones)
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @rutas.route("/grabaciones/<sesion>/<nombre>", methods=["GET", "HEAD"])
    def video(sesion, nombre):
        try:
            archivo, tamano = catalogo.abrir(sesion, nombre)
        except BlockingIOError:
            return jsonify(error="Esta grabacion sigue en curso. Estara disponible al cerrarse."), 409
        except OSError:
            abort(404, description="La grabacion ya no esta disponible.")
        if (preparador is not None and request.args.get("descargar") != "1"
                and not preparador.preparado(sesion, nombre)):
            archivo.close()
            return jsonify(error="Preparando el indice para reproduccion rapida. Actualiza la lista en unos segundos."), 425
        return responder_video(archivo, tamano, f"{sesion}_{nombre}")

    return rutas
