"""Captura una foto y libera la camara al terminar."""

from datetime import datetime
from pathlib import Path
from time import sleep

from picamera2 import Picamera2


def capturar_foto():
    carpeta = Path(__file__).resolve().parent / "capturas"
    carpeta.mkdir(exist_ok=True)
    destino = carpeta / datetime.now().strftime("foto_%Y%m%d_%H%M%S_%f.jpg")

    # El bloque with cierra la camara incluso si ocurre un error.
    with Picamera2() as camara:
        configuracion = camara.create_still_configuration(main={"size": (1920, 1080)})
        camara.configure(configuracion)
        camara.start()
        # Damos tiempo al enfoque automatico y a la exposicion.
        sleep(3)
        camara.capture_file(str(destino))

    print(f"Foto guardada: {destino}")
    return destino


if __name__ == "__main__":
    capturar_foto()
