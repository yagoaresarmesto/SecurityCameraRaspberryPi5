import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch
from picamera_recorder.catalogo import CatalogoGrabaciones
from picamera_recorder.optimizacion import OptimizadorGrabaciones, indice_al_principio
from picamera_recorder.rutas_grabaciones import crear_rutas_grabaciones
from flask import Flask


class OptimizacionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sesion = self.root / '2026-10-21_12-00-00_1234abcd'
        self.sesion.mkdir()
        self.video = self.sesion / 'video_00000.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=10',
            '-t', '2', '-c:v', 'libx264', '-g', '10', '-movflags', '+frag_keyframe+empty_moov+default_base_moof', str(self.video)], check=True, timeout=20)
        self.catalogo = CatalogoGrabaciones(self.root)
        self.opt = OptimizadorGrabaciones(self.catalogo, RLock(), reserva_bytes=1)

    def hash_video(self):
        return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(self.video),
            '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], timeout=20)

    def test_copy_preserves_video_and_age(self):
        original_hash = self.hash_video()
        os.utime(self.video, ns=(1234567890000000, 1234567890000000))
        age = self.video.stat().st_mtime_ns
        self.assertFalse(self.opt.preparado(self.sesion.name, self.video.name))
        self.assertTrue(self.opt.preparar(self.sesion.name, self.video.name))
        self.assertTrue(self.opt.preparado(self.sesion.name, self.video.name))
        self.assertEqual(self.hash_video(), original_hash)
        self.assertEqual(self.video.stat().st_mtime_ns, age)
        self.assertFalse(self.opt.preparar(self.sesion.name, self.video.name))
        self.assertEqual(list(self.sesion.glob('.preparando*')), [])

    def test_low_space_preserves_original(self):
        original = self.video.read_bytes()
        with patch('picamera_recorder.optimizacion.disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaises(RuntimeError): self.opt.preparar(self.sesion.name, self.video.name)
        self.assertEqual(self.video.read_bytes(), original)

    def test_failure_preserves_original_and_removes_temp(self):
        original = self.video.read_bytes()
        with patch.object(self.opt, '_comando', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError): self.opt.preparar(self.sesion.name, self.video.name)
        self.assertEqual(self.video.read_bytes(), original)
        self.assertEqual(list(self.sesion.glob('.preparando*')), [])

    def test_active_not_touched(self):
        self.catalogo.sesion_activa = lambda: self.sesion
        with self.assertRaises(BlockingIOError): self.opt.preparar(self.sesion.name, self.video.name)

    def test_http_preparing_then_ready(self):
        app = Flask(__name__)
        app.register_blueprint(crear_rutas_grabaciones(self.catalogo, self.opt))
        client = app.test_client()
        url = '/grabaciones/' + self.sesion.name + '/' + self.video.name
        with client.get('/api/grabaciones') as r:
            self.assertTrue(r.json['items'][0]['preparando'])
            self.assertNotIn('url', r.json['items'][0])
        with client.get(url) as r: self.assertEqual(r.status_code, 425)
        with client.head(url + '?descargar=1') as r: self.assertEqual(r.status_code, 200)
        self.opt.preparar(self.sesion.name, self.video.name)
        with client.get('/api/grabaciones') as r:
            self.assertFalse(r.json['items'][0]['preparando'])
            self.assertIn('url', r.json['items'][0])
        with client.get(url, headers={'Range':'bytes=0-63'}) as r: self.assertEqual(r.status_code, 206)
