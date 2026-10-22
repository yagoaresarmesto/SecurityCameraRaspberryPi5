"""Une configuracion, servicio y servidor. Gestiona las senales."""
import signal
from threading import Event
from time import monotonic
from werkzeug.serving import make_server
from .app import crear_app
from .config import leer_configuracion
from .servicio import ServicioCamara

def main(argv=None):
    config = leer_configuracion(argv)
    parar = Event()
    anteriores = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        anteriores[sig] = signal.signal(sig, lambda *_: parar.set())
    try:
        servicio = ServicioCamara(config)
        app = crear_app(servicio)
        with make_server("0.0.0.0", 8000, app, threaded=True) as servidor:
            servidor.timeout = 0.5
            with servicio:
                inicio = monotonic()
                print("PiCameraRecorder: puerto 8000 | Ctrl+C para detener", flush=True)
                while not parar.is_set():
                    if config.duracion and monotonic() - inicio >= config.duracion:
                        break
                    servicio.comprobar()
                    servidor.handle_request()
    finally:
        for sig, anterior in anteriores.items():
            signal.signal(sig, anterior)
