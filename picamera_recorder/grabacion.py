"""Guarda H.264 en MP4 de duracion limitada sin reabrir la camara."""
from datetime import datetime
from pathlib import Path
import fcntl
from time import monotonic
from threading import RLock
from .almacenamiento import AlmacenamientoCircular
from uuid import uuid4

from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput


class Grabador:
    def __init__(self, carpeta, segundos=3600, reserva_mb=1024, objetivo_mb=None):
        self.carpeta = Path(carpeta).resolve()
        self.segundos = segundos
        objetivo_mb = objetivo_mb if objetivo_mb is not None else max(2048, reserva_mb * 2)
        self.almacen = AlmacenamientoCircular(self.carpeta, reserva_mb, objetivo_mb)
        self._bloqueo = None
        self._proxima_comprobacion = 0
        self.bloqueo_almacen = RLock()
        self.encoder = None
        self.sesion = None
        self.error = None
        self.activo = False
        self.libre_mb = None

    def hay_espacio(self):
        try:
            with self.bloqueo_almacen:
                return self.almacen.asegurar_espacio(self.sesion if self.activo else None)
        finally:
            self.libre_mb = self.almacen.libre_mb

    def _liberar_bloqueo(self):
        if self._bloqueo is not None:
            self._bloqueo.close()
            self._bloqueo = None

    def iniciar(self, camara):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        # Una sola grabacion por carpeta: otra ejecucion no puede borrar un MP4
        # que siga abierto en una sesion diferente.
        import os
        fd = os.open(self.carpeta / ".grabacion.lock",
                     os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self._bloqueo = os.fdopen(fd, "a")
        try:
            fcntl.flock(self._bloqueo, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._iniciar(camara)
        except BaseException:
            self._liberar_bloqueo()
            raise
        if not self.activo:
            self._liberar_bloqueo()

    def _iniciar(self, camara):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        try:
            espacio = self.hay_espacio()
        except OSError as error:
            self._fallo(error)
            return
        if not espacio:
            self.error = "Grabacion detenida: no hay videos cerrados suficientes para liberar espacio."
            print(self.error, flush=True)
            return
        nombre = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid4().hex[:8]
        self.sesion = self.carpeta / nombre
        self.sesion.mkdir()
        # El muxer divide en fotogramas clave; cada archivo puede reproducirse solo.
        output = PyavOutput(str(self.sesion / "video_%05d.mp4"), format="segment", options={
            "segment_time": str(self.segundos),
            "segment_list": str(self.sesion / ".segmentos.csv"),
            "segment_list_type": "csv",
            "reset_timestamps": "1",
            "segment_format": "mp4",
            "segment_format_options": "movflags=+frag_keyframe+empty_moov+default_base_moof",
        })
        output.error_callback = self._fallo
        encoder = H264Encoder(bitrate=2_000_000, framerate=15, iperiod=15, repeat=True)
        camara.start_encoder(encoder, output)
        self.encoder = encoder
        self.activo = True
        print(f"Grabando segmentos de {self.segundos}s en {self.sesion}", flush=True)

    def _fallo(self, error):
        # La notificacion llega del codificador: el bucle principal lo detendra.
        self.error = f"Error al guardar el video: {error}"

    def comprobar(self, camara):
        if not self.activo:
            return
        ahora = monotonic()
        if not self.error and ahora < self._proxima_comprobacion:
            return
        self._proxima_comprobacion = ahora + 5
        try:
            if not self.error and not self.hay_espacio():
                self.error = "Grabacion detenida: no hay videos cerrados suficientes para liberar espacio."
        except OSError as error:
            self._fallo(error)
        if self.error:
            print(self.error, flush=True)
            self.detener(camara)

    def detener(self, camara):
        try:
            if self.encoder is not None:
                encoder, self.encoder = self.encoder, None
                try:
                    camara.stop_encoder(encoder)
                finally:
                    self.activo = False
                    print("Archivo actual cerrado. Grabacion detenida.", flush=True)
        finally:
            self._liberar_bloqueo()

    def sesion_en_curso(self):
        # El bloqueo se libera despues de cerrar la salida, incluso en caso de error.
        return self.sesion if self._bloqueo is not None else None

    def estado(self):
        archivos = [a[1] for a in self.almacen.archivos(self.sesion)] if self.sesion else []
        return {
            "borrados_automaticos": self.almacen.borrados,
            "espacio_liberado_mb": self.almacen.bytes_borrados // (1024 * 1024),
            "reserva_mb": self.almacen.reserva // (1024 * 1024),
            "objetivo_mb": self.almacen.objetivo // (1024 * 1024),
            "grabando": self.activo and self.error is None,
            "error": self.error,
            "segmento_segundos": self.segundos,
            "espacio_libre_mb": self.libre_mb,
            "sesion": self.sesion.name if self.sesion else None,
            "archivos": len(archivos),
            "archivo_actual": archivos[-1].name if archivos and self.activo else None,
        }
