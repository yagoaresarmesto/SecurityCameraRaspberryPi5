"""Lecturas del sistema Linux; un dato no disponible no interrumpe la cámara."""
from pathlib import Path
import math


def leer_numero(ruta, divisor=1):
    try:
        valor = float(Path(ruta).read_text().split()[0]) / divisor
        return round(valor, 1) if math.isfinite(valor) and valor >= 0 else None
    except (OSError, ValueError, IndexError):
        return None


def estado_sistema():
    return {
        "temperatura_cpu_c": leer_numero("/sys/class/thermal/thermal_zone0/temp", 1000),
        "encendida_segundos": leer_numero("/proc/uptime"),
    }
