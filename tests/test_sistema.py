import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from picamera_recorder.sistema import leer_numero, estado_sistema

class SistemaTests(unittest.TestCase):
    def test_lectura_y_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / 'dato'
            ruta.write_text('48500')
            self.assertEqual(leer_numero(ruta, 1000), 48.5)
            ruta.write_text('12345.67 999.0')
            self.assertEqual(leer_numero(ruta), 12345.7)
    def test_datos_invalidos_y_ausentes(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / 'dato'
            self.assertIsNone(leer_numero(ruta))
            for dato in ('', 'error', 'nan', 'inf', '-5'):
                ruta.write_text(dato)
                self.assertIsNone(leer_numero(ruta))
    def test_sistema_degrada_sin_ficheros(self):
        with patch('picamera_recorder.sistema.leer_numero', return_value=None):
            self.assertEqual(estado_sistema(), {'temperatura_cpu_c': None, 'encendida_segundos': None})
