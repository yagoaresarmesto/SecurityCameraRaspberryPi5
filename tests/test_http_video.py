import io
import unittest
from flask import Flask
from picamera_recorder.http_video import interpretar_rango, responder_video


class HttpVideoTests(unittest.TestCase):
    def test_empty_file_and_suffix_larger_than_file(self):
        self.assertEqual(interpretar_rango(0).longitud, 0)
        self.assertEqual(interpretar_rango(10, 'bytes=-99').longitud, 10)
        with self.assertRaises(ValueError): interpretar_rango(0, 'bytes=0-')

    def test_descriptor_closed_when_stream_is_abandoned(self):
        app = Flask(__name__)
        stream = io.BytesIO(b'x' * 600000)
        with app.test_request_context('/'):
            response = responder_video(stream, 600000, 'video.mp4')
            next(iter(response.response))
            response.close()
        self.assertTrue(stream.closed)

    def test_head_range_closes_without_reading(self):
        app = Flask(__name__)
        stream = io.BytesIO(b'0123456789')
        with app.test_request_context('/', method='HEAD', headers={'Range':'bytes=3-7'}):
            response = responder_video(stream, 10, 'video.mp4')
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.headers['Content-Length'], '5')
            self.assertTrue(stream.closed)
            response.close()
