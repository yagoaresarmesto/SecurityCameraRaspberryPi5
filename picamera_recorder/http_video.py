"""Entrega de archivos por bloques y rangos HTTP para reproducir y descargar."""
import re
from dataclasses import dataclass

from flask import Response, request

TAMANO_BLOQUE = 256 * 1024


@dataclass(frozen=True)
class RangoVideo:
    inicio: int
    fin: int
    estado: int

    @property
    def longitud(self):
        return max(0, self.fin - self.inicio + 1)


def interpretar_rango(tamano, cabecera=None):
    """Admite un rango cerrado, abierto o sufijo; ValueError si no es valido."""
    if not cabecera:
        return RangoVideo(0, tamano - 1, 200)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", cabecera.strip()) if len(cabecera) <= 128 else None
    if match is None or not any(match.groups()) or tamano <= 0:
        raise ValueError("Rango no valido")
    primero, ultimo = match.groups()
    if primero:
        inicio = int(primero)
        fin = min(int(ultimo), tamano - 1) if ultimo else tamano - 1
    else:
        cantidad = int(ultimo)
        if cantidad <= 0:
            raise ValueError("Sufijo no valido")
        inicio, fin = max(0, tamano - cantidad), tamano - 1
    if not 0 <= inicio <= fin < tamano:
        raise ValueError("Rango fuera del archivo")
    return RangoVideo(inicio, fin, 206)


def leer_bloques(archivo, rango):
    try:
        archivo.seek(rango.inicio)
        pendientes = rango.longitud
        while pendientes:
            bloque = archivo.read(min(TAMANO_BLOQUE, pendientes))
            if not bloque:
                break
            pendientes -= len(bloque)
            yield bloque
    finally:
        archivo.close()


def responder_video(archivo, tamano, nombre_descarga):
    """Asume un nombre validado por el catalogo y toma propiedad del descriptor."""
    try:
        rango = interpretar_rango(tamano, request.headers.get("Range"))
    except ValueError:
        archivo.close()
        return Response(status=416, headers={
            "Content-Range": f"bytes */{tamano}", "Cache-Control": "no-store"})
    disposicion = "attachment" if request.args.get("descargar") == "1" else "inline"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(rango.longitud),
        "Content-Disposition": f'{disposicion}; filename="{nombre_descarga}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if rango.estado == 206:
        headers["Content-Range"] = f"bytes {rango.inicio}-{rango.fin}/{tamano}"
    contenido = leer_bloques(archivo, rango) if request.method != "HEAD" else None
    respuesta = Response(contenido, status=rango.estado, mimetype="video/mp4", headers=headers)
    respuesta.call_on_close(archivo.close)
    if request.method == "HEAD":
        archivo.close()
    return respuesta
