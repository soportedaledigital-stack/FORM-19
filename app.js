'use strict';
const $ = id => document.getElementById(id);
const ORDER = [40, 41, 42].flatMap(row => [...'EFGHIJK'].map(col => col + row));
const gate = new CaptureGate();
let values = {}, series = null, stream = null, running = false, loaded = false;
let selectedRow = 40, timer = null, activeScan = null, ocrController = null;
let epoch = 0, starting = false, errorCount = 0, operationBusy = false;

function message(id, text, type = '') {
  const node = $(id); node.hidden = false; node.className = 'message ' + type; node.textContent = text;
}
function showValue(value) {
  if (value === null || value === undefined) return '—';
  const number = Number(String(value).replace(',', '.'));
  if (!Number.isFinite(number)) return String(value);
  const places = Number(number.toFixed(3)) === number ? 3 : 4;
  return number.toFixed(places).replace('.', ',');
}
function target() {
  const start = Math.max(0, [40, 41, 42].indexOf(selectedRow)) * 7;
  return ORDER.slice(start).find(addr => values[addr] == null) || null;
}
function draw() {
  const next = target(); $('target').textContent = next || 'Grupo completo';
  $('progress').textContent = `${ORDER.filter(a => values[a] != null).length} / 21 lecturas`;
  $('cells').replaceChildren();
  for (const row of [40, 41, 42]) {
    const heading = document.createElement('div'); heading.className = 'rowname';
    heading.textContent = `Referencia ${row === 40 ? '0,2982' : row === 41 ? '0,7915' : '1,4878'} g/L`;
    const grid = document.createElement('div'); grid.className = 'grid';
    for (const col of 'EFGHIJK') {
      const addr = col + row, value = values[addr], cell = document.createElement('div');
      cell.className = `cell ${value != null ? 'used' : ''} ${addr === next ? 'active' : ''}`;
      cell.dataset.cell = addr; cell.append(document.createTextNode(addr));
      const line = document.createElement('div'), bold = document.createElement('b'); bold.textContent = showValue(value);
      line.append(bold); cell.append(line); grid.append(cell);
    }
    $('cells').append(heading, grid);
  }
}
function controls() {
  $('start').disabled = !loaded || running || starting || Boolean(activeScan) || operationBusy;
  $('stop').disabled = !running && !starting;
  $('row').disabled = running || starting || Boolean(activeScan) || operationBusy;
  $('reset').disabled = operationBusy;
  for (const id of ['downloadExcel', 'downloadEvidence', 'downloadAudit']) {
    $(id).classList.toggle('disabled', !loaded || operationBusy);
    $(id).setAttribute('aria-disabled', String(!loaded || operationBusy));
  }
}
async function checkedResponse(url, options = {}, timeoutMs = 30000) {
  const controller = options.signal ? null : new AbortController();
  const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options, signal: options.signal || controller.signal });
    if (!response.ok) {
      const type = response.headers.get('content-type') || '';
      let detail = '';
      if (type.includes('application/json')) { const data = await response.json(); detail = data.error || ''; }
      const error = new Error(detail || `El servidor respondió ${response.status}. No se completó la operación.`);
      error.status = response.status;
      throw error;
    }
    return response;
  } finally { if (timeout) clearTimeout(timeout); }
}
async function api(url, options = {}, timeoutMs = 30000) {
  const response = await checkedResponse(url, options, timeoutMs);
  if (!(response.headers.get('content-type') || '').includes('application/json')) {
    throw Error('El servidor no devolvió datos válidos. Compruebe que se desplegó la versión V5.');
  }
  return response.json();
}
function jsonPost(data) { return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }; }
function showPhoto(saved) {
  $('last').textContent = saved.value + ' g/L';
  $('lastPhoto').src = saved.photo + '?v=' + encodeURIComponent(saved.timestamp || Date.now());
  $('photoCaption').textContent = `Foto guardada · ${saved.cell} · ${saved.value} g/L`;
  $('photoPanel').hidden = false;
}
async function status() {
  loaded = false; controls();
  try {
    const data = await api('/api/status');
    if (!data.ok || !data.uploaded || !data.values || !data.series) throw Error('No se pudo preparar la plantilla FORM19.');
    values = data.values; series = data.series; loaded = true;
    $('sessionInfo').textContent = `FORM19 disponible · ${data.version}`;
    if (data.last) { gate.saved(data.last.value); showPhoto(data.last); }
    draw();
    message('saveMsg', 'Archivo de trabajo listo. Puede iniciar la captura o descargar el FORM19.', 'success');
    if (!data.ocr_available) message('ocrMsg', 'Tesseract no está disponible. La descarga funciona, pero debe corregirse el despliegue para usar la cámara.', 'warning');
  } catch (error) {
    $('sessionInfo').textContent = 'No se pudo preparar el FORM19';
    message('saveMsg', error.message, 'warning');
    if (error.status === 401 || error.status === 410) { $('auth').hidden = false; message('loginMsg', error.message, 'warning'); }
  } finally { controls(); }
}
$('login').onclick = async () => {
  $('login').disabled = true;
  try {
    await api('/api/login', jsonPost({ password: $('password').value }));
    $('password').value = ''; $('auth').hidden = true; $('workspace').hidden = false;
    gate.reset(); await status();
  } catch (error) { message('loginMsg', error.message, 'warning'); }
  finally { $('login').disabled = false; }
};
$('password').addEventListener('keydown', event => { if (event.key === 'Enter') $('login').click(); });
$('row').onchange = () => { selectedRow = Number($('row').value); draw(); };

