# Instalar PiCameraRecorder en otra Raspberry Pi 5

## Entorno y alcance

Proyecto para Raspberry Pi 5 y Camera Module 3, con Raspberry Pi OS de 64 bits y su Python del sistema. La instalación actual funciona con base Debian 13 (Trixie), Python 3.13.5 y Picamera2 0.3.36. No se ha probado una instalación limpia en una segunda placa. Usa una imagen de Raspberry Pi OS compatible con Pi 5; un Debian genérico puede no traer el soporte de cámara necesario.

`requirements.txt` cubre Flask. Picamera2, libcamera, PyAV, NumPy y Pillow se obtienen de los repositorios del sistema para mantener la compatibilidad de los componentes nativos. No copies el entorno `.venv` de otra máquina ni instales versiones de cámara o NumPy con pip encima de las del sistema.

Este flujo sigue la recomendación del [manual oficial de Picamera2](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf): paquetes de cámara mediante APT y entorno virtual con acceso a los paquetes del sistema.

## 1. Preparar la placa y copiar el proyecto

Con la placa apagada y sin alimentación, conecta la cámara con el cable compatible con Pi 5. Prepara Raspberry Pi OS de 64 bits, conecta la red y configura tu usuario.

Copia el código a `~/proyectos/PiCameraRecorder`. Incluye:

- `picamera_recorder/`, `templates/`, `static/`, `tests/`, `scripts/`, `deploy/` y `docs/`.
- `requirements.txt`, los documentos Markdown y las entradas `web.py`, `main.py`, `foto.py` y `grabador.py`.

No necesitas copiar `.venv/`, `__pycache__/`, `work/`, `grabaciones/` ni `capturas/` para una instalación nueva. No borres esos directorios de la placa original: pueden contener vídeos y fotos. La aplicación crea su carpeta de grabaciones al arrancar.

Si decides migrar también vídeos, detén antes el servicio de origen y copia completa la carpeta `grabaciones/`, incluidos sus archivos ocultos: las estrellas y los eventos están ahí. No mezcles dos grabadores escribiendo en una carpeta compartida.

## 2. Dependencias del sistema

En la nueva Raspberry:

```bash
sudo apt update
sudo apt install python3-venv python3-picamera2 python3-av python3-numpy python3-pil python3-flask ffmpeg rpicam-apps
```

Estos paquetes instalan también sus dependencias, incluido el soporte libcamera necesario. Si APT no encuentra los paquetes, revisa la imagen y los repositorios de Raspberry Pi OS; no lo soluciones sustituyendo el Python del sistema.

## 3. Crear el entorno virtual

Desde la carpeta copiada:

```bash
cd ~/proyectos/PiCameraRecorder
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

El entorno usa las bibliotecas de cámara de APT y mantiene separadas las instalaciones adicionales de pip. El comando con `-r` no es un instalador completo del sistema: ejecuta primero el paso de APT.

## 4. Comprobar la cámara y el código

Asegúrate de que ninguna otra aplicación usa la cámara:

```bash
rpicam-hello --list-cameras
.venv/bin/python -c "import flask, picamera2, av, numpy; from PIL import Image; from picamera2.outputs import PyavOutput; print('Dependencias disponibles')"
.venv/bin/python -m unittest discover -s tests -v
```

Debe aparecer la cámara IMX708. Las pruebas usan archivos temporales y no necesitan tomar el control de la cámara. En la versión documentada hay 49 pruebas.

Primera comprobación de la web sin grabar ni limpiar vídeos:

```bash
.venv/bin/python -m picamera_recorder --sin-grabar
```

Abre `http://IP_DE_LA_NUEVA_RASPBERRY:8000/` desde un dispositivo de la misma red. Puedes consultar sus IP con `hostname -I`. Comprueba el directo, detén esta ejecución manual con Ctrl+C y espera a que libere la cámara. Para probar la grabación manual, ejecuta después:

```bash
.venv/bin/python -m picamera_recorder
```

Por defecto empieza a grabar y activa la limpieza circular de archivos propios en `grabaciones/`. Usa una carpeta nueva si estás haciendo pruebas con datos existentes. Detén la ejecución manual antes de instalar o iniciar el servicio.

## 5. Configurar el arranque automático (opcional)

La unidad `deploy/picamera-recorder.service` contiene el usuario y las rutas de la placa original. En la nueva placa, prepara una copia y edítala:

```bash
cp deploy/picamera-recorder.service /tmp/picamera-recorder.service
nano /tmp/picamera-recorder.service
```

Adapta `User`, `Group`, `WorkingDirectory` y `ExecStart` al usuario, grupo y ruta absolutos de la nueva Raspberry. `whoami`, `id -gn` y `pwd` ayudan a identificarlos. `ExecStart` debe usar el Python de su nueva `.venv`; systemd no expande `~` como una terminal. No ejecutes la cámara como root para resolver permisos.

Guarda y valida la unidad. Si la validación informa de errores, corrígelos antes de continuar:

```bash
systemd-analyze verify /tmp/picamera-recorder.service
```

Una vez validada, guarda la configuración adaptada en el proyecto e instálala. En una placa donde ya exista el servicio, revisa primero su configuración: los comandos siguientes la reemplazan.

```bash
cp /tmp/picamera-recorder.service deploy/picamera-recorder.service
sudo install -m 644 deploy/picamera-recorder.service /etc/systemd/system/picamera-recorder.service
sudo systemctl daemon-reload
sudo systemctl enable --now picamera-recorder
systemctl status picamera-recorder --no-pager -l
```

Comprueba en la web «Grabando» y «Señal activa». Para consultar registros:

```bash
journalctl -u picamera-recorder -n 50 --no-pager
```

Para desactivar el arranque y detenerlo: `sudo systemctl disable --now picamera-recorder`. Para reactivarlo e iniciarlo: `sudo systemctl enable --now picamera-recorder`. No lances a la vez el servicio y la ejecución manual.

## 6. Red y uso diario

Las IP de la guía de uso corresponden a la placa original. La nueva tendrá sus propias direcciones. Para usarla fuera de casa, configura Tailscale en esa placa y autorízala en tu red privada; no copies credenciales ni el estado de Tailscale de la placa original.

La web no tiene inicio de sesión propio. Quien tenga acceso de red al puerto 8000 podrá entrar al panel. No publiques ese puerto en el router.

Consulta [GUIA_DE_USO.md](GUIA_DE_USO.md) para grabación, movimiento, estrellas y apagado. Puedes apagar directamente desde el menú o con `sudo poweroff`: systemd detiene el servicio y cierra el vídeo. Espera al fin del apagado antes de quitar la corriente.

## Referencia del entorno comprobado (22/10/2026)

| Componente | Versión observada |
| --- | --- |
| Python | 3.13.5 |
| Flask | 3.1.1 |
| Picamera2 | 0.3.36 |
| PyAV | 14.2.0 |
| NumPy | 2.2.4 |
| Pillow | 11.1.0 |
| FFmpeg (APT) | 8:7.1.3-0+deb13u1+rpt1 |
| rpicam-apps | 1.12.0 |

Son versiones observadas, no una lista para congelar con pip. Las bibliotecas nativas se actualizan juntas mediante APT. En una segunda placa hay que verificar dependencias, pruebas y cámara antes de dar por terminada la instalación.
