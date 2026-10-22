# PiCameraRecorder

Cámara de seguridad y proyecto de aprendizaje: Raspberry Pi 5 + Camera Module 3.

## Instalación y documentación

Para instalar en otra Raspberry Pi 5, sigue [INSTALACION.md](INSTALACION.md): incluye APT, entorno virtual, `requirements.txt`, pruebas y adaptación del servicio al usuario y las rutas de la nueva placa. La guía diaria está en [GUIA_DE_USO.md](GUIA_DE_USO.md).

## Uso

El servicio arranca automáticamente. El comando siguiente es una alternativa manual: detén antes `picamera-recorder` para evitar dos procesos usando la cámara.

```bash
cd /home/yago/proyectos/PiCameraRecorder
.venv/bin/python -m picamera_recorder
```

También funciona `.venv/bin/python web.py`. Ctrl+C o SIGTERM detienen la captura,
cierran el último MP4 y liberan la cámara. El cierre del navegador no detiene la
grabación. El arranque automático está habilitado mediante systemd; consulta la sección del servicio al final de este documento.

- Directo: 1280 × 720, 15 fps, MJPEG, una cámara para todos los espectadores.
- Grabación: H.264, bitrate objetivo 2 Mb/s, MP4 de **3600 segundos (una hora)**.
  El corte se realiza en fotogramas clave; puede variar alrededor de un segundo.
  Si se detiene antes, el último archivo será más corto.
- Cada arranque crea una carpeta de sesión distinta:
  `grabaciones/FECHA_HORA_IDENTIFICADOR/video_00000.mp4`, etc.
  Una sesión puede contener varios archivos de una hora; no se detiene al cumplirla.
- Aproximadamente 900 MB por hora, 21,6 GB/día; el tamaño real varía.

## Grabación circular (borrado definitivo)

Al bajar de **1024 MiB libres (1 GiB)**, se borran vídeos cerrados por antigüedad
hasta recuperar **2048 MiB (2 GiB)**. Se comprueba el espacio cada cinco segundos.
Esto se aplica también al arrancar y puede eliminar vídeos de sesiones anteriores.

Solo se consideran MP4 con el nombre generado por la aplicación, en carpetas de
sesión reconocibles dentro de la carpeta configurada con --carpeta. No se siguen
enlaces simbólicos ni se eliminan otros documentos, capturas o archivos enlazados.
Las carpetas vacías se conservan. No guardar documentos personales con esos nombres.

El último archivo de la sesión activa siempre queda protegido. Un bloqueo exclusivo
impide que dos grabadores usen la misma carpeta y borren vídeos abiertos entre sí.
Si no quedan vídeos cerrados suficientes y se pierde la reserva, se detiene solo la
grabación, cierra el archivo activo y mantiene el directo. No se reanuda por sí sola.
Si se recupera la reserva pero no el objetivo, la limpieza continúa en siguientes
comprobaciones cuando haya más vídeos cerrados. Los errores de disco detienen la
grabación. Un corte de corriente puede perder la última parte del archivo activo.

La web muestra archivos conservados de la sesión, espacio libre y borrados/liberación
automáticos de este arranque. Los contadores se reinician al reiniciar la aplicación.

```bash
# Prueba corta en una carpeta independiente
.venv/bin/python web.py --segmentos 8 --duracion 27 --carpeta work/prueba-manual
# Solo directo, sin borrar ni grabar
.venv/bin/python web.py --sin-grabar
# Ajustar límites (MiB); objetivo debe superar reserva
.venv/bin/python web.py --reserva-mb 1024 --objetivo-mb 2048
```

## Acceso

- Red de casa: http://192.168.1.199:8000
- Dispositivo con Tailscale conectado a la misma cuenta: http://100.121.185.67:8000

Se verificó el acceso desde datos móviles. No hay autenticación propia en la web;
el acceso depende de la red local o de las reglas de Tailscale. No abrir puertos
del router para publicar directamente este servidor. Tailscale y PiCameraRecorder funcionan como servicios del sistema.

## Arquitectura

La web utiliza Application Factory y Service Layer. El servicio es propietario de
la camara, el catalogo y el trabajador de preparacion de videos. La interfaz se
divide en componentes HTML, CSS y modulos JavaScript nativos (sin npm).

