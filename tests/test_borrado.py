import os
import tempfile
import unittest
from pathlib import Path
from threading import Lock
from flask import Flask
from picamera_recorder.catalogo import CatalogoGrabaciones
from picamera_recorder.rutas_grabaciones import crear_rutas_grabaciones

SESION = '2026-10-21_12-00-00_1234abcd'
class BorradoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / SESION
        self.folder.mkdir()
        self.video = self.folder / 'video_00000.mp4'
        self.video.write_bytes(b'video de prueba')
        self.active = None
        self.cat = CatalogoGrabaciones(self.root, lambda:self.active)
        app = Flask(__name__)
        app.register_blueprint(crear_rutas_grabaciones(self.cat))
        self.client = app.test_client()
        self.url = '/api/grabaciones/' + SESION + '/video_00000.mp4'
    def borrar(self, **headers):
        return self.client.delete(self.url, headers={'X-PiCameraRecorder':'1', **headers})
    def test_borra_cerrado_y_repetir_devuelve_404(self):
        response = self.borrar()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['bytes_liberados'],15)
        self.assertFalse(self.video.exists())
        self.assertEqual(self.borrar().status_code,404)
        self.assertEqual(self.client.get('/api/grabaciones').json['total'],0)
    def test_protege_actual_y_permite_anterior(self):
        self.active = self.folder
        self.assertEqual(self.borrar().status_code,409)
        self.assertTrue(self.video.exists())
        current=self.folder/'video_00001.mp4'
        current.write_bytes(b'actual')
        self.assertEqual(self.borrar().status_code,200)
        self.assertEqual(current.read_bytes(),b'actual')
    def test_exige_cabecera_y_origen(self):
        self.assertEqual(self.client.delete(self.url).status_code,403)
        self.assertEqual(self.borrar(Origin='http://otro.example').status_code,403)
        self.assertEqual(self.borrar(**{'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertTrue(self.video.exists())
        self.assertEqual(self.borrar(Origin='http://localhost').status_code,200)
    def test_no_borra_enlaces_ni_nombres_ajenos(self):
        exterior=self.root/'personal.mp4'
        exterior.write_bytes(b'conservar')
        self.video.unlink()
        self.video.symlink_to(exterior)
        self.assertEqual(self.borrar().status_code,404)
        self.video.unlink()
        os.link(exterior,self.video)
        self.assertEqual(self.borrar().status_code,404)
        self.assertEqual(exterior.read_bytes(),b'conservar')
        with self.assertRaises(FileNotFoundError):
            self.cat.eliminar(SESION,'../personal.mp4',Lock())
    def test_no_sigue_directorio_enlazado(self):
        self.video.unlink()
        self.folder.rmdir()
        exterior=self.root/'exterior'
        exterior.mkdir()
        target=exterior/'video_00000.mp4'
        target.write_bytes(b'conservar')
        self.folder.symlink_to(exterior,target_is_directory=True)
        self.assertNotEqual(self.borrar().status_code,200)
        self.assertTrue(target.exists())
