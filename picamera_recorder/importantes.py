"""Marcas persistentes junto al MP4, consultadas sin seguir enlaces."""
import os
import stat


class GrabacionProtegida(Exception):
    """Hay que retirar la estrella antes de eliminar el vídeo."""


def nombre_marca(nombre):
    return '.' + nombre + '.importante'


def es_importante(fd, nombre):
    try:
        os.stat(nombre_marca(nombre), dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    # Cualquier entrada protege; un error de lectura nunca autoriza un borrado.
    return True


def guardar_importancia(fd, nombre, importante):
    marca = nombre_marca(nombre)
    if importante:
        try:
            nuevo = os.open(marca, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=fd)
        except FileExistsError:
            return
        try:
            os.fsync(nuevo)
        finally:
            os.close(nuevo)
    else:
        try:
            info = os.stat(marca, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OSError('Marca de protección no válida.')
        os.unlink(marca, dir_fd=fd)
    os.fsync(fd)
