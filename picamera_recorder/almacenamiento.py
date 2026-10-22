"""Retencion circular limitada a los MP4 generados por PiCameraRecorder."""
import os
import re
import stat
from pathlib import Path
from shutil import disk_usage
from .importantes import es_importante

SESION = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[0-9a-f]{8}")
VIDEO = re.compile(r"video_(\d{5,})\.mp4")
MIB = 1024 * 1024


class AlmacenamientoCircular:
    def __init__(self, carpeta, reserva_mb=1024, objetivo_mb=2048, medir=None):
        if reserva_mb <= 0 or objetivo_mb <= reserva_mb:
            raise ValueError("El objetivo de espacio debe superar la reserva positiva.")
        self.carpeta = Path(carpeta).resolve()
        self.reserva = reserva_mb * MIB
        self.objetivo = objetivo_mb * MIB
        self._medir = medir or disk_usage
        self.libre_mb = None
        self.borrados = 0
        self.bytes_borrados = 0
        self._limpiando = False

    def _libre(self):
        libre = self._medir(self.carpeta).free
        self.libre_mb = libre // MIB
        return libre

    def archivos(self, sesion):
        """Solo ficheros regulares propios; nunca seguir enlaces simbolicos."""
        if sesion.is_symlink() or not sesion.is_dir():
            return []
        resultado = []
        for archivo in sesion.iterdir():
            match = VIDEO.fullmatch(archivo.name)
            if not match:
                continue
            try:
                info = archivo.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                resultado.append((int(match[1]), archivo, info))
        return sorted(resultado, key=lambda item: item[0])

    def asegurar_espacio(self, sesion_activa=None):
        """El llamante mantiene el bloqueo exclusivo de grabacion de esta carpeta."""
        libre = self._libre()
        if libre < self.reserva:
            self._limpiando = True
        if not self._limpiando:
            return True
        if libre >= self.objetivo:
            self._limpiando = False
            return True

        candidatos = []
        for sesion in self.carpeta.iterdir():
            if not SESION.fullmatch(sesion.name) or sesion.is_symlink() or not sesion.is_dir():
                continue
            archivos = self.archivos(sesion)
            # En la sesion actual solo son borrables los anteriores al ultimo.
            # El muxer cierra un MP4 antes de abrir el siguiente. Si hay una
            # rotacion durante este recorrido, excluimos de mas, nunca de menos.
            if sesion_activa is not None and sesion == sesion_activa:
                archivos = archivos[:-1]
            candidatos.extend(archivos)
        candidatos.sort(key=lambda item: (item[2].st_mtime_ns, str(item[1])))

        raiz_fd = os.open(self.carpeta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for _, archivo, anterior in candidatos:
                if self._libre() >= self.objetivo:
                    self._limpiando = False
                    break
                # Abrir respecto a la raiz y sin seguir enlaces evita salir de
                # grabaciones incluso si se cambia un directorio durante el barrido.
                try:
                    sesion_fd = os.open(archivo.parent.name,
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=raiz_fd)
                except FileNotFoundError:
                    continue
                try:
                    try:
                        actual = os.stat(archivo.name, dir_fd=sesion_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1
                            or (actual.st_dev, actual.st_ino) != (anterior.st_dev, anterior.st_ino)):
                        continue
                    if es_importante(sesion_fd, archivo.name):
                        continue
                    os.unlink(archivo.name, dir_fd=sesion_fd)
                    self.borrados += 1
                    self.bytes_borrados += actual.st_size
                    print(f"Limpieza automatica: eliminado {archivo}", flush=True)
                finally:
                    os.close(sesion_fd)
        finally:
            os.close(raiz_fd)
        libre = self._libre()
        if libre >= self.objetivo:
            self._limpiando = False
        # Si no se alcanza el objetivo pero queda reserva, volver a intentarlo
        # cuando el muxer cierre el siguiente video. Nunca borrar el activo.
        return libre >= self.reserva
