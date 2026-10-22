"""Prepara MP4 cerrados para web sin recodificar. Una tarea en segundo plano."""
import json
import os
import struct
import subprocess
from shutil import disk_usage
from threading import Event, Thread
from time import monotonic
from uuid import uuid4


def indice_al_principio(archivo):
    """MOOV completo antes de los datos y sin MVEX (MP4 fragmentado)."""
    archivo.seek(0, 2)
    total = archivo.tell()
    position = 0
    while position + 8 <= total:
        archivo.seek(position)
        header = archivo.read(8)
        size, kind = struct.unpack('>I4s', header)
        header_size = 8
        if size == 1:
            extended = archivo.read(8)
            if len(extended) != 8: return False
            size = struct.unpack('>Q', extended)[0]
            header_size = 16
        if size < header_size or position + size > total: return False
        if kind in (b'mdat', b'moof'): return False
        if kind == b'moov':
            child, end = position + header_size, position + size
            while child + 8 <= end:
                archivo.seek(child)
                length, tag = struct.unpack('>I4s', archivo.read(8))
                if tag == b'mvex' or length < 8 or child + length > end: return False
                child += length
            return child == end
        position += size
    return False


class OptimizadorGrabaciones:
    def __init__(self, catalogo, bloqueo, reserva_bytes=2*1024**3, permitido=lambda: True):
        self.catalogo = catalogo
        self.bloqueo = bloqueo
        self.reserva_bytes = reserva_bytes
        self.parar = Event()
        self.hilo = None
        self.errores = {}
        self.cache = {}
        self.reintentos = {}
        self.permitido = permitido

    def preparado(self, sesion, nombre):
        try:
            archivo, _ = self.catalogo.abrir(sesion, nombre)
            with archivo:
                info = os.fstat(archivo.fileno())
                key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if key not in self.cache:
                    if len(self.cache) > 2000: self.cache.clear()
                    self.cache[key] = indice_al_principio(archivo)
                return self.cache[key]
        except OSError:
            return False

    def iniciar(self):
        self.hilo = Thread(target=self._bucle, name='preparar-mp4', daemon=True)
        self.hilo.start()

    def detener(self):
        self.parar.set()
        if self.hilo is not None:
            self.hilo.join(timeout=10)

    def _comando(self, args, pass_fds=()):
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              pass_fds=pass_fds) as process:
            deadline = monotonic() + 300
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=.25)
                    if process.returncode:
                        raise RuntimeError(stderr.decode(errors='replace')[-500:])
                    return stdout
                except subprocess.TimeoutExpired:
                    if self.parar.is_set() or monotonic() >= deadline:
                        process.terminate()
                        try: process.communicate(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise RuntimeError('Preparacion interrumpida; original conservado.')

    def preparar(self, sesion, nombre):
        archivo, size = self.catalogo.abrir(sesion, nombre)
        with archivo:
            if indice_al_principio(archivo): return False
            original = os.fstat(archivo.fileno())
            if disk_usage(self.catalogo.carpeta).free < size + self.reserva_bytes:
                raise RuntimeError('Falta espacio temporal para preparar este MP4.')
            fd = self.catalogo.abrir_directorio_sesion(sesion)
            temporal = '.preparando_' + uuid4().hex + '.mp4'
            try:
                output_fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                os.close(output_fd)
                source = f'/proc/self/fd/{archivo.fileno()}'
                target = f'/proc/self/fd/{fd}/{temporal}'
                self._comando(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', source,
                    '-map', '0:v:0', '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', target],
                    pass_fds=(archivo.fileno(), fd))
                def sondear(path):
                    return json.loads(self._comando(['ffprobe', '-v', 'error', '-show_entries',
                        'format=duration:stream=codec_name,width,height', '-of', 'json', path],
                        pass_fds=(archivo.fileno(), fd)))
                antes, despues = sondear(source), sondear(target)
                if antes['streams'] != despues['streams'] or abs(float(antes['format']['duration']) - float(despues['format']['duration'])) > .15:
                    raise RuntimeError('La comprobacion del MP4 no coincide; original conservado.')
                check_fd = os.open(temporal, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                with os.fdopen(check_fd, 'rb') as check:
                    if not indice_al_principio(check): raise RuntimeError('No se pudo crear el indice web.')
                    os.fsync(check.fileno())
                with self.bloqueo:
                    actual = os.stat(nombre, dir_fd=fd, follow_symlinks=False)
                    if (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns) != (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns):
                        raise RuntimeError('El archivo cambio durante la preparacion.')
                    os.utime(temporal, ns=(original.st_atime_ns, original.st_mtime_ns), dir_fd=fd, follow_symlinks=False)
                    os.replace(temporal, nombre, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
                print(f'MP4 preparado para web: {sesion}/{nombre}', flush=True)
                return True
            finally:
                try: os.unlink(temporal, dir_fd=fd)
                except FileNotFoundError: pass
                os.close(fd)

    def _bucle(self):
        while not self.parar.is_set():
            if not self.permitido():
                self.parar.wait(10)
                continue
            try:
                for item in self.catalogo.listar():
                    if self.parar.is_set(): return
                    key = (item['sesion'], item['archivo'])
                    if item['en_curso'] or self.preparado(*key) or monotonic() < self.reintentos.get(key, 0): continue
                    try:
                        self.preparar(*key)
                        self.errores.pop(key, None)
                    except Exception as error:
                        self.errores[key] = 'No se pudo preparar. Puedes descargar el original.'
                        self.reintentos[key] = monotonic() + 120
                        print(f'Preparacion MP4: {key}: {error}', flush=True)
            except OSError as error:
                print(f'Catalogo MP4: {error}', flush=True)
            self.parar.wait(10)
