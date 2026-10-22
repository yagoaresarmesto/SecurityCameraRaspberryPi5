"""Catalogo de MP4 locales. Consulta y borrado seguro de grabaciones cerradas."""
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from .almacenamiento import SESION, VIDEO
from .importantes import es_importante, guardar_importancia, GrabacionProtegida


class CatalogoGrabaciones:
    def __init__(self, carpeta, sesion_activa=lambda: None):
        self.carpeta = Path(carpeta).resolve()
        self.sesion_activa = sesion_activa

    def _raiz(self):
        return os.open(self.carpeta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def _activo(self, sesion, nombres):
        actual = self.sesion_activa()
        if actual is not None and Path(actual).name == sesion:
            return max(nombres, key=lambda n: int(VIDEO.fullmatch(n)[1]), default=None)
        return None

    def _entradas(self, fd):
        entradas = []
        for nombre in os.listdir(fd):
            if not VIDEO.fullmatch(nombre):
                continue
            try:
                info = os.stat(nombre, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                entradas.append((nombre, info))
        return entradas

    def _nombres(self, fd):
        return [nombre for nombre, _ in self._entradas(fd)]

    def abrir_directorio_sesion(self, sesion):
        """Devuelve un descriptor de directorio; el llamante debe cerrarlo."""
        if not SESION.fullmatch(sesion):
            raise FileNotFoundError()
        raiz = self._raiz()
        try:
            return os.open(sesion, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=raiz)
        finally:
            os.close(raiz)

    def listar(self):
        resultado = []
        try:
            raiz = self._raiz()
        except FileNotFoundError:
            return []
        try:
            for sesion in os.listdir(raiz):
                if not SESION.fullmatch(sesion):
                    continue
                try:
                    fd = os.open(sesion, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=raiz)
                except (FileNotFoundError, NotADirectoryError, OSError):
                    continue
                try:
                    entradas = self._entradas(fd)
                    activo = self._activo(sesion, [nombre for nombre, _ in entradas])
                    for nombre, info in entradas:
                        resultado.append({'sesion': sesion, 'archivo': nombre,
                            'fecha': sesion[:10], 'bytes': info.st_size,
                            'modificado': datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                            'en_curso': nombre == activo, 'importante': es_importante(fd, nombre)})
                finally:
                    os.close(fd)
        finally:
            os.close(raiz)
        return sorted(resultado, key=lambda v: (v['sesion'], int(VIDEO.fullmatch(v['archivo'])[1])), reverse=True)

    def abrir(self, sesion, nombre):
        if not SESION.fullmatch(sesion) or not VIDEO.fullmatch(nombre):
            raise FileNotFoundError()
        fd = self.abrir_directorio_sesion(sesion)
        try:
            actual = self.sesion_activa()
            if actual is not None and Path(actual).name == sesion:
                nombres = self._nombres(fd)
                ultimo = max((int(VIDEO.fullmatch(n)[1]) for n in nombres), default=-1)
                # Si el muxer rota entre listar y abrir, el nuevo indice tambien
                # queda bloqueado. Solo se sirven indices anteriores al ultimo.
                if int(VIDEO.fullmatch(nombre)[1]) >= ultimo:
                    raise BlockingIOError('El archivo todavia se esta grabando.')
            video = os.open(nombre, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        finally:
            os.close(fd)
        try:
            info = os.fstat(video)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FileNotFoundError()
            return os.fdopen(video, 'rb'), info.st_size
        except BaseException:
            os.close(video)
            raise

    def marcar_importante(self, sesion, nombre, importante, bloqueo):
        """Serializa la marca con el borrado y permite proteger el archivo activo."""
        if not SESION.fullmatch(sesion) or not VIDEO.fullmatch(nombre):
            raise FileNotFoundError()
        with bloqueo:
            fd = self.abrir_directorio_sesion(sesion)
            try:
                info = os.stat(nombre, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise FileNotFoundError()
                guardar_importancia(fd, nombre, importante)
            finally:
                os.close(fd)

    def eliminar(self, sesion, nombre, bloqueo):
        """Borra un MP4 cerrado bajo el mismo bloqueo que retención y optimización."""
        if not SESION.fullmatch(sesion) or not VIDEO.fullmatch(nombre):
            raise FileNotFoundError()
        with bloqueo:
            fd = self.abrir_directorio_sesion(sesion)
            try:
                actual = self.sesion_activa()
                if actual is not None and Path(actual).name == sesion:
                    ultimo = max((int(VIDEO.fullmatch(n)[1]) for n in self._nombres(fd)), default=-1)
                    if int(VIDEO.fullmatch(nombre)[1]) >= ultimo:
                        raise BlockingIOError('El archivo sigue en curso.')
                info = os.stat(nombre, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise FileNotFoundError()
                if es_importante(fd, nombre):
                    raise GrabacionProtegida()
                os.unlink(nombre, dir_fd=fd)
                return info.st_size
            finally:
                os.close(fd)
