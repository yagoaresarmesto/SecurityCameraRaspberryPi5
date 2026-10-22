"""Service Layer: unico propietario de la camara y sus salidas."""
from contextlib import ExitStack
from .grabacion import Grabador
from .streaming import Fotogramas
from .movimiento import Movimiento
from .catalogo import CatalogoGrabaciones
from .optimizacion import OptimizadorGrabaciones

class ServicioCamara:
    def __init__(self, config):
        self.config = config
        self.salida = Fotogramas()
        self.grabador = Grabador(config.carpeta, config.segmentos, config.reserva_mb, config.objetivo_mb)
        self.catalogo = CatalogoGrabaciones(self.grabador.carpeta, self.grabador.sesion_en_curso)
        self.optimizador = OptimizadorGrabaciones(self.catalogo, self.grabador.bloqueo_almacen,
            self.grabador.almacen.objetivo, lambda: self.grabador.sesion_en_curso() is not None)
        self.movimiento = Movimiento(self.salida, self.grabador, self.catalogo)
        self._recursos = None
        self._camara = None

    def __enter__(self):
        from picamera2 import Picamera2
        from picamera2.encoders import JpegEncoder
        from picamera2.outputs import FileOutput
        recursos = ExitStack()
        try:
            camara = recursos.enter_context(Picamera2())
            self._camara = camara
            camara.configure(camara.create_video_configuration(
                main={"size": (1280, 720)}, controls={"FrameRate": 15}, buffer_count=6))
            jpeg = JpegEncoder()
            camara.start_encoder(jpeg, FileOutput(self.salida))
            recursos.callback(camara.stop_encoder, jpeg)
            recursos.callback(self.grabador.detener, camara)
            if not self.config.sin_grabar:
                self.grabador.iniciar(camara)
            camara.start()
            recursos.callback(camara.stop)
            recursos.callback(self._cerrar_directo)
            if self.grabador.activo:
                self.optimizador.iniciar()
                recursos.callback(self.optimizador.detener)
            self.movimiento.iniciar()
            recursos.callback(self.movimiento.detener)
            self._recursos = recursos.pop_all()
            return self
        except BaseException:
            self._cerrar_directo()
            recursos.close()
            self._camara = None
            raise

    def _cerrar_directo(self):
        with self.salida.condition:
            self.salida.stopped = True
            self.salida.condition.notify_all()

    def __exit__(self, *exc):
        try:
            if self._recursos is not None:
                self._recursos.close()
        finally:
            self._recursos = None
            self._camara = None
        print("Camara liberada. Fin.", flush=True)

    def comprobar(self):
        self.grabador.comprobar(self._camara)

    def estado(self):
        return dict(self.grabador.estado(), fotogramas=self.salida.sequence,
                    solo_directo=self.config.sin_grabar, movimiento=self.movimiento.estado())

    def directo(self):
        return self.salida.generar()
