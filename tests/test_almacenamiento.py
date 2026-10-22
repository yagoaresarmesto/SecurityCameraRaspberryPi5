import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from picamera_recorder.almacenamiento import AlmacenamientoCircular, MIB
from picamera_recorder.config import leer_configuracion


class CircularTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session = self.root / '2026-10-21_10-00-00_1234abcd'
        self.session.mkdir()

    def video(self, n, age=1):
        p = self.session / f'video_{n:05d}.mp4'
        p.write_bytes(b'video')
        os.utime(p, (age, age))
        return p

    def storage(self, free=5, increment=10):
        initial = set(self.root.rglob('*.mp4'))
        return AlmacenamientoCircular(self.root, 10, 20,
            medir=lambda _: SimpleNamespace(free=(free + increment * sum(not p.exists() for p in initial))*MIB))

    def test_oldest_first_and_target(self):
        newest = self.video(0, 30)
        oldest = self.video(1, 10)
        middle = self.video(2, 20)
        s = self.storage()
        self.assertTrue(s.asegurar_espacio())
        self.assertFalse(oldest.exists())
        self.assertFalse(middle.exists())
        self.assertTrue(newest.exists())
        self.assertEqual(s.borrados, 2)
        self.assertEqual(s.bytes_borrados, 10)

    def test_active_latest_numeric_is_protected(self):
        closed = self.video(99999)
        active = self.video(100000)
        s = self.storage(increment=30)
        self.assertTrue(s.asegurar_espacio(self.session))
        self.assertFalse(closed.exists())
        self.assertTrue(active.exists())

    def test_only_active_cannot_recover(self):
        active = self.video(0)
        s = self.storage()
        self.assertFalse(s.asegurar_espacio(self.session))
        self.assertTrue(active.exists())

    def test_above_reserve_does_not_delete(self):
        video = self.video(0)
        s = self.storage(free=15)
        self.assertTrue(s.asegurar_espacio())
        self.assertTrue(video.exists())
        self.assertEqual(s.borrados, 0)

    def test_foreign_and_linked_files_untouched(self):
        outside = self.root / 'personal.mp4'
        outside.write_bytes(b'personal')
        (self.session / 'video_00000.mp4').symlink_to(outside)
        os.link(outside, self.session / 'video_00001.mp4')
        foreign = self.root / 'personal'
        foreign.mkdir()
        (foreign / 'video_00000.mp4').write_bytes(b'personal')
        (self.root / '2026-10-20_10-00-00_1234abcd').symlink_to(foreign, target_is_directory=True)
        s = self.storage()
        self.assertFalse(s.asegurar_espacio())
        self.assertEqual(outside.read_bytes(), b'personal')
        self.assertEqual(s.borrados, 0)

    def test_hour_default(self):
        self.assertEqual(leer_configuracion([]).segmentos, 3600)

    def test_single_writer_lock(self):
        from picamera_recorder.grabacion import Grabador
        first = Grabador(self.root)
        second = Grabador(self.root)
        first._iniciar = lambda camera: setattr(first, 'activo', True)
        second._iniciar = lambda camera: setattr(second, 'activo', True)
        try:
            first.iniciar(None)
            with self.assertRaises(BlockingIOError):
                second.iniciar(None)
        finally:
            first.detener(None)
        second.iniciar(None)
        second.detener(None)


if __name__ == '__main__':
    unittest.main()
