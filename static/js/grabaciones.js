import { $, number, set } from './utilidades.js';
import { pausarDirecto, reanudarDirecto } from './panel.js?v=movimiento1';
let libraryPage = 1, libraryPages = 1, libraryRequest = 0;
let playingItem = null, deleting = false, savingStar = false;
const media = $('recording-video');
function fileSize(bytes) {
 if (bytes >= 1024**3) return (bytes / 1024**3).toLocaleString('es-ES', {maximumFractionDigits:2}) + ' GiB';
 return (bytes / 1024**2).toLocaleString('es-ES', {maximumFractionDigits:1}) + ' MiB';
}
function sessionLabel(s) { return s.slice(8,10) + '/' + s.slice(5,7) + '/' + s.slice(0,4) + ' · ' + s.slice(11,19).replaceAll('-', ':') + ' · ' + s.slice(20); }
function stopPlayback(resume = true) {
 const wasOpen = !$('playback').hidden;
 playingItem = null;
 $('motion-events').replaceChildren();
 media.pause(); media.removeAttribute('src'); media.load(); $('playback').hidden = true;
 if (wasOpen && resume) reanudarDirecto();
}
function openRecording(item) {
 stopPlayback(false);
 playingItem = item;
 loadMotion(item);
 pausarDirecto();
 set('playback-name', item.archivo); set('playback-session', 'Sesión ' + sessionLabel(item.sesion));
 set('playback-status', 'Conectando con el vídeo…');
 $('player-download').href = item.descarga;
 $('playback').hidden = false; media.src = item.url; media.load();
 $('playback').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block:'start'});
 media.play().catch(() => { if (!media.error) set('playback-status', 'Pulsa reproducir para ver el vídeo.'); });
}
media.addEventListener('loadedmetadata', () => {
 const duration = media.duration;
 set('playback-status', Number.isFinite(duration) ? 'Duración: ' + Math.floor(duration / 60) + ' min ' + Math.floor(duration % 60) + ' s · Puedes avanzar con la barra del reproductor.' : 'Vídeo listo para reproducir.');
});
media.addEventListener('error', () => { if (media.hasAttribute('src')) set('playback-status', 'No se puede reproducir este vídeo. Puede haberse eliminado por la limpieza automática o no ser compatible con este navegador. Actualiza la lista o descarga el MP4.'); });
$('close-playback').addEventListener('click', stopPlayback);
async function deleteRecording(item, button) {
 if (deleting) return;
 if (!window.confirm('¿Eliminar definitivamente ' + item.archivo + '\nSesión: ' + sessionLabel(item.sesion) + '\nEsta acción no se puede deshacer.')) return;
 deleting = true; button.disabled = true;
 try {
  const response = await fetch('/api/grabaciones/' + encodeURIComponent(item.sesion) + '/' + encodeURIComponent(item.archivo), {method:'DELETE', headers:{'X-PiCameraRecorder':'1'}, signal:AbortSignal.timeout(10000)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'No se pudo eliminar la grabación.');
  if (playingItem?.sesion === item.sesion && playingItem?.archivo === item.archivo) stopPlayback();
  set('delete-status', 'Grabación eliminada. El espacio libre se actualizará en unos segundos.');
  await loadLibrary();
 } catch (error) {
  set('delete-status', (error.name === 'TimeoutError' ? 'No se pudo confirmar el borrado. Actualiza la lista antes de reintentarlo.' : error.message));
 } finally { deleting = false; button.disabled = false; }
}
async function toggleImportant(item, button) {
 if (savingStar) return;
 savingStar = true; ++libraryRequest; button.disabled = true;
 try {
  const response = await fetch('/api/grabaciones/' + encodeURIComponent(item.sesion) + '/' + encodeURIComponent(item.archivo) + '/importante', {
   method:'PUT', headers:{'X-PiCameraRecorder':'1', 'Content-Type':'application/json'},
   body:JSON.stringify({importante:!item.importante}), signal:AbortSignal.timeout(10000)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'No se pudo guardar la estrella.');
  set('delete-status', result.importante ? '★ Vídeo importante: la limpieza automática lo conservará.' : 'Estrella retirada. La limpieza automática podrá borrar este vídeo cuando falte espacio.');
 } catch (error) {
  set('delete-status', error.name === 'TimeoutError' ? 'No se pudo confirmar el cambio. Consulta la estrella actual antes de reintentarlo.' : error.message);
 } finally { savingStar = false; button.disabled = false; await loadLibrary(); }
}
async function loadLibrary() {
 if (savingStar) return;
 const requestId = ++libraryRequest;
 const button = $('refresh-library'); button.disabled = true;
 const params = new URLSearchParams({pagina:libraryPage, fecha:$('filter-date').value, sesion:$('filter-session').value});
 try {
  const response = await fetch('/api/grabaciones?' + params, {cache:'no-store', signal:AbortSignal.timeout(7000)});
  if (!response.ok) throw new Error('No se pudo cargar el catálogo');
  const data = await response.json();
  if (requestId !== libraryRequest) return;
  libraryPage = data.pagina; libraryPages = data.paginas;
  const selected = $('filter-session').value;
  $('filter-session').replaceChildren(new Option('Todas las sesiones', ''));
  for (const session of data.sesiones) $('filter-session').append(new Option(sessionLabel(session), session));
  if (selected && !data.sesiones.includes(selected)) $('filter-session').append(new Option(sessionLabel(selected), selected));
  $('filter-session').value = selected;
  const fragment = document.createDocumentFragment();
  for (const item of data.items) {
   const row = document.createElement('tr');
   const file = document.createElement('td');
   const name = document.createElement('strong'); name.textContent = item.archivo;
   const session = document.createElement('small'); session.textContent = sessionLabel(item.sesion);
   file.append(name, session);
   const size = document.createElement('td'); size.textContent = fileSize(item.bytes);
   const status = document.createElement('td'); const badge = document.createElement('span');
   badge.className = 'tag ' + (item.en_curso || item.preparando ? 'state-open' : 'state-closed'); badge.textContent = item.en_curso ? 'En curso' : item.preparando ? 'Preparando' : 'Disponible'; status.append(badge);
   const actions = document.createElement('td'); const group = document.createElement('div'); group.className = 'recording-actions';
   const star = document.createElement('button'); star.type = 'button'; star.className = 'btn important-toggle';
   star.textContent = item.importante ? '★ Importante' : '☆ Proteger'; star.setAttribute('aria-pressed', String(Boolean(item.importante)));
   star.setAttribute('aria-label', (item.importante ? 'Quitar estrella de ' : 'Marcar como importante ') + item.sesion + ' ' + item.archivo);
   star.title = item.importante ? 'Protegido de la limpieza automática. Pulsa para quitar la estrella.' : 'Conservar este vídeo aunque falte espacio.';
   star.addEventListener('click', () => toggleImportant(item, star)); group.append(star);
   if (item.en_curso) { const hint = document.createElement('small'); hint.textContent = 'Disponible al cerrar el archivo'; group.append(hint); }
   else {
    const play = document.createElement('button'); play.type = 'button'; play.className = 'btn'; play.textContent = 'Reproducir'; play.setAttribute('aria-label', 'Reproducir ' + item.sesion + ' ' + item.archivo); play.disabled = Boolean(item.preparando); play.textContent = item.preparando ? 'Preparando…' : 'Reproducir'; play.addEventListener('click', () => openRecording(item));
    const download = document.createElement('a'); download.href = item.descarga; download.className = 'btn'; download.textContent = 'Descargar'; download.setAttribute('download', ''); download.setAttribute('aria-label', 'Descargar ' + item.sesion + ' ' + item.archivo);
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn'; remove.textContent = 'Eliminar'; remove.setAttribute('aria-label', 'Eliminar ' + item.sesion + ' ' + item.archivo); remove.addEventListener('click', () => deleteRecording(item, remove));
    remove.disabled = Boolean(item.importante); if (item.importante) remove.title = 'Quita la estrella antes de eliminar este vídeo.';
    group.append(play, download, remove); if (item.preparacion_error) { const hint = document.createElement('small'); hint.textContent = item.preparacion_error; group.append(hint); }
   }
   actions.append(group); row.append(file, size, status, actions); fragment.append(row);
  }
  $('recordings-rows').replaceChildren(fragment);
  set('library-status', data.total ? number.format(data.total) + ' archivo(s) conservado(s) · Más recientes primero' : 'No hay grabaciones para estos filtros. Prueba con otra fecha o espera a que termine el primer archivo.');
  $('library-status').classList.remove('error-text');
  set('recordings-page', 'Página ' + data.pagina + ' de ' + data.paginas);
  $('prev-recordings').disabled = libraryPage <= 1; $('next-recordings').disabled = libraryPage >= libraryPages;
 } catch (error) {
  if (requestId !== libraryRequest) return;
  $('recordings-rows').replaceChildren(); $('prev-recordings').disabled = true; $('next-recordings').disabled = true;
  set('library-status', 'No se pudo cargar la lista. Comprueba tu conexión y pulsa Actualizar.'); $('library-status').classList.add('error-text');
 } finally { if (requestId === libraryRequest) button.disabled = false; }
}
$('refresh-library').addEventListener('click', loadLibrary);
for (const id of ['filter-date', 'filter-session']) $(id).addEventListener('change', () => { libraryPage = 1; if (id === 'filter-date') $('filter-session').value = ''; loadLibrary(); });
$('clear-filters').addEventListener('click', () => { $('filter-date').value = ''; $('filter-session').value = ''; libraryPage = 1; loadLibrary(); });
$('prev-recordings').addEventListener('click', () => { if (libraryPage > 1) { libraryPage--; loadLibrary(); } });
$('next-recordings').addEventListener('click', () => { if (libraryPage < libraryPages) { libraryPage++; loadLibrary(); } });
loadLibrary(); setInterval(() => { if (!document.hidden) loadLibrary(); }, 15000);
function eventTime(seconds) {
 const n = Math.floor(seconds); return Math.floor(n/60).toString().padStart(2,'0') + ':' + (n%60).toString().padStart(2,'0');
}
async function loadMotion(item) {
 set('motion-video-status', 'Cargando eventos…'); $('motion-events').replaceChildren();
 try {
  const response = await fetch('/api/grabaciones/' + encodeURIComponent(item.sesion) + '/' + encodeURIComponent(item.archivo) + '/movimiento', {cache:'no-store',signal:AbortSignal.timeout(7000)});
  if (!response.ok) throw new Error('No se pudieron cargar los eventos.');
  const data = await response.json();
  if (playingItem !== item) return;
  set('motion-video-status', !data.disponible ? 'Esta grabación no dispone de análisis de movimiento. Se analiza desde que se activó esta función.' : data.total ? data.total + ' evento(s). Pulsa un momento para ver los 3 segundos anteriores. Tiempos aproximados; se muestran hasta 500 eventos.' : 'No se detectó movimiento en esta grabación.');
  for (const event of data.eventos) {
   const button = document.createElement('button'); button.type = 'button'; button.className = 'btn'; button.textContent = 'Movimiento ' + eventTime(event.inicio) + '–' + eventTime(event.fin);
   button.addEventListener('click', () => {
    const seek = () => { if (playingItem !== item) return; media.currentTime = Math.min(Math.max(0,event.inicio-3),Number.isFinite(media.duration) ? Math.max(0,media.duration-.1) : event.inicio); media.play().catch(() => {}); };
    if (media.readyState >= 1) seek(); else media.addEventListener('loadedmetadata',seek,{once:true});
   });
   $('motion-events').append(button);
  }
 } catch (error) { if (playingItem === item) set('motion-video-status', 'No se pudieron consultar los eventos. Cierra el reproductor y vuelve a abrirlo para reintentar.'); }
}
