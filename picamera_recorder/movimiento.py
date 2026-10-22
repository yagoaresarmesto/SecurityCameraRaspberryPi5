"""Detección básica y eventos persistentes; no modifica la captura de vídeo."""
from contextlib import contextmanager
import csv
import io
import math
import os
import sqlite3
import stat
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic, time

import numpy as np
from PIL import Image, ImageFilter


class Detector:
    """Cuatro muestras/s, tres positivas y dos segundos de calma para agrupar."""
    UMBRALES = {'baja': .08, 'media': .035, 'alta': .012}

    def __init__(self):
        self.anterior = None
        self.positivas = 0
        self.primera = None
        self.inicio = None
        self.ultima = None
        self.nivel = 'media'
        self.muestras = 0

    def analizar(self, imagen, instante):
        actual = np.asarray(imagen.resize((160, 90)).convert('L').filter(ImageFilter.GaussianBlur(1)), dtype=np.int16)
        anterior, self.anterior = self.anterior, actual
        self.muestras += 1
        if anterior is None or self.muestras <= 8:
            return None
        delta = actual - anterior
        # Compensa cambios uniformes de exposición sin ignorar movimiento local.
        diferencia = np.abs(delta - np.median(delta))
        proporcion = float(np.mean(diferencia > 18))
        if proporcion >= self.UMBRALES[self.nivel]:
            if not self.positivas:
                self.primera = instante
            self.positivas += 1
            self.ultima = instante
            if self.positivas >= 3 and self.inicio is None:
                self.inicio = self.primera
        else:
            self.positivas = 0
        if self.inicio is not None:
            evento = (self.inicio, max(self.inicio, self.ultima))
            if instante - self.ultima >= 2:
                self.inicio = None
            return evento
        return None


class EventosMovimiento:
    """SQLite con acceso serializado y rangos reales del muxer para cada MP4."""
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.ruta = self.carpeta / '.movimiento.sqlite3'
        self.bloqueo = RLock()

    @contextmanager
    def _abrir(self):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.ruta, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OSError('Base de eventos no válida')
        finally:
            os.close(fd)
        db = sqlite3.connect(self.ruta, timeout=2)
        db.execute('CREATE TABLE IF NOT EXISTS videos (sesion TEXT, nombre TEXT, inicio REAL, fin REAL, PRIMARY KEY(sesion,nombre))')
        db.execute('CREATE TABLE IF NOT EXISTS eventos (sesion TEXT, inicio REAL, fin REAL, PRIMARY KEY(sesion,inicio))')
        try:
            with db:
                yield db
        finally:
            db.close()

    def registrar(self, sesion, inicio, fin):
        with self.bloqueo, self._abrir() as db:
            db.execute('INSERT INTO eventos VALUES (?,?,?) ON CONFLICT(sesion,inicio) DO UPDATE SET fin=max(fin,excluded.fin)', (sesion,inicio,fin))

    def sincronizar(self, sesion, rangos):
        with self.bloqueo, self._abrir() as db:
            db.executemany('INSERT INTO videos VALUES (?,?,?,?) ON CONFLICT(sesion,nombre) DO UPDATE SET inicio=excluded.inicio,fin=excluded.fin', [(sesion,n,a,b) for n,a,b in rangos])

    def listar(self, sesion, nombre):
        if not self.ruta.exists():
            return {'disponible': False, 'eventos': [], 'total': 0}
        with self.bloqueo, self._abrir() as db:
            rango = db.execute('SELECT inicio,fin FROM videos WHERE sesion=? AND nombre=?', (sesion,nombre)).fetchone()
            if rango is None:
                return {'disponible': False, 'eventos': [], 'total': 0}
            a,b = rango
            total = db.execute('SELECT count(*) FROM eventos WHERE sesion=? AND inicio<? AND fin>=?', (sesion,b,a)).fetchone()[0]
            rows = db.execute('SELECT inicio,fin FROM eventos WHERE sesion=? AND inicio<? AND fin>=? ORDER BY inicio LIMIT 500', (sesion,b,a)).fetchall()
            return {'disponible': True, 'total': total, 'eventos': [{'inicio': round(max(0,x-a),2), 'fin': round(max(0,min(b,y)-a),2)} for x,y in rows]}

    def limpiar(self, existentes):
        if not self.ruta.exists(): return
        with self.bloqueo, self._abrir() as db:
            for sesion,nombre in db.execute('SELECT sesion,nombre FROM videos').fetchall():
                if (sesion,nombre) not in existentes:
                    db.execute('DELETE FROM videos WHERE sesion=? AND nombre=?',(sesion,nombre))
            db.execute('DELETE FROM eventos WHERE NOT EXISTS (SELECT 1 FROM videos WHERE videos.sesion=eventos.sesion AND eventos.inicio<videos.fin AND eventos.fin>=videos.inicio)')


