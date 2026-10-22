import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from picamera_recorder.app import crear_app
from picamera_recorder.catalogo import CatalogoGrabaciones


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        servicio = SimpleNamespace(
            catalogo=CatalogoGrabaciones(Path(self.tmp.name)),
            optimizador=None,
            estado=lambda: {'grabando': False, 'error': None},
            directo=lambda: iter([b'--frame\r\n']),
        )
        self.client = crear_app(servicio).test_client()

    def test_page_renders_components_and_assets(self):
        with self.client.get('/') as response:
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            for value in ['id="stream"', 'id="biblioteca"', 'id="recording-video"',
                          'id="record-card"', 'type="module"', '/static/css/panel.css']:
                self.assertIn(value, text)
            self.assertNotIn('<style>', text)

    def test_static_modules_and_styles_are_served(self):
        for path, mimetype in [('css/panel.css', 'text/css'),
                              ('js/utilidades.js', 'javascript'),
                              ('js/panel.js', 'javascript'),
                              ('js/grabaciones.js', 'javascript')]:
            with self.subTest(path=path), self.client.get('/static/' + path) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn(mimetype, response.mimetype)

    def test_existing_routes_keep_their_contract(self):
        with self.client.get('/estado') as response:
            self.assertEqual(response.json['grabando'], False)
        with self.client.get('/api/grabaciones') as response:
            self.assertEqual(response.json['items'], [])
            self.assertEqual(response.json['paginas'], 1)
        with self.client.get('/directo') as response:
            self.assertIn('multipart/x-mixed-replace', response.content_type)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