function roiBounds() {
  const width = Number($('region').value) / 100, height = Number($('height').value) / 100;
  const x = Math.max(0, Math.min(1 - width, Number($('horizontal').value) / 100 - width / 2));
  const y = Math.max(0, Math.min(1 - height, Number($('vertical').value) / 100 - height / 2));
  return { x, y, width, height };
}
function updateROI() {
  const b = roiBounds();
  Object.assign($('roi').style, { left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.width * 100}%`, height: `${b.height * 100}%` });
  for (const id of ['region', 'height', 'horizontal', 'vertical']) $(id + 'Label').textContent = $(id).value + '%';
  // Never combine confirmation frames from two different crops.
  gate.pending = null; gate.seen = 0;
}
for (const id of ['region', 'height', 'horizontal', 'vertical']) $(id).oninput = updateROI;
updateROI();

function cameraError(error) {
  const descriptions = {
    NotAllowedError: 'No hay permiso para usar la cámara. Permítalo en la configuración de este sitio y abra la URL HTTPS en el navegador.',
    NotFoundError: 'No se encontró una cámara disponible.',
    NotReadableError: 'La cámara está ocupada o no se puede abrir. Cierre otras aplicaciones que la utilicen.',
    OverconstrainedError: 'La cámara no admite la configuración solicitada.'
  };
  return descriptions[error.name] || error.message || 'No fue posible abrir la cámara.';
}
async function openCamera(currentEpoch) {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw Error('La cámara requiere HTTPS y un navegador con permiso de cámara. Abra directamente la dirección de Render, no un archivo HTML.');
  let acquired;
  try {
    acquired = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
  } catch (error) {
    if (error.name !== 'OverconstrainedError') throw error;
    acquired = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  }
  if (epoch !== currentEpoch) { acquired.getTracks().forEach(track => track.stop()); return false; }
  stream = acquired; $('video').srcObject = stream;
  try {
    await $('video').play();
    await new Promise((resolve, reject) => {
      const until = Date.now() + 10000;
      const check = () => {
        if (epoch !== currentEpoch) return reject(Error('Inicio de cámara cancelado.'));
        if ($('video').videoWidth && $('video').videoHeight && $('video').readyState >= 2) return resolve();
        if (Date.now() > until) return reject(Error('La cámara no entregó una imagen. Revise los permisos e inténtelo nuevamente.'));
        setTimeout(check, 80);
      };
      check();
    });
    return true;
  } catch (error) { acquired.getTracks().forEach(track => track.stop()); stream = null; throw error; }
}
async function frame() {
  const video = $('video');
  if (!video.videoWidth || video.readyState < 2) throw Error('Esperando una imagen válida de la cámara.');
  const bounds = roiBounds(), canvas = document.createElement('canvas');
  const sw = video.videoWidth * bounds.width, sh = video.videoHeight * bounds.height;
  const scale = Math.min(1.5, 1200 / sw);
  canvas.width = Math.max(16, Math.round(sw * scale)); canvas.height = Math.max(16, Math.round(sh * scale));
  canvas.getContext('2d').drawImage(video, bounds.x * video.videoWidth, bounds.y * video.videoHeight, sw, sh, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.94));
  if (!blob) throw Error('El navegador no pudo tomar la fotografía.');
  return blob;
}
function stopCamera(showMessage = true) {
  running = false; starting = false; epoch += 1; clearTimeout(timer); timer = null;
  if (ocrController) ocrController.abort();
  if (stream) { stream.getTracks().forEach(track => track.stop()); stream = null; }
  $('video').srcObject = null; $('video').parentElement.style.minHeight = '180px'; $('roi').hidden = true; $('cameraPlaceholder').hidden = false;
  gate.pending = null; gate.seen = 0; controls();
  if (showMessage) message('ocrMsg', 'Captura detenida. Las lecturas ya guardadas se conservan.');
}
async function halt(showMessage = true) {
  stopCamera(showMessage);
  if (activeScan) await activeScan.catch(() => {});
  controls();
}
async function scanOnce(currentEpoch) {
  let saving = false;
  try {
    const addr = target();
    if (!addr) { stopCamera(false); message('ocrMsg', 'Las celdas del grupo seleccionado y los grupos siguientes están completas. Descargue el FORM19.', 'success'); return; }
    const blob = await frame();
    if (!running || epoch !== currentEpoch) return;
    const fd = new FormData(); fd.append('image', blob, 'lectura.jpg'); fd.append('series', series);
    ocrController = new AbortController();
    const deadline = setTimeout(() => ocrController?.abort(), 25000);
    let detected;
    message('ocrMsg', 'Fotografía tomada. Analizando el display…');
    try { detected = await api('/api/ocr', { method: 'POST', body: fd, signal: ocrController.signal }); }
    finally { clearTimeout(deadline); ocrController = null; }
    if (!running || epoch !== currentEpoch) return;
    errorCount = 0;
    $('ocrDetail').textContent = `Texto detectado: ${(detected.raw || []).join(' | ') || '(ninguno)'}\nDuración del último análisis: ${((detected.elapsed_ms || 0) / 1000).toFixed(1)} s`;
    const action = gate.observe(detected.detected, detected.blank === true);
    if (action === 'searching') {
      message('ocrMsg', gate.armed && gate.lastSaved && gate.blanks >= 3 ? 'Listo para otra medición. Vuelva a mostrar el display.' : detected.warning || 'Buscando un número legible con decimal…', 'warning'); return;
    }
    if (action === 'duplicate') { message('ocrMsg', `${detected.detected} g/L ya se registró. Esperando una nueva medición.`); return; }
    if (action === 'confirming') { message('ocrMsg', `Detectado ${detected.detected} g/L. Comprobando con la siguiente fotografía…`); return; }
    if (!detected.token) throw Error('La imagen no tiene identificador de guardado. Actualice todos los archivos a V5.');
    message('ocrMsg', `Guardando foto y lectura ${detected.detected} g/L en ${addr}…`);
    // Do not abort a save: wait for its result before reset/logout/download.
    saving = true;
    const saved = await api('/api/save', jsonPost({ cell: addr, value: detected.detected, token: detected.token, series }));
    values[saved.cell] = Number(saved.value.replace(',', '.'));
    gate.saved(saved.value); showPhoto(saved); draw();
    message('saveMsg', `${saved.cell} = ${saved.value} g/L. Lectura y fotografía guardadas. Siguiente celda: ${target() || 'FIN'}.`, 'success');
    message('ocrMsg', `Guardado automático confirmado en ${saved.cell}. Esperando otra medición.`, 'success');
    if (!target()) { stopCamera(false); message('ocrMsg', 'Grupo completado. Descargue el FORM19 y sus fotografías.', 'success'); }
  } catch (error) {
    gate.pending = null; gate.seen = 0;
    if (!running || epoch !== currentEpoch) return;
    errorCount += 1;
    const text = error.name === 'AbortError' ? 'El servidor tardó demasiado en analizar la imagen. Se volverá a intentar.' : error.message;
    message('ocrMsg', text, 'warning');
    // A failed/uncertain save can have committed on the server: stop rather than
    // blindly retrying into a new cell. The next status reload reveals the truth.
    if ([401, 409, 410, 503].includes(error.status) || errorCount >= 3 || saving) {
      stopCamera(false); message('ocrMsg', text + ' La captura se detuvo; revise el estado antes de continuar.', 'warning');
      if (error.status === 401) { loaded = false; $('auth').hidden = false; }
    }
  }
}
function scheduleScan(currentEpoch) {
  if (!running || epoch !== currentEpoch || activeScan) return;
  activeScan = scanOnce(currentEpoch).finally(() => {
    activeScan = null; controls();
    if (running && epoch === currentEpoch) timer = setTimeout(() => scheduleScan(currentEpoch), errorCount ? 1800 : 650);
  });
}
$('start').onclick = async () => {
  if (!loaded || running || starting || activeScan) return;
  if (!target()) { message('ocrMsg', 'No quedan celdas vacías desde el grupo seleccionado. Elija otro grupo o comience una nueva serie.', 'warning'); return; }
  starting = true; controls();
  const currentEpoch = ++epoch;
  try {
    // Refresh persisted readings before resuming, including a save whose response was lost.
    const fresh = await api('/api/status');
    if (epoch !== currentEpoch) return;
    if (fresh.series !== series) throw Error('La serie cambió en otra pestaña. Actualice la página.');
    values = fresh.values; if (fresh.last) gate.saved(fresh.last.value); draw();
    if (!await openCamera(currentEpoch) || epoch !== currentEpoch) return;
    running = true; starting = false; errorCount = 0;
    $('video').parentElement.style.minHeight = '0'; $('roi').hidden = false; $('cameraPlaceholder').hidden = true; controls();
    scheduleScan(currentEpoch);
  } catch (error) { stopCamera(false); message('ocrMsg', cameraError(error), 'warning'); }
  finally { starting = false; controls(); }
};
$('stop').onclick = () => halt();

async function downloadFile(event, filename) {
  event.preventDefault();
  const endpoint = event.currentTarget.href;
  if (!loaded || operationBusy) return;
  operationBusy = true; controls();
  try {
    await halt();
    message('downloadMsg', 'Preparando la descarga…');
    const response = await checkedResponse(endpoint);
    if ((response.headers.get('content-type') || '').includes('application/json')) throw Error('El servidor no devolvió el archivo solicitado.');
    const blob = await response.blob();
    if (!blob.size) throw Error('El archivo recibido está vacío.');
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 120000);
    message('downloadMsg', 'Archivo preparado. Revise las descargas de su navegador.', 'success');
  } catch (error) { message('downloadMsg', error.message, 'warning'); }
  finally { operationBusy = false; controls(); }
}
$('downloadExcel').onclick = event => downloadFile(event, 'FORM19_LECTURAS_CAPTURADAS.xlsm');
$('downloadEvidence').onclick = event => downloadFile(event, 'FORM19_EXCEL_FOTOS_HISTORIAL.zip');
$('downloadAudit').onclick = event => downloadFile(event, 'FORM19_TRAZABILIDAD.csv');
$('reset').onclick = async () => {
  if (!confirm('¿Empezar una nueva serie y borrar las lecturas y fotos actuales? Descargue antes su trabajo.')) return;
  operationBusy = true; controls(); await halt();
  try {
    const data = await api('/api/reset', { method: 'POST' });
    values = data.values; series = data.series; loaded = true; selectedRow = 40; $('row').value = '40';
    gate.reset(); $('last').textContent = '—'; $('photoPanel').hidden = true; $('lastPhoto').removeAttribute('src');
    draw(); message('saveMsg', 'Nueva serie preparada. No hay lecturas ni fotos de la serie anterior.', 'success');
  } catch (error) { message('saveMsg', error.message, 'warning'); }
  finally { operationBusy = false; controls(); }
};
$('logout').onclick = async () => {
  if (ORDER.some(a => values[a] != null) && !confirm('¿Salir? Asegúrese de haber descargado el FORM19 y las fotos.')) return;
  operationBusy = true; controls(); await halt();
  try { await api('/api/logout', { method: 'POST' }); location.reload(); }
  catch (error) { message('saveMsg', error.message, 'warning'); operationBusy = false; controls(); }
};
document.addEventListener('visibilitychange', () => { if (document.hidden && (running || starting)) halt(); });
window.addEventListener('pagehide', () => stopCamera(false));
if (document.body.dataset.logged === 'true') status();
