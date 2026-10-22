"""Prueba real: directo, varios MP4, reinicio y espacio insuficiente."""
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work" / time.strftime("prueba_segmentos_%Y%m%d_%H%M%S")
BASE.mkdir(parents=True)
URL = "http://127.0.0.1:8000"


def estado():
    with urlopen(URL + "/estado", timeout=3) as r:
        return json.load(r)


def imagenes():
    with urlopen(URL + "/directo", timeout=6) as r:
        assert "multipart/x-mixed-replace" in r.headers["Content-Type"]
        datos = b""
        for _ in range(200):
            datos += r.read(4096)
            inicio = datos.find(b"\xff\xd8")
            fin = datos.find(b"\xff\xd9", inicio + 2) if inicio >= 0 else -1
            if fin >= 0:
                foto = Image.open(io.BytesIO(datos[inicio:fin+2]))
                foto.load()
                assert foto.size == (1280, 720)
                return
        raise AssertionError("No se recibe una imagen JPEG completa")


def ejecutar(nombre, opciones, verificar):
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", 8000)) != 0, "El puerto 8000 ya esta ocupado"
    with (BASE / (nombre + ".log")).open("w") as log:
        p = subprocess.Popen([sys.executable, "web.py", *opciones], cwd=ROOT,
                             stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                if p.poll() is not None:
                    raise AssertionError((BASE / (nombre + ".log")).read_text())
                try:
                    datos = estado()
                    break
                except (OSError, ValueError):
                    time.sleep(0.2)
            else:
                raise AssertionError("El servidor no arranca")
            verificar(datos)
            p.wait(timeout=45)
            assert p.returncode == 0, (BASE / (nombre + ".log")).read_text()
        finally:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()


def comprobar_directo(s):
    assert s["grabando"], s
    assert s["segmento_segundos"] == 8, s
    a = s["fotogramas"]
    imagenes()
    imagenes()  # Otro espectador; la camara sigue abierta una sola vez.
    assert estado()["fotogramas"] > a
    print("OK: dos conexiones al directo mientras graba", flush=True)


carpeta = BASE / "videos"
ejecutar("segmentos", ["--segmentos", "8", "--duracion", "27", "--carpeta", str(carpeta)], comprobar_directo)
sesiones = [p for p in carpeta.iterdir() if p.is_dir()]
assert len(sesiones) == 1
videos = sorted(sesiones[0].glob("*.mp4"))
assert len(videos) >= 3, videos
resultados = []
for video in videos:
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height,start_time",
        "-of", "json", str(video)], text=True))
    stream = data["streams"][0]
    assert (stream["codec_name"], stream["width"], stream["height"]) == ("h264", 1280, 720), data
    duracion = float(data["format"]["duration"])
    assert duracion > 0 and duracion < 10, data
    if video != videos[-1]:
        assert 6.5 < duracion < 9.5, data
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"],
                   check=True, timeout=30, stdout=subprocess.DEVNULL)
    resultados.append({"archivo": video.name, "segundos": duracion, "bytes": video.stat().st_size})
    print("OK MP4:", resultados[-1], flush=True)
assert 24 < sum(v["segundos"] for v in resultados) < 30
def huella_video(path):
    # El optimizador puede reorganizar el contenedor, pero no cambiar el video.
    return subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
        "-c", "copy", "-f", "hash", "-hash", "sha256", "-"], timeout=30)


anteriores = {p: huella_video(p) for p in videos}


def reinicio(s):
    assert s["grabando"], s
    imagenes()


ejecutar("reinicio", ["--duracion", "4", "--carpeta", str(carpeta)], reinicio)
assert len([p for p in carpeta.iterdir() if p.is_dir()]) == 2
assert all(huella_video(p) == huella for p, huella in anteriores.items())
print("OK: reinicio crea otra sesion sin sobrescribir videos", flush=True)


def sin_espacio(s):
    assert not s["grabando"] and s["error"] and s["archivos"] == 0, s
    imagenes()
    print("OK: espacio insuficiente impide grabar y conserva el directo", flush=True)


ejecutar("espacio", ["--duracion", "4", "--reserva-mb", "999999999", "--carpeta", str(BASE / "sin_espacio")], sin_espacio)
assert not list((BASE / "sin_espacio").rglob("*.mp4"))
(BASE / "resultado.json").write_text(json.dumps(resultados, indent=2))
print("PRUEBA_COMPLETA:", BASE, flush=True)
