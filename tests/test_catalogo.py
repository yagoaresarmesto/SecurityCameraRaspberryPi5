import os
import tempfile
import unittest
from pathlib import Path
from flask import Flask
from picamera_recorder.catalogo import CatalogoGrabaciones
from picamera_recorder.rutas_grabaciones import crear_rutas_grabaciones

S = '2026-10-21_12-00-00_1234abcd'
V = 'video_00000.mp4'


class CatalogoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session = self.root / S
        self.session.mkdir()
        self.video = self.session / V
        self.video.write_bytes(b'0123456789')
        self.active = None
        self.catalog = CatalogoGrabaciones(self.root, lambda: self.active)
        self.app = Flask(__name__)
        self.app.register_blueprint(crear_rutas_grabaciones(self.catalog))
        self.client = self.app.test_client()
        self.url = '/grabaciones/' + S + '/' + V

    def get(self, url, **kwargs):
        response = self.client.get(url, **kwargs)
        self.addCleanup(response.close)
        return response

    def test_catalog_and_download(self):
        data = self.get('/api/grabaciones').json
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['items'][0]['bytes'], 10)
        self.assertFalse(data['items'][0]['en_curso'])
        self.assertEqual(data['items'][0]['url'], self.url)
        r = self.get(self.url + '?descargar=1')
        self.assertEqual(r.data, b'0123456789')
        self.assertEqual(r.mimetype, 'video/mp4')
        self.assertIn('attachment;', r.headers['Content-Disposition'])

    def test_active_denied_then_available_when_closed(self):
        self.active = self.session
        item = self.get('/api/grabaciones').json['items'][0]
        self.assertTrue(item['en_curso'])
        self.assertNotIn('url', item)
        self.assertEqual(self.get(self.url).status_code, 409)
        self.active = None
        self.assertEqual(self.get(self.url).status_code, 200)

    def test_rotation_protects_latest(self):
        self.active = self.session
        (self.session / 'video_00001.mp4').write_bytes(b'new')
        self.assertEqual(self.get(self.url).status_code, 200)
        self.assertEqual(self.get(self.url.replace(V, 'video_00001.mp4')).status_code, 409)

    def test_ranges_and_head(self):
        for header, body, content_range in [('bytes=2-5', b'2345', 'bytes 2-5/10'),
                ('bytes=7-', b'789', 'bytes 7-9/10'), ('bytes=-3', b'789', 'bytes 7-9/10'),
                ('bytes=8-99', b'89', 'bytes 8-9/10')]:
            with self.subTest(header=header):
                r = self.get(self.url, headers={'Range': header})
                self.assertEqual(r.status_code, 206)
                self.assertEqual(r.data, body)
                self.assertEqual(r.headers['Content-Range'], content_range)
                self.assertEqual(int(r.headers['Content-Length']), len(body))
        r = self.client.head(self.url)
        self.addCleanup(r.close)
        self.assertEqual(r.data, b'')
        self.assertEqual(r.headers['Content-Length'], '10')

    def test_invalid_ranges(self):
        for value in ['bytes=30-', 'bytes=6-2', 'bytes=-0', 'bytes=0-1,3-4', 'bad', 'bytes=-', 'bytes=' + '9'*5000 + '-']:
            with self.subTest(value=value[:20]):
                self.assertEqual(self.get(self.url, headers={'Range': value}).status_code, 416)

    def test_filters_and_pagination(self):
        for n in range(1, 35):
            (self.session / f'video_{n:05d}.mp4').write_bytes(b'x')
        data = self.get('/api/grabaciones?pagina=2').json
        self.assertEqual(len(data['items']), 5)
        self.assertEqual(data['paginas'], 2)
        self.assertEqual(self.get('/api/grabaciones?fecha=2026-10-20').json['total'], 0)
        self.assertEqual(self.get('/api/grabaciones?sesion=' + S).json['total'], 35)
        for query in ['pagina=0', 'pagina=abc', 'fecha=bad', 'sesion=../secret']:
            self.assertEqual(self.get('/api/grabaciones?' + query).status_code, 400)

    def test_missing_deleted_and_traversal(self):
        for url in ['/grabaciones/../secret', '/grabaciones/' + S + '/..%2FREADME.md', '/grabaciones/bad/' + V]:
            self.assertEqual(self.get(url).status_code, 404)
        self.video.unlink()
        self.assertEqual(self.get(self.url).status_code, 404)
        self.assertEqual(self.get('/api/grabaciones').json['total'], 0)

    def test_symlinks_and_hardlinks_not_served(self):
        outside = self.root / 'secret'
        outside.write_bytes(b'secret')
        self.video.unlink()
        self.video.symlink_to(outside)
        self.assertEqual(self.get(self.url).status_code, 404)
        self.assertEqual(self.get('/api/grabaciones').json['total'], 0)
        self.video.unlink()
        os.link(outside, self.video)
        self.assertEqual(self.get(self.url).status_code, 404)
        self.assertEqual(self.get('/api/grabaciones').json['total'], 0)
        linked = '2026-10-20_12-00-00_1234abcd'
        (self.root / linked).symlink_to(self.session, target_is_directory=True)
        self.assertEqual(self.get('/grabaciones/' + linked + '/' + V).status_code, 404)


if __name__ == '__main__':
    unittest.main()
