import io
from time import monotonic
from threading import Condition

class Fotogramas(io.BufferedIOBase):
    """Conserva solo la ultima imagen; no escribe archivos."""
    def __init__(self):
        self.condition = Condition()
        self.frame = None
        self.instante = None
        self.primero = None
        self.sequence = 0
        self.stopped = False

    def write(self, data):
        with self.condition:
            self.instante = monotonic()
            if self.primero is None: self.primero = self.instante
            self.frame = bytes(data)
            self.sequence += 1
            self.condition.notify_all()
        return len(data)

    def generar(self):
        anterior = 0
        while True:
            with self.condition:
                listo = self.condition.wait_for(
                    lambda: self.sequence != anterior or self.stopped, timeout=10
                )
                if self.stopped or not listo:
                    return
                frame = self.frame
                anterior = self.sequence
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + frame + b"\r\n")
