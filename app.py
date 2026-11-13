"""DALEDIGITAL FORM19 V5 — automatic capture and protected XLSM download."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time

from flask import Flask, jsonify, request, send_file, render_template, session
from werkzeug.exceptions import HTTPException
from form19_core import (READINGS, MAX_IMAGE_BYTES, is_valid_book, get_values,
                         patch_cell, parse_value, format_value, decode_image,
                         jpeg_bytes, recognize_display)

VERSION = 'V5 · 2026-11-13'
ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / 'data' / 'FORM19_PLANTILLA.xlsm'
BASE = Path(os.environ.get('FORM19_STORAGE', str(Path(tempfile.gettempdir()) / 'daledigital_form19_v4')))
BASE.mkdir(parents=True, exist_ok=True)
GUARD = threading.RLock()
OCR_LOCK = threading.BoundedSemaphore(1)
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=10 * 1024 * 1024,
                  SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=os.environ.get('RENDER', '').lower() == 'true',
                  SESSION_COOKIE_SAMESITE='Lax',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
                  SEND_FILE_MAX_AGE_DEFAULT=0)


class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def authorized():
    return bool(os.environ.get('APP_PASSWORD', 'admin').strip()) and session.get('authenticated') is True


def paths():
    sid = session.get('sid', '')
    if not re.fullmatch(r'[a-f0-9]{32}', sid):
        raise AppError('La sesión expiró. Inicie sesión nuevamente.', 401)
    return BASE / (sid + '.xlsm'), BASE / (sid + '.csv'), BASE / (sid + '-capturas')


def template_data():
    if not TEMPLATE.is_file():
        raise AppError('Falta data/FORM19_PLANTILLA.xlsm en el servidor. Suba la carpeta data y vuelva a desplegar con el Dockerfile V5.', 503)
    data = TEMPLATE.read_bytes()
    try:
        is_valid_book(data)
    except Exception as exc:
        raise AppError('La plantilla FORM19 no es válida. Restaure el archivo XLSM incluido en el proyecto.', 503) from exc
    return data


def ensure_workbook(create=False):
    with GUARD:
        book, log, assets = paths()
        if not book.exists():
            if not create:
                raise AppError('La copia temporal de esta sesión ya no está disponible. No se ha creado una copia vacía en su lugar. Inicie sesión de nuevo para comenzar otra serie.', 410)
            atomic_write(book, template_data())
        assets.mkdir(exist_ok=True)
        meta = assets / 'session.json'
        if not meta.exists():
            atomic_write(meta, json_bytes({'series': secrets.token_hex(16), 'receipts': {}}))
        return book, log, assets


def metadata(assets):
    return json.loads((assets / 'session.json').read_text(encoding='utf-8'))


def check_series(meta, value):
    if not value or not hmac.compare_digest(str(value), meta['series']):
        raise AppError('La serie cambió. Actualice la página antes de capturar más lecturas.', 409)


@app.before_request
def protect():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('Origin')
        if origin and urlparse(origin).netloc != request.host:
            raise AppError('Solicitud rechazada: origen diferente al de la aplicación.', 403)
    if request.path.startswith('/api/') and request.path != '/api/login' and not authorized():
        raise AppError('La sesión expiró o no ha iniciado sesión. Ingrese nuevamente.', 401)


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.path.startswith('/api/') or request.path == '/':
        response.headers['Cache-Control'] = 'no-store, private'
    return response


@app.errorhandler(Exception)
def errors(exc):
    if isinstance(exc, AppError):
        return jsonify(error=str(exc)), exc.status
    if isinstance(exc, HTTPException):
        text = 'La fotografía supera el tamaño permitido.' if exc.code == 413 else exc.description
        return jsonify(error=text), exc.code
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    app.logger.exception('Error FORM19')
    return jsonify(error='No se pudo completar la operación en el servidor. Sus lecturas no se han confirmado como guardadas. Revise los registros del servicio.'), 500


@app.get('/health')
def health():
    # Do not report a healthy deployment when the template is absent.
    if not TEMPLATE.is_file() or not shutil.which('tesseract'):
        return jsonify(ok=False, template=TEMPLATE.is_file(), ocr=bool(shutil.which('tesseract')), version=VERSION), 503
    return jsonify(ok=True, version=VERSION)


@app.get('/')
def home():
    return render_template('index.html', logged=authorized(), version=VERSION)


@app.post('/api/login')
def login():
    password = os.environ.get('APP_PASSWORD', 'admin').strip()
    data = request.get_json(silent=True) or {}
    candidate = str(data.get('password', ''))
    if not password or not hmac.compare_digest(candidate.encode('utf-8'), password.encode('utf-8')):
        raise AppError('Contraseña incorrecta o APP_PASSWORD sin configurar.', 401)
    template_data()  # Validate before setting a successful authentication cookie.
    old_sid = session.get('sid', '')
    resume = authorized() and re.fullmatch(r'[a-f0-9]{32}', old_sid) and (BASE / (old_sid + '.xlsm')).exists()
    session.clear()
    session.update(authenticated=True, sid=old_sid if resume else secrets.token_hex(16))
    session.permanent = True
    try:
        ensure_workbook(create=True)
    except Exception:
        session.clear()
        raise
    return jsonify(ok=True, resumed=bool(resume), version=VERSION)


@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/api/status')
def status():
    with GUARD:
        book, _, assets = ensure_workbook()
        values = get_values(book.read_bytes())
        meta = metadata(assets)
        photos = [addr for addr in READINGS if (assets / (addr + '.jpg')).exists()]
        receipts = list(meta['receipts'].values())
        return jsonify(ok=True, uploaded=True, values=values, series=meta['series'],
                       photos=photos, last=receipts[-1] if receipts else None,
                       version=VERSION, ocr_available=bool(shutil.which('tesseract')))


@app.post('/api/ocr')
def ocr():
    with GUARD:
        _, _, assets = ensure_workbook()
        series = metadata(assets)['series']
        check_series({'series': series}, request.form.get('series'))
    upload = request.files.get('image')
    if not upload:
        raise AppError('Falta la fotografía.')
    image = decode_image(upload.read(MAX_IMAGE_BYTES + 1))
    if not OCR_LOCK.acquire(blocking=False):
        raise AppError('El reconocimiento está ocupado; se reintentará automáticamente.', 429)
    started = time.monotonic()
    try:
        detected, candidates, raw, warning, blank = recognize_display(image)
    except RuntimeError as exc:
        raise AppError('El reconocimiento superó el tiempo permitido. Acerque el display y reduzca el recuadro; se volverá a intentar.', 504) from exc
    except FileNotFoundError as exc:
        raise AppError('El servidor no tiene Tesseract. Despliegue usando el Dockerfile incluido.', 503) from exc
    finally:
        OCR_LOCK.release()
    token = None
    if detected is not None:
        photo = jpeg_bytes(image)
        token = secrets.token_hex(24)
        with GUARD:
            _, _, assets = ensure_workbook()
            check_series(metadata(assets), series)  # Reject a frame captured before reset.
            atomic_write(assets / 'pending.jpg', photo)
            atomic_write(assets / 'pending.json', json_bytes({'token': token, 'value': detected,
                'series': series, 'created': time.time(), 'sha256': hashlib.sha256(photo).hexdigest()}))
    return jsonify(detected=detected, candidates=candidates, raw=raw, warning=warning,
                   blank=blank, token=token, elapsed_ms=round((time.monotonic() - started) * 1000))


@app.post('/api/save')
def save():
    data = request.get_json(silent=True) or {}
    addr = str(data.get('cell', '')).upper()
    token = str(data.get('token', ''))
    if addr not in READINGS:
        raise AppError('Solo se permite escribir E40:K42.')
    value = parse_value(data.get('value'))
    with GUARD:
        book, log, assets = ensure_workbook()
        meta = metadata(assets)
        check_series(meta, data.get('series'))
        # A retry after a lost response must not create a second reading.
        receipt = meta['receipts'].get(token)
        if receipt:
            if receipt['cell'] != addr or parse_value(receipt['value']) != value:
                raise AppError('Esta fotografía ya se registró en otra celda.', 409)
            return jsonify(**receipt, repeated_request=True)
        pending_path = assets / 'pending.json'
        if not re.fullmatch(r'[a-f0-9]{48}', token) or not pending_path.exists():
            raise AppError('No hay una foto reconocida para guardar. Reinicie la captura.', 409)
        pending = json.loads(pending_path.read_text(encoding='utf-8'))
        if not hmac.compare_digest(pending['token'], token) or pending['series'] != meta['series']:
            raise AppError('La fotografía cambió. Use una sola pestaña para capturar.', 409)
        if time.time() - pending['created'] > 180:
            raise AppError('La fotografía expiró. Tome una nueva lectura.', 409)
        if parse_value(pending['value']) != value:
            raise AppError('El valor no corresponde a la foto reconocida.', 409)
        original = book.read_bytes()
        if get_values(original)[addr] is not None:
            raise AppError(f'{addr} ya contiene una lectura. No se sobrescribió.', 409)
        photo = (assets / 'pending.jpg').read_bytes()
        if hashlib.sha256(photo).hexdigest() != pending['sha256']:
            raise AppError('La fotografía no coincide con su registro. Repita la captura.', 409)
        new_book = patch_cell(original, addr, value)
        stamp = datetime.now(timezone.utc).isoformat()
        result = {'ok': True, 'cell': addr, 'value': format_value(value), 'previous': None,
                  'photo': '/api/photo/' + addr, 'timestamp': stamp, 'sha256': pending['sha256']}
        meta['receipts'][token] = result
        old_csv = log.read_bytes() if log.exists() else None
        text = StringIO(newline='')
        writer = csv.writer(text)
        if old_csv is None:
            writer.writerow(['Fecha UTC', 'Celda', 'Valor anterior', 'Valor nuevo g/L', 'Modo', 'Foto', 'SHA256 foto'])
        writer.writerow([stamp, addr, '', format(value, '.4f'), 'Captura automática V5', addr + '.jpg', pending['sha256']])
        new_csv = (old_csv or b'\xef\xbb\xbf') + text.getvalue().encode('utf-8')
        changes = {assets / (addr + '.jpg'): photo, book: new_book, log: new_csv,
                   assets / 'session.json': json_bytes(meta)}
        backups = {path: path.read_bytes() if path.exists() else None for path in changes}
        try:
            for path, payload in changes.items():
                atomic_write(path, payload)
        except Exception:
            for path, previous in backups.items():
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, previous)
            raise
    return jsonify(**result)


@app.post('/api/reset')
def reset_workbook():
    data = template_data()
    with GUARD:
        book, log, assets = ensure_workbook()
        shutil.rmtree(assets)
        assets.mkdir()
        meta = {'series': secrets.token_hex(16), 'receipts': {}}
        atomic_write(assets / 'session.json', json_bytes(meta))
        atomic_write(book, data)
        log.unlink(missing_ok=True)
    return jsonify(ok=True, values=get_values(data), series=meta['series'])


def attachment(data, name, mimetype):
    return send_file(BytesIO(data), as_attachment=True, download_name=name,
                     mimetype=mimetype, max_age=0, conditional=False)


@app.get('/api/download')
def download():
    with GUARD:
        book, _, _ = ensure_workbook()
        data = book.read_bytes()
    return attachment(data, 'FORM19_LECTURAS_CAPTURADAS.xlsm', 'application/vnd.ms-excel.sheet.macroEnabled.12')


@app.get('/api/audit')
def audit():
    with GUARD:
        _, log, _ = ensure_workbook()
        if not log.exists():
            raise AppError('Todavía no hay lecturas registradas para descargar el historial.')
        data = log.read_bytes()
    return attachment(data, 'FORM19_TRAZABILIDAD.csv', 'text/csv; charset=utf-8')


@app.get('/api/photo/<addr>')
def photo(addr):
    if addr not in READINGS:
        raise AppError('Celda no válida.', 404)
    with GUARD:
        _, _, assets = ensure_workbook()
        path = assets / (addr + '.jpg')
        if not path.exists():
            raise AppError('Esta celda no tiene una fotografía guardada.', 404)
        data = path.read_bytes()
    return send_file(BytesIO(data), mimetype='image/jpeg', max_age=0, conditional=False)


@app.get('/api/evidence')
def evidence():
    output = BytesIO()
    with GUARD:
        book, log, assets = ensure_workbook()
        meta = metadata(assets)
        photos = [assets / (addr + '.jpg') for addr in READINGS if (assets / (addr + '.jpg')).exists()]
        if not photos:
            raise AppError('Todavía no hay fotografías guardadas.')
        with ZipFile(output, 'w', ZIP_DEFLATED) as z:
            z.writestr('FORM19_LECTURAS_CAPTURADAS.xlsm', book.read_bytes())
            if log.exists():
                z.writestr('FORM19_TRAZABILIDAD.csv', log.read_bytes())
            for path in photos:
                z.writestr('fotos/' + path.name, path.read_bytes())
            z.writestr('MANIFIESTO.json', json_bytes({'version': VERSION, 'lecturas': list(meta['receipts'].values())}))
    return attachment(output.getvalue(), 'FORM19_EXCEL_FOTOS_HISTORIAL.zip', 'application/zip')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '10000')), threaded=True)
