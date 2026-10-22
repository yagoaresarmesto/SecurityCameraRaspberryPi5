import os
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from picamera_recorder.almacenamiento import AlmacenamientoCircular, MIB
from picamera_recorder.catalogo import CatalogoGrabaciones
from picamera_recorder.importantes import GrabacionProtegida, nombre_marca
from picamera_recorder.rutas_grabaciones import crear_rutas_grabaciones

SESION = '2026-10-22_12-00-00_1234abcd'
VIDEO = 'video_00000.mp4'


class ImportantesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / SESION
        self.folder.mkdir()
        self.video = self.folder / VIDEO
        self.video.write_bytes(b'conservar')
        self.lock = RLock()
        self.cat = CatalogoGrabaciones(self.root)
        app = Flask(__name__)
        app.register_blueprint(crear_rutas_grabaciones(self.cat))
        self.client = app.test_client()
        self.url = '/api/grabaciones/' + SESION + '/' + VIDEO + '/importante'

    def marcar(self, value, **headers):
        return self.client.put(self.url, json={'importante': value},
                               headers={'X-PiCameraRecorder': '1', **headers})

    def test_persistencia_idempotencia_y_borrado_manual(self):
        self.assertEqual(self.marcar(True).status_code, 200)
        self.assertEqual(self.marcar(True).status_code, 200)
        nuevo = CatalogoGrabaciones(self.root)
        self.assertTrue(nuevo.listar()[0]['importante'])
        with self.assertRaises(GrabacionProtegida):
            nuevo.eliminar(SESION, VIDEO, self.lock)
        response = self.client.delete(self.url.removesuffix('/importante'), headers={'X-PiCameraRecorder': '1'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.video.read_bytes(), b'conservar')
        self.assertEqual(self.marcar(False).status_code, 200)
        self.assertEqual(self.marcar(False).status_code, 200)
        nuevo.eliminar(SESION, VIDEO, self.lock)
        self.assertFalse(self.video.exists())

    def test_actual_protegido_no_hereda_al_siguiente(self):
        self.cat.sesion_activa = lambda: self.folder
        self.assertEqual(self.marcar(True).status_code, 200)
        (self.folder / 'video_00001.mp4').write_bytes(b'nuevo')
        items = self.cat.listar()
        self.assertTrue(items[0]['en_curso'])
        self.assertFalse(items[0]['importante'])
        self.assertTrue(items[1]['importante'])

    def test_validacion_y_origen(self):
        self.assertEqual(self.client.put(self.url, json={'importante': True}).status_code, 403)
        self.assertEqual(self.marcar(True, Origin='http://ajeno.example').status_code, 403)
        self.assertEqual(self.marcar(True, **{'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        for invalid in [1, 'true', None, [], {}]:
            self.assertEqual(self.marcar(invalid).status_code, 400)
        self.video.unlink()
        self.assertEqual(self.marcar(True).status_code, 404)
        self.assertFalse((self.folder / nombre_marca(VIDEO)).exists())

    def test_no_sigue_enlaces(self):
        exterior = self.root / 'personal'
        exterior.write_bytes(b'fuera')
        self.video.unlink()
        self.video.symlink_to(exterior)
        self.assertEqual(self.marcar(True).status_code, 404)
        self.video.unlink()
        self.video.write_bytes(b'conservar')
        marca = self.folder / nombre_marca(VIDEO)
        marca.symlink_to(exterior)
        self.assertEqual(self.marcar(True).status_code, 200)
        self.assertTrue(self.cat.listar()[0]['importante'])
        self.assertEqual(self.marcar(False).status_code, 500)
        self.assertEqual(exterior.read_bytes(), b'fuera')

    def almacen(self):
        iniciales = list(self.folder.glob('*.mp4'))
        return AlmacenamientoCircular(self.root, 10, 20, medir=lambda _: SimpleNamespace(
            free=(5 + 20 * sum(not p.exists() for p in iniciales)) * MIB))

    def test_limpieza_omite_importante_y_borra_otro(self):
        os.utime(self.video, (1, 1))
        otro = self.folder / 'video_00001.mp4'
        otro.write_bytes(b'borrable')
        self.cat.marcar_importante(SESION, VIDEO, True, self.lock)
        almacen = self.almacen()
        self.assertTrue(almacen.asegurar_espacio())
        self.assertTrue(self.video.exists())
        self.assertFalse(otro.exists())
        self.assertEqual(almacen.borrados, 1)

    def test_solo_importantes_no_recupera_reserva(self):
        self.cat.marcar_importante(SESION, VIDEO, True, self.lock)
        almacen = self.almacen()
        self.assertFalse(almacen.asegurar_espacio())
        self.assertTrue(self.video.exists())
        self.assertEqual(almacen.borrados, 0)
        self.cat.marcar_importante(SESION, VIDEO, False, self.lock)
        self.assertTrue(almacen.asegurar_espacio())
        self.assertFalse(self.video.exists())

    def test_marca_y_borrado_usan_el_bloqueo_compartido(self):
        with patch('picamera_recorder.catalogo.guardar_importancia') as guardar:
            guardar.side_effect = lambda *args: self.assertTrue(self.lock._is_owned())
            self.cat.marcar_importante(SESION, VIDEO, True, self.lock)
        with patch('picamera_recorder.catalogo.es_importante') as consultar:
            consultar.side_effect = lambda *args: (self.assertTrue(self.lock._is_owned()) or True)
            with self.assertRaises(GrabacionProtegida):
                self.cat.eliminar(SESION, VIDEO, self.lock)

    def test_error_de_consulta_nunca_autoriza_borrar(self):
        with patch('picamera_recorder.almacenamiento.es_importante', side_effect=OSError('lectura')):
            with self.assertRaises(OSError):
                self.almacen().asegurar_espacio()
        self.assertTrue(self.video.exists())
