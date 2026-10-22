"""Primer paso: comprobar la camara desde Python, sin grabar."""

import argparse

from picamera2 import Picamera2
from foto import capturar_foto


def main():
    parser = argparse.ArgumentParser(description="PiCameraRecorder: primeros pasos")
    parser.add_argument("--foto", action="store_true", help="Guardar una foto en capturas/")
    args = parser.parse_args()
    if args.foto:
        capturar_foto()
        return

    # Consultar las camaras disponibles no inicia una grabacion.
    cameras = Picamera2.global_camera_info()
    if not cameras:
        raise SystemExit("No se detecta ninguna camara. Revisa la conexion.")
    for camera in cameras:
        print(f"Camara {camera['Num']}: {camera['Model']}")
    print("Camara disponible. Para iniciar la web: .venv/bin/python -m picamera_recorder")


if __name__ == "__main__":
    main()