class Movimiento:
    def __init__(self, salida, grabador, catalogo):
        self.salida, self.grabador, self.catalogo = salida, grabador, catalogo
        self.eventos = EventosMovimiento(grabador.carpeta)
        self.detector = Detector()
        self.parar = Event()
        self.hilo = None
        self.bloqueo = RLock()
        self.error = None
        self.ultimo = None
        self.arranque = None
        self.ultimo_frame = None

    def iniciar(self):
        self.hilo = Thread(target=self._bucle, name='movimiento', daemon=True)
        self.hilo.start()

    def detener(self):
        self.parar.set()
        if self.hilo:
            self.hilo.join(timeout=5)

    def nivel(self, valor):
        if valor not in Detector.UMBRALES: raise ValueError('Sensibilidad no válida')
        with self.bloqueo:
            self.detector.nivel = valor
            self.detector.anterior = None
            self.detector.positivas = 0
        return self.estado()

    def estado(self):
        with self.bloqueo:
            return {'activo': self.detector.inicio is not None and self.ultimo_frame is not None and monotonic()-self.ultimo_frame<3,
                    'sensibilidad': self.detector.nivel, 'ultimo': self.ultimo, 'error': self.error,
                    'disponible': self.ultimo_frame is not None and monotonic()-self.ultimo_frame<3,
                    'calibrando': self.detector.muestras <= 8}

    def _rangos(self):
        sesion = self.grabador.sesion
        if sesion is None: return []
        rangos = []
        try:
            with (sesion/'.segmentos.csv').open() as archivo:
                for row in csv.reader(archivo):
                    if len(row) != 3: continue
                    nombre = Path(row[0]).name
                    from .almacenamiento import VIDEO
                    if not VIDEO.fullmatch(nombre): continue
                    a,b = float(row[1]),float(row[2])
                    if math.isfinite(a) and math.isfinite(b) and b>=a>=0:
                        rangos.append((nombre,a,b))
        except FileNotFoundError: pass
        archivos = self.grabador.almacen.archivos(sesion)
        conocidos = {n for n,_,_ in rangos}
        if archivos and archivos[-1][1].name not in conocidos:
            inicio = max((b for _,_,b in rangos),default=0)
            fin = max(inicio+.01, monotonic()-(self.arranque or monotonic()))
            rangos.append((archivos[-1][1].name,inicio,fin))
        return rangos

    def _bucle(self):
        ultima_escritura = 0
        ultima_limpieza = 0
        ultimo_evento = None
        while not self.parar.wait(.25):
            try:
                with self.salida.condition:
                    frame, instante = self.salida.frame, self.salida.instante
                    primero = self.salida.primero
                if frame is None or instante == self.ultimo_frame: continue
                self.arranque = primero
                with Image.open(io.BytesIO(frame)) as imagen:
                    with self.bloqueo:
                        evento = self.detector.analizar(imagen,instante-primero)
                        self.ultimo_frame = instante
                        self.error = None
                        if evento:
                            ultimo_evento = evento
                            self.ultimo = time()
                ahora = monotonic()
                if ahora-ultima_escritura>=2 or self.parar.is_set():
                    sesion = self.grabador.sesion
                    if sesion is not None:
                        with self.grabador.bloqueo_almacen:
                            self.eventos.sincronizar(sesion.name,self._rangos())
                            if ultimo_evento is not None:
                                self.eventos.registrar(sesion.name,*ultimo_evento)
                        ultimo_evento = None
                    ultima_escritura = ahora
                if ahora-ultima_limpieza>=30:
                    with self.grabador.bloqueo_almacen:
                        existentes={(v['sesion'],v['archivo']) for v in self.catalogo.listar()}
                        self.eventos.limpiar(existentes)
                    ultima_limpieza = ahora
            except Exception as error:
                with self.bloqueo:
                    self.error = 'No se pudo analizar o guardar movimiento; la grabación continúa.'
                print(f'Movimiento: {error}',flush=True)
                self.parar.wait(2)
        # Registrar la última actividad y los rangos al cerrar ordenadamente.
        try:
            sesion=self.grabador.sesion
            if sesion is not None:
                with self.grabador.bloqueo_almacen:
                    self.eventos.sincronizar(sesion.name,self._rangos())
                    if ultimo_evento is not None: self.eventos.registrar(sesion.name,*ultimo_evento)
        except Exception as error:
            print(f'Cierre movimiento: {error}',flush=True)
