"""Configuracion sin acceso al hardware."""
from dataclasses import dataclass
from pathlib import Path
import argparse
RAIZ = Path(__file__).resolve().parent.parent

def entero_positivo(texto):
    valor = int(texto)
    if valor <= 0:
        raise argparse.ArgumentTypeError("Usa un entero mayor que cero.")
    return valor

@dataclass(frozen=True)
class Configuracion:
    carpeta: Path = RAIZ / "grabaciones"
    segmentos: int = 3600
    reserva_mb: int = 1024
    objetivo_mb: int | None = None
    duracion: int | None = None
    sin_grabar: bool = False

def leer_configuracion(argv=None):
    parser = argparse.ArgumentParser(description="Directo y grabacion de PiCameraRecorder")
    parser.add_argument("--segmentos", type=entero_positivo, default=3600)
    parser.add_argument("--carpeta", type=Path, default=RAIZ / "grabaciones")
    parser.add_argument("--reserva-mb", type=entero_positivo, default=1024)
    parser.add_argument("--objetivo-mb", type=entero_positivo, help="Espacio a recuperar; por defecto al menos 2 GiB y el doble de la reserva.")
    parser.add_argument("--duracion", type=entero_positivo)
    parser.add_argument("--sin-grabar", action="store_true")
    args = parser.parse_args(argv)
    if args.objetivo_mb is not None and args.objetivo_mb <= args.reserva_mb:
        parser.error("--objetivo-mb debe superar --reserva-mb")
    return Configuracion(**vars(args))