```text
picamera_recorder/  Configuracion, camara, almacenamiento, catalogo y HTTP
templates/         Pagina y componentes Jinja
static/css/        Estilos adaptables
static/js/         Panel, biblioteca y utilidades compartidas
tests/             Pruebas automaticas con archivos temporales
scripts/           Verificacion opcional con camara real
docs/              Explicacion de arquitectura y puntos de ampliacion
grabaciones/       Videos de usuario (no son codigo)
capturas/          Fotos de usuario (no son codigo)
```

Lee [docs/arquitectura.md](docs/arquitectura.md) para conocer las responsabilidades
de cada archivo y como ampliar el proyecto. Las entradas web.py, grabador.py,
main.py y foto.py conservan su compatibilidad y funcionalidades.

## Fotos y entorno

`.venv/bin/python main.py` lista las cámaras. `main.py --foto` captura un JPEG a
1920 × 1080 en capturas/ tras esperar tres segundos. Detener la web antes de usarlo.
El entorno se creó con --system-site-packages para usar Picamera2 y dependencias nativas.

## Verificación

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/verificar_grabacion.py
```

Las pruebas de limpieza usan directorios temporales y espacio simulado, no vídeos
personales. La prueba real verifica MP4 reproducibles, directo, reinicio y poco espacio;
requiere detener el servidor antes. No se simula la falta de espacio llenando la tarjeta.

## Biblioteca web

La seccion Grabaciones permite filtrar por fecha de sesion y sesion, reproducir
MP4 terminados y descargar una copia. Muestra 30 archivos por pagina, recientes
primero, y actualiza la lista cada 15 segundos. El archivo en curso no se sirve
hasta cerrarse. El reproductor admite avanzar mediante rangos HTTP; la compatibilidad
H.264 depende del navegador. Los vídeos sin estrella siguen sujetos a la limpieza automática.

El listado de CatalogoGrabaciones consulta el disco sin modificarlo; el Blueprint de grabaciones
expone /api/grabaciones y /grabaciones/<sesion>/<archivo>. Solo reconoce nombres
generados por la aplicacion, archivos regulares de un enlace y directorios sin
enlaces simbolicos. Las respuestas de video se envian por bloques, sin cargar un
MP4 completo en RAM. No se publica ningun directorio adicional.

## Reproduccion rapida

La captura mantiene MP4 fragmentados para tolerar mejor interrupciones. Un trabajador
en segundo plano prepara archivos cerrados con ffmpeg -c copy -movflags +faststart:
coloca un indice completo al principio sin recodificar. El listado muestra Preparando
hasta entonces; la descarga del original sigue disponible. Se procesa un video a la
vez, preservando fecha y calidad. Un archivo temporal se valida antes del reemplazo
atomico. Si hay un error o poco espacio temporal, se conserva el original. La limpieza
y el reemplazo comparten un bloqueo. Los temporales no aparecen en la biblioteca.

## Mantenimiento

Los instaladores temporales, copias historicas y resultados de pruebas de desarrollo
no forman parte del codigo mantenido. Antes de esta reorganizacion se archivaron
sus fuentes en una copia fuera del proyecto, en ../PiCameraRecorder-backups/.
Los videos de prueba antiguos se retiraron. La verificacion con camara real crea
sus propios datos dentro de work/, que esta excluido de Git.


## Estado de la Raspberry

El panel muestra temperatura de CPU, tiempo desde el último encendido y errores actuales de grabación. Se actualiza cada tres segundos. Si una lectura del sistema no está disponible, muestra «No disponible»; si se pierde la conexión, indica que no puede confirmar el estado. No es un historial de errores del sistema operativo. Las lecturas se realizan en picamera_recorder/sistema.py, sin dependencias adicionales.


## Eliminar grabaciones desde la web

En Grabaciones, pulsa Eliminar en un archivo cerrado y confirma el nombre y la sesión. El borrado es definitivo; no existe papelera. El archivo en curso no se puede borrar. Si está reproduciéndose el archivo eliminado, el visor vuelve al directo. La lista se actualiza al terminar y el espacio libre, en la siguiente lectura. Solo elimina MP4 propios dentro de grabaciones; las carpetas de sesión se conservan. El borrado comparte el bloqueo de retención y optimización, y exige una petición DELETE con cabecera propia desde la misma web. No añade autenticación: se mantiene el acceso por red local o Tailscale.


## Movimiento en la web

Se analizan imágenes reducidas (160 × 90, hasta cuatro por segundo) en un hilo independiente. No se envían avisos externos. El panel muestra actividad, última detección y sensibilidad baja/media/alta; el cambio de sensibilidad dura hasta reiniciar. Hay dos segundos iniciales de calibración y se requieren tres muestras positivas. Dos segundos de calma agrupan la actividad. Luces, sombras y movimiento de la propia cámara pueden producir detecciones; no distingue personas.

Al reproducir un vídeo, Momentos con movimiento muestra eventos y permite saltar tres segundos antes. Los tiempos son aproximados por el muestreo y la alineación del directo y el codificador. Solo se analizan nuevas grabaciones, sin análisis retroactivo. Los límites de segmentos se leen del CSV del muxer (.segmentos.csv). Los eventos se conservan en .movimiento.sqlite3, dentro de grabaciones. Al borrar vídeos, sus eventos dejan de estar disponibles y se purgan en hasta 30 segundos mientras la aplicación está en marcha. No se modifica ni recodifica el vídeo. Si falla la detección o el almacenamiento de eventos, se muestra el error y la grabación continúa.


## Servicio de arranque automático

PiCameraRecorder está configurado como servicio del sistema `picamera-recorder.service`, ejecutado como usuario `yago`. Arranca al encender la Raspberry, sin abrir sesión ni dejar una terminal abierta. Si el proceso falla, systemd intenta reiniciarlo a los cinco segundos (hasta cinco arranques en un minuto). Los errores de grabación que mantienen la web abierta siguen requiriendo revisión; no son un fallo del proceso.

| Acción | Comando |
| --- | --- |
| Ver estado | `systemctl status picamera-recorder --no-pager` |
| Iniciar ahora | `sudo systemctl start picamera-recorder` |
| Detener ahora, cerrando el vídeo | `sudo systemctl stop picamera-recorder` |
| Reiniciar la aplicación | `sudo systemctl restart picamera-recorder` |
| Desactivar arranque y detener | `sudo systemctl disable --now picamera-recorder` |
| Activar arranque e iniciar | `sudo systemctl enable --now picamera-recorder` |
| Consultar mensajes recientes | `journalctl -u picamera-recorder -n 50 --no-pager` |
| Seguir mensajes en directo | `journalctl -u picamera-recorder -f` |

**Ctrl + C ya no detiene el servicio.** En el comando de seguimiento de mensajes solo deja de mostrar el registro. Para parar la cámara usa `sudo systemctl stop picamera-recorder`.

Después de detener el servicio puedes usar el comando manual del proyecto; no ejecutes ambos a la vez. Desactivar el servicio no borra vídeos ni código. Si solo lo detienes, volverá a arrancar al encender la Raspberry mientras siga habilitado.

Para apagar, usa directamente el menú o `sudo poweroff`: systemd detiene el servicio y cierra el vídeo de forma ordenada. No es necesario detenerlo primero. No desconectes la alimentación mientras graba.

La configuración mantenida está en `deploy/picamera-recorder.service`; la copia que usa systemd está en `/etc/systemd/system/picamera-recorder.service`. Si cambias el usuario o mueves el proyecto, hay que adaptar ambas rutas, instalar de nuevo la unidad y ejecutar `sudo systemctl daemon-reload`.

## Grabaciones importantes

La estrella de la biblioteca excluye ese MP4 de la limpieza automática y bloquea su borrado manual hasta retirarla. Puede marcarse el archivo activo. La protección persiste tras reiniciar; afecta a un archivo, no a toda su sesión. Si no quedan archivos borrables y no se mantiene la reserva de disco, la grabación se detiene y conserva los protegidos. Consulta la guía de uso para los controles.

El arranque automático se ha comprobado tras apagar y volver a encender la placa. El servicio funciona en segundo plano, sin ventana ni terminal; `active (running)` confirma el proceso y la web permite comprobar la grabación.
