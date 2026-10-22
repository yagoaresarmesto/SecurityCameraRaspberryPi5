# Guía de uso de PiCameraRecorder

Raspberry Pi 5 con Camera Module 3. Esta guía explica el uso diario; los detalles técnicos están en README.md y docs/arquitectura.md.

## 1. Encender y arrancar

Enciende la Raspberry y espera a que termine de iniciar: PiCameraRecorder arranca automáticamente y puedes abrir la web.

Si has desactivado el servicio, puedes arrancarlo con `sudo systemctl start picamera-recorder`. Para usarlo manualmente, detén antes el servicio y ejecuta:

```bash
cd ~/proyectos/PiCameraRecorder
.venv/bin/python -m picamera_recorder
```

No hace falta activar antes el entorno virtual: el comando ya utiliza su Python.
Solo en modo manual debes dejar esa terminal abierta. En el modo automático no necesitas ninguna terminal.

Se inician el directo, la grabación y la limpieza automática. No ejecutes una segunda instancia.

## 2. Abrir la web

Desde un ordenador o móvil conectado a la misma red de casa:

[Panel en la red local](http://192.168.1.199:8000/)

Desde fuera de casa, por ejemplo con datos móviles:

1. Conecta Tailscale en el móvil u ordenador a la misma red privada que la Raspberry.
2. Comprueba que la Raspberry está encendida, conectada a Internet y con PiCameraRecorder arrancado.
3. Abre [Panel mediante Tailscale](http://100.121.185.67:8000/).

Las direcciones corresponden a la configuración actual. La IP local puede cambiar si el router la reasigna. La web no tiene una cuenta ni contraseña propia: el acceso depende de la red local o de Tailscale.

## 3. Ver el directo

En «Vista general» aparece la imagen de la cámara y el estado de grabación.

- «Señal activa» indica que el visor recibe imagen.
- El botón de reconexión vuelve a solicitar el directo si se queda parado.
- El botón de pantalla completa amplía el visor cuando el navegador lo permite.

Puedes cerrar el navegador: la Raspberry sigue grabando mientras la aplicación permanece en marcha.

## 4. Cómo se guardan los vídeos

La grabación es continua y se divide en archivos MP4 de aproximadamente una hora. Al completar uno, comienza el siguiente. Si detienes la aplicación antes, el último será más corto.

Cada arranque crea una sesión nueva. Los archivos se guardan en la Raspberry dentro del proyecto:

```text
grabaciones/FECHA_HORA_IDENTIFICADOR/video_00000.mp4
```

El formato es H.264 a 1280 × 720 y 15 imágenes por segundo. El tamaño orientativo es de 900 MB por hora; puede variar.

## 5. Consultar, reproducir y descargar

Abre «Grabaciones» en el menú lateral.

1. Usa los filtros de fecha y sesión si necesitas localizar un vídeo.
2. Pulsa «Actualizar» para consultar de nuevo la lista; también se actualiza automáticamente cada 15 segundos.
3. Pulsa «Reproducir» en un archivo disponible. Puedes avanzar mediante la barra del reproductor.
4. Pulsa «Cerrar reproductor» para regresar al directo.
5. Usa el enlace «Descargar» para conservar una copia en tu ordenador o móvil.

Estados de los archivos:

| Estado | Significado |
| --- | --- |
| En curso | Se está escribiendo; estará disponible cuando se cierre. |
| Preparando | Se está preparando el índice del MP4 para reproducirlo con rapidez, sin perder calidad. La descarga puede estar disponible mientras tanto. |
| Disponible | Ya puede reproducirse y descargarse. |

Si la reproducción tarda, espera a que termine la preparación, actualiza la lista y vuelve a probar. La conexión y la compatibilidad H.264 del navegador también influyen.

## 6. Espacio y borrado automático

Cuando quedan menos de 1 GiB libres, la aplicación borra las grabaciones cerradas más antiguas hasta intentar recuperar 2 GiB. También comprueba el espacio al arrancar.

**El borrado es definitivo. La limpieza conserva los vídeos con estrella; descarga una copia para guardarlos también fuera de la Raspberry.**

El archivo que se está grabando queda protegido. Si no puede recuperar espacio suficiente, se detiene la grabación y el directo sigue funcionando. Tras liberar espacio, hay que reiniciar la aplicación para volver a grabar.

Los contadores de archivos borrados y espacio recuperado corresponden al arranque actual; se reinician al volver a iniciar la aplicación.

## 7. Detener y apagar con seguridad

Puedes apagar directamente desde el menú o con `sudo poweroff`: el sistema detiene el servicio y cierra el vídeo. No necesitas pararlo antes. Si solo quieres detener la cámara sin apagar la Raspberry, usa `sudo systemctl stop picamera-recorder`. Los pasos con Ctrl + C siguientes son solo para el modo manual.

1. Ve a la terminal donde está funcionando PiCameraRecorder.
2. Pulsa **Ctrl + C** una vez.
3. Espera a que cierre el archivo y aparezca el mensaje de cámara liberada y el prompt de la terminal.
4. Apaga la Raspberry desde el menú del sistema, o ejecuta:

```bash
sudo poweroff
```

Espera a que termine el apagado antes de desconectar la alimentación. Evita desenchufarla mientras graba: podrías perder la última parte del archivo activo.

Al volver a encenderla, el servicio se inicia solo si permanece habilitado.

## 8. Problemas habituales

| Problema | Qué comprobar |
| --- | --- |
| La web no abre | Raspberry encendida, aplicación arrancada y dirección correcta. Fuera de casa, Tailscale conectado en ambos dispositivos. |
| El directo no aparece | Pulsa reconectar. Si persiste, consulta `journalctl -u picamera-recorder -n 50 --no-pager` y comprueba que ninguna otra aplicación use la cámara. |
| El vídeo actual no se reproduce | Es normal mientras está «En curso». Espera al cierre del segmento o detén el servicio con `sudo systemctl stop picamera-recorder` para cerrarlo (Ctrl+C solo en modo manual). |
| Un vídeo aparece como «Preparando» | Espera y actualiza la lista. Los archivos grandes necesitan más tiempo. |
| No graba pero hay directo | Revisa el estado, el espacio libre y los registros del servicio. Libera espacio si hace falta y reinicia la aplicación. |
| «Address already in use» al arrancar | Puede haber otra instancia usando el puerto 8000. Comprueba `systemctl status picamera-recorder --no-pager` antes de iniciar otra instancia. |
| Desaparece una grabación antigua | Puede haber actuado la limpieza automática. Las copias descargadas quedan fuera de esa limpieza. |

## 9. Dónde ampliar información

- [INSTALACION.md](INSTALACION.md): instalación en otra Raspberry Pi 5.
- README.md: configuración, opciones de terminal y pruebas.
- docs/arquitectura.md: organización del código y puntos de ampliación.

Configuración documentada: segmentos de 3600 segundos, reserva de 1024 MiB y objetivo de 2048 MiB. Estos valores pueden cambiar si se arranca con otras opciones.


## Estado de la Raspberry

El panel muestra temperatura de CPU, tiempo desde el último encendido y errores actuales de grabación. Se actualiza cada tres segundos. Si una lectura del sistema no está disponible, muestra «No disponible»; si se pierde la conexión, indica que no puede confirmar el estado. No es un historial de errores del sistema operativo. Las lecturas se realizan en picamera_recorder/sistema.py, sin dependencias adicionales.


## Eliminar grabaciones desde la web

En Grabaciones, pulsa Eliminar en un archivo cerrado y confirma el nombre y la sesión. El borrado es definitivo; no existe papelera. El archivo en curso no se puede borrar. Si está reproduciéndose el archivo eliminado, el visor vuelve al directo. La lista se actualiza al terminar y el espacio libre, en la siguiente lectura. Solo elimina MP4 propios dentro de grabaciones; las carpetas de sesión se conservan. El borrado comparte el bloqueo de retención y optimización, y exige una petición DELETE con cabecera propia desde la misma web. No añade autenticación: se mantiene el acceso por red local o Tailscale.


## Movimiento en la web

Se analizan imágenes reducidas (160 × 90, hasta cuatro por segundo) en un hilo independiente. No se envían avisos externos. El panel muestra actividad, última detección y sensibilidad baja/media/alta; el cambio de sensibilidad dura hasta reiniciar. Hay dos segundos iniciales de calibración y se requieren tres muestras positivas. Dos segundos de calma agrupan la actividad. Luces, sombras y movimiento de la propia cámara pueden producir detecciones; no distingue personas.

Al reproducir un vídeo, Momentos con movimiento muestra eventos y permite saltar tres segundos antes. Los tiempos son aproximados por el muestreo y la alineación del directo y el codificador. Solo se analizan nuevas grabaciones, sin análisis retroactivo. Los límites de segmentos se leen del CSV del muxer (.segmentos.csv). Los eventos se conservan en .movimiento.sqlite3, dentro de grabaciones. Al borrar vídeos, sus eventos dejan de estar disponibles y se purgan en hasta 30 segundos mientras la aplicación está en marcha. No se modifica ni recodifica el vídeo. Si falla la detección o el almacenamiento de eventos, se muestra el error y la grabación continúa.


## Uso en móvil

Los filtros se apilan en filas y cada grabación se muestra como una tarjeta con tamaño, estado y acciones. No hace falta desplazar una tabla horizontalmente para reproducir, descargar o eliminar. Los controles se adaptan al ancho disponible.


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

Puedes apagar directamente desde el menú o con `sudo poweroff`. systemd detendrá el servicio y cerrará el vídeo; no es necesario pararlo antes. No desconectes la alimentación mientras graba.

La configuración mantenida está en `deploy/picamera-recorder.service`; la copia que usa systemd está en `/etc/systemd/system/picamera-recorder.service`. Si cambias el usuario o mueves el proyecto, hay que adaptar ambas rutas, instalar de nuevo la unidad y ejecutar `sudo systemctl daemon-reload`.

## Vídeos importantes (estrella)

En Grabaciones, pulsa **☆ Proteger** para conservar un vídeo. Aparecerá **★ Importante** y la limpieza automática lo omitirá. También puedes marcar el archivo en curso: la estrella protege ese archivo concreto, no toda la sesión ni los siguientes segmentos. La marca se conserva al reiniciar.

Pulsa **★ Importante** para quitar la estrella y permitir de nuevo su limpieza. Para eliminarlo manualmente, quita primero la estrella y después pulsa Eliminar y confirma. Marcar no duplica ni recodifica el vídeo.

Si el disco se queda sin la reserva mínima y solo quedan archivos protegidos o en curso, la grabación se detiene y el directo continúa. La estrella no es una copia de seguridad: descarga los vídeos que quieras conservar fuera de la Raspberry.

El arranque automático se ha verificado tras apagar y encender la Raspberry. No aparece una ventana: funciona en segundo plano. En `systemctl status`, `enabled` indica arranque al encender y `active (running)` indica un proceso activo; comprueba «Grabando» en la web para confirmar la grabación. Ctrl+C en el visor `journalctl -f` solo cierra ese visor.
