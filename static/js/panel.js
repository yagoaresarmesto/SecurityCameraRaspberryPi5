import { $, number, set } from './utilidades.js';
/* Estado: lectura de /estado. Los controles del visor no modifican la grabación. */
let previousFrames = null, stalled = 0, imageFailed = false, polling = false;
const amount = mb => mb >= 1024 ? (mb / 1024).toLocaleString('es-ES', {maximumFractionDigits:1}) + ' GiB' : number.format(mb) + ' MiB';
function notice(message) { $('alert').hidden = !message; set('alert', message || ''); }
function tick() {
 const now = new Date();
 set('date', now.toLocaleDateString('es-ES', {day:'numeric', month:'long', year:'numeric'}));
 set('clock', now.toLocaleTimeString('es-ES', {hour12:false}) + ' · Hora local');
}
function disconnected() {
 set('motion-state', 'Sin conexión'); set('motion-last', 'No se puede confirmar la actividad.');
 set('system-temp', 'Sin conexión'); set('system-uptime', 'Sin conexión'); set('system-error', 'No se puede consultar el estado de grabación.');
 set('connection-text', 'Sin conexión'); $('connection').classList.add('error-text');
 set('record-state', 'Sin conexión'); $('record-card').classList.add('pending');
 set('record-note', 'No se puede confirmar si sigue grabando.');
 set('signal', 'Estado sin confirmar'); set('live-label', 'SIN CONFIRMAR');
 $('signal-dot').classList.remove('online');
 set('updated', 'Sin conexión · los datos pueden estar desactualizados');
 notice('No se puede consultar la Raspberry. Comprueba la conexión de red o Tailscale y que la aplicación esté funcionando.');
}
async function update() {
 if (polling) return;
 polling = true;
 try {
  const response = await fetch('/estado', {cache:'no-store', signal:AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error('Estado no disponible');
  const s = await response.json();
  if (typeof s.grabando !== 'boolean' || typeof s.fotogramas !== 'number') throw new Error('Estado no válido');
  set('connection-text', 'Raspberry conectada'); $('connection').classList.remove('error-text');
  set('record-state', s.error ? 'Detenida' : s.solo_directo ? 'Solo directo' : s.grabando ? 'Grabando' : 'Detenida');
  $('record-card').classList.toggle('pending', !s.grabando || Boolean(s.error));
  set('record-note', s.error ? 'Revisa el aviso para más información.' : s.solo_directo ? 'La grabación está desactivada.' : s.grabando ? 'Grabación continua en tu Raspberry.' : 'No hay una grabación en curso.');
  const sistema = s.sistema || {};
  const temp = sistema.temperatura_cpu_c, uptime = sistema.encendida_segundos;
  set('system-temp', typeof temp === 'number' && Number.isFinite(temp) ? temp.toLocaleString('es-ES', {maximumFractionDigits:1}) + ' °C' : 'No disponible');
  const minutos = Math.floor(uptime / 60);
  set('system-uptime', typeof uptime === 'number' && Number.isFinite(uptime) ? (minutos >= 1440 ? Math.floor(minutos / 1440) + ' d ' : '') + Math.floor(minutos % 1440 / 60) + ' h ' + minutos % 60 + ' min' : 'No disponible');
  set('system-error', s.error || 'Sin errores de grabación detectados');
  const m = s.movimiento || {};
  set('motion-state', m.error ? 'Detección no disponible' : !m.disponible ? 'Esperando imágenes' : m.calibrando ? 'Calibrando…' : m.activo ? 'Movimiento detectado' : 'Sin movimiento');
  set('motion-last', m.error || (m.ultimo ? 'Última actividad: ' + new Date(m.ultimo * 1000).toLocaleString('es-ES') : 'Todavía no se ha detectado actividad en este arranque.'));
  if (document.activeElement !== $('motion-sensitivity') && m.sensibilidad) $('motion-sensitivity').value = m.sensibilidad;
  const seconds = s.segmento_segundos;
  set('duration', seconds >= 3600 ? (seconds / 3600).toLocaleString('es-ES') + ' h' : seconds >= 60 ? (seconds / 60).toLocaleString('es-ES') + ' min' : seconds + ' s');
  set('files', number.format(s.archivos)); set('deleted', number.format(s.borrados_automaticos));
  set('reclaimed', amount(s.espacio_liberado_mb));
  set('free', s.espacio_libre_mb == null ? '—' : (s.espacio_libre_mb / 1024).toLocaleString('es-ES', {minimumFractionDigits:1, maximumFractionDigits:1}));
  set('storage-sub', s.espacio_libre_mb == null ? 'Espacio aún no medido' : 'Espacio libre en la Raspberry');
  set('policy', 'Si quedan menos de ' + amount(s.reserva_mb) + ', se borran los vídeos más antiguos hasta recuperar ' + amount(s.objetivo_mb) + '.');
  set('filename', s.archivo_actual || 'Sin archivo en curso');
  set('session', s.sesion ? 'Sesión: ' + s.sesion : 'Todavía no hay una sesión de grabación');
  stalled = previousFrames === s.fotogramas ? stalled + 1 : 0; previousFrames = s.fotogramas;
  const active = $('playback').hidden && s.fotogramas > 0 && stalled < 3 && !imageFailed;
  set('signal', !$('playback').hidden ? 'Directo pausado en este visor' : active ? 'Señal activa' : imageFailed ? 'Directo desconectado' : 'Esperando imagen');
  set('live-label', !$('playback').hidden ? 'VISOR PAUSADO' : active ? 'EN DIRECTO' : 'ESPERANDO SEÑAL');
  $('signal-dot').classList.toggle('online', active);
  notice(s.error || (imageFailed ? 'El visor ha perdido la conexión. Pulsa Reconectar para volver a cargar el directo.' : stalled >= 3 ? 'La cámara no está enviando nuevos fotogramas. Comprueba la terminal de la Raspberry.' : ''));
  set('updated', 'Última lectura · ' + new Date().toLocaleTimeString('es-ES', {hour12:false}));
 } catch (error) { disconnected(); }
 finally { polling = false; }
}
$('stream').addEventListener('error', () => { imageFailed = true; set('signal', 'Directo desconectado'); set('live-label', 'SIN SEÑAL'); $('signal-dot').classList.remove('online'); notice('El visor ha perdido la conexión. Pulsa Reconectar para volver a cargar el directo.'); });
$('reconnect').addEventListener('click', () => {
 imageFailed = false; previousFrames = null; stalled = 0;
 $('stream').src = '/directo?reconectar=' + Date.now();
 set('signal', 'Reconectando…'); update();
});
if (!document.fullscreenEnabled) $('fullscreen').hidden = true;
$('fullscreen').addEventListener('click', async () => {
 try { if (document.fullscreenElement) await document.exitFullscreen(); else await $('video').requestFullscreen(); }
 catch (error) { notice('Este navegador no permite abrir el visor a pantalla completa.'); }
});
$('exit-fullscreen').addEventListener('click', () => document.exitFullscreen());
document.addEventListener('fullscreenchange', () => $('fullscreen').setAttribute('aria-label', document.fullscreenElement ? 'Salir de pantalla completa' : 'Abrir directo a pantalla completa'));
document.querySelectorAll('.nav a').forEach(link => link.addEventListener('click', () => {
 document.querySelectorAll('.nav a').forEach(item => item.classList.toggle('active', item === link));
}));
tick(); update(); setInterval(tick, 1000); setInterval(update, 3000);

export function pausarDirecto() {
 $('stream').removeAttribute('src');
}

export function reanudarDirecto() {
 imageFailed = false;
 $('stream').src = '/directo?reanudar=' + Date.now();
}

$('motion-sensitivity').addEventListener('change', async () => {
 const selector = $('motion-sensitivity'); selector.disabled = true;
 try {
  const response = await fetch('/api/movimiento/sensibilidad', {method:'POST', headers:{'Content-Type':'application/json','X-PiCameraRecorder':'1'}, body:JSON.stringify({sensibilidad:selector.value}), signal:AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error('No se pudo cambiar la sensibilidad.');
  set('motion-notice', 'Sensibilidad cambiada. Se mantiene hasta reiniciar la aplicación.');
 } catch (error) { set('motion-notice', 'No se pudo confirmar el cambio. Se mostrará la sensibilidad del servidor en la próxima lectura.'); }
 finally { selector.disabled = false; update(); }
});
