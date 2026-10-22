import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from picamera_recorder.movimiento import Detector, EventosMovimiento


def foto(pos=None, fondo=40):
    image=Image.new('L',(160,90),fondo)
    if pos is not None:
        ImageDraw.Draw(image).rectangle((pos,10,pos+35,75),fill=230)
    return image


class DetectorTests(unittest.TestCase):
    def calibrar(self,d):
        for n in range(9): d.analizar(foto(),n*.25)

    def test_escena_estatica_y_cambio_luz_uniforme(self):
        d=Detector(); self.calibrar(d)
        for n in range(10,30): self.assertIsNone(d.analizar(foto(fondo=100),n*.25))
        self.assertIsNone(d.inicio)

    def test_movimiento_sostenido_y_agrupacion(self):
        d=Detector(); self.calibrar(d)
        for n,pos in enumerate((10,35,60),10): evento=d.analizar(foto(pos),n*.25)
        self.assertIsNotNone(evento)
        inicio=evento[0]
        self.assertIsNotNone(d.inicio)
        d.analizar(foto(60),3.25)
        evento=d.analizar(foto(85),3.5)
        self.assertEqual(evento[0],inicio)
        evento=d.analizar(foto(85),6)
        self.assertEqual(evento[0],inicio)
        self.assertIsNone(d.inicio)

    def test_cambio_aislado_no_crea_evento(self):
        d=Detector(); self.calibrar(d)
        self.assertIsNone(d.analizar(foto(10),3))
        self.assertIsNone(d.analizar(foto(10),3.25))
        self.assertIsNone(d.inicio)


class EventosTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=EventosMovimiento(self.root)

    def test_cruce_de_segmento_y_persistencia(self):
        self.db.sincronizar('sesion',[('video_00000.mp4',0,8),('video_00001.mp4',8,16)])
        self.db.registrar('sesion',7,10)
        self.db.registrar('sesion',7,11)
        reabierto=EventosMovimiento(self.root)
        self.assertEqual(reabierto.listar('sesion','video_00000.mp4')['eventos'],[{'inicio':7,'fin':8}])
        self.assertEqual(reabierto.listar('sesion','video_00001.mp4')['eventos'],[{'inicio':0,'fin':3}])
        self.assertEqual(reabierto.listar('sesion','video_00001.mp4')['total'],1)

    def test_limpieza_conserva_evento_compartido(self):
        self.db.sincronizar('sesion',[('a',0,8),('b',8,16)])
        self.db.registrar('sesion',7,10)
        self.db.limpiar({('sesion','b')})
        self.assertFalse(self.db.listar('sesion','a')['disponible'])
        self.assertEqual(self.db.listar('sesion','b')['total'],1)
        self.db.limpiar(set())
        with self.db._abrir() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM eventos').fetchone()[0],0)

    def test_legacy_no_se_presenta_como_sin_movimiento(self):
        self.assertFalse(self.db.listar('antigua','video.mp4')['disponible'])
        self.db.sincronizar('nueva',[('video.mp4',0,8)])
        resultado=self.db.listar('nueva','video.mp4')
        self.assertTrue(resultado['disponible'])
        self.assertEqual(resultado['eventos'],[])

    def test_no_sigue_enlace_base(self):
        exterior=self.root/'personal'
        exterior.write_text('conservar')
        self.db.ruta.symlink_to(exterior)
        with self.assertRaises(OSError): self.db.registrar('s',0,1)
        self.assertEqual(exterior.read_text(),'conservar')
