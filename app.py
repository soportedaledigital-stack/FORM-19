"""DALEDIGITAL FORM19 camera capture web app for Render.
Preserves XLSM structure by patching only cells E40:K42 in OOXML worksheet XML.
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import csv, hmac, os, re, secrets, tempfile, threading
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile
from lxml import etree
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from flask import Flask, jsonify, request, send_file, render_template, session

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config.update(MAX_CONTENT_LENGTH=18*1024*1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=os.environ.get('RENDER','') == 'true',
                  SESSION_COOKIE_SAMESITE='Lax')
BASE = Path(tempfile.gettempdir()) / 'daledigital_form19'
BASE.mkdir(exist_ok=True)
GUARD = threading.RLock()
READINGS = tuple(f'{col}{row}' for row in (40,41,42) for col in 'EFGHIJK')
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def authorized():
    pwd = os.environ.get('APP_PASSWORD', 'admin').strip()
    return bool(pwd) and session.get('authenticated') is True

@app.route('/health')
def health(): return 'ok', 200

@app.route('/', methods=['GET'])
def home(): return render_template('index.html', logged=authorized())

@app.post('/api/login')
def login():
    pwd = os.environ.get('APP_PASSWORD','admin').strip()
    candidate = str((request.get_json(silent=True) or {}).get('password',''))
    if not pwd or not hmac.compare_digest(candidate,pwd):
        return jsonify(error='Contraseña incorrecta o APP_PASSWORD sin configurar.'), 401
    session.clear()
    session['authenticated'] = True
    session['sid'] = secrets.token_hex(16)
    return jsonify(ok=True)

@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)

@app.before_request
def protect():
    if request.path.startswith('/api/') and request.path not in ('/api/login',):
        if not authorized(): return jsonify(error='Acceso no autorizado. Inicie sesión.'), 401


def storage():
    sid = session.get('sid','')
    if not re.fullmatch(r'[a-f0-9]{32}', sid):
        raise ValueError('Inicie sesión nuevamente.')
    return BASE / (sid + '.xlsm'), BASE / (sid + '.csv')


def worksheet_path(z):
    book = etree.fromstring(z.read('xl/workbook.xml'))
    links = etree.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    sheets = book.findall(f'{{{NS}}}sheets/{{{NS}}}sheet')
    target_sheet = next((s for s in sheets if s.get('name') == 'REGISTRO DE DATOS'), None)
    if target_sheet is None: raise ValueError('Falta la hoja REGISTRO DE DATOS.')
    rid = target_sheet.get(f'{{{REL_NS}}}id')
    target = next((e.get('Target') for e in links if e.get('Id') == rid), None)
    if not target: raise ValueError('No se encuentra la hoja en el XLSM.')
    from posixpath import normpath
    return normpath(target.lstrip('/') if target.startswith('/xl/') else 'xl/' + target)


def is_valid_book(data):
    if len(data) > 16*1024*1024: raise ValueError('El archivo supera el límite de 16 MB.')
    with ZipFile(BytesIO(data)) as z:
        path = worksheet_path(z)
        if path not in z.namelist(): raise ValueError('Estructura XLSM inválida.')
        root = etree.fromstring(z.read(path))
        for row in (40,41,42):
            row_nodes = root.xpath(f'.//m:sheetData/m:row[@r="{row}"]',namespaces={'m':NS})
            if len(row_nodes)!=1: raise ValueError(f'La fila {row} no existe en la plantilla.')
        return path


def get_values(data):
    with ZipFile(BytesIO(data)) as z:
        path=worksheet_path(z)
        root=etree.fromstring(z.read(path))
        cells={c.get('r'):c for c in root.findall(f'.//{{{NS}}}sheetData/{{{NS}}}row/{{{NS}}}c')}
        result={}
        for addr in READINGS:
            c=cells.get(addr)
            v=None if c is None else c.find(f'{{{NS}}}v')
            result[addr] = v.text if v is not None else None
        return result


def patch_cell(original, addr, value):
    in_stream, out_stream = BytesIO(original), BytesIO()
    with ZipFile(in_stream) as src, ZipFile(out_stream,'w') as dst:
        path = worksheet_path(src)
        root = etree.fromstring(src.read(path))
        row_nr = int(addr[1:])
        row = root.xpath(f'.//m:sheetData/m:row[@r="{row_nr}"]',namespaces={'m':NS})[0]
        cell = next((c for c in row if c.tag == f'{{{NS}}}c' and c.get('r')==addr), None)
        if cell is None: raise ValueError('La celda seleccionada no está presente en FORM19.')
        for child in list(cell):
            if child.tag in (f'{{{NS}}}f',f'{{{NS}}}v',f'{{{NS}}}is'):
                cell.remove(child)
        cell.attrib.pop('t', None)
        etree.SubElement(cell,f'{{{NS}}}v').text = format(value,'.4f')
        replacement=etree.tostring(root,encoding='UTF-8',xml_declaration=True)
        for meta in src.infolist():
            dst.writestr(meta, replacement if meta.filename == path else src.read(meta.filename))
    return out_stream.getvalue()


def parse_value(s):
    if not isinstance(s,str) or not re.fullmatch(r'\s*\d{1,2}(?:[.,]\d{1,4})?\s*',s):
        raise ValueError('Formato inválido. Ejemplos: 0,300; 0,45; 1,2 g/L.')
    x=float(s.strip().replace(',','.'))
    if not 0 <= x <= 3: raise ValueError('Valor fuera de 0 a 3 g/L.')
    return x

@app.post('/api/upload')
def upload():
    file=request.files.get('file')
    if not file or not file.filename.lower().endswith('.xlsm'):
        return jsonify(error='Seleccione un Excel .xlsm.'),400
    try:
        data=file.read(16*1024*1024+1)
        is_valid_book(data)
        with GUARD:
            p,log=storage()
            p.write_bytes(data)
            log.unlink(missing_ok=True)
        return jsonify(ok=True, values=get_values(data), message='Plantilla recibida. Las demás celdas no se modificarán.')
    except (ValueError, BadZipFile,KeyError,etree.XMLSyntaxError) as e:
        return jsonify(error=str(e)),400

@app.get('/api/status')
def status():
    try:
        p,_=storage()
        return jsonify(uploaded=p.exists(), values=get_values(p.read_bytes()) if p.exists() else {})
    except Exception: return jsonify(uploaded=False,values={})

@app.post('/api/save')
def save():
    d=request.get_json(silent=True) or {}
    try:
        addr=str(d.get('cell','')).upper()
        if addr not in READINGS: raise ValueError('Solo se permite escribir E40:K42.')
        value=parse_value(d.get('value'))
        with GUARD:
            p,log=storage()
            if not p.exists(): raise ValueError('Primero cargue un archivo FORM19 .xlsm.')
            data=p.read_bytes()
            previous=get_values(data)[addr]
            if previous is not None and not bool(d.get('replace')):
                raise ValueError(f'{addr} ya contiene {previous}. Active reemplazo si corresponde.')
            new_data=patch_cell(data,addr,value)
            tmp=p.with_suffix('.tmp')
            tmp.write_bytes(new_data)
            tmp.replace(p)
            new_file=not log.exists()
            with log.open('a',newline='',encoding='utf-8-sig') as f:
                writer=csv.writer(f)
                if new_file: writer.writerow(['Fecha UTC','Celda','Valor anterior','Valor nuevo g/L','Modo'])
                writer.writerow([datetime.now(timezone.utc).isoformat(),addr,previous,format(value,'.4f'),str(d.get('source','confirmado'))[:50]])
        return jsonify(ok=True,cell=addr,value=f'{value:.3f}'.replace('.',','),previous=previous)
    except ValueError as e: return jsonify(error=str(e)),400

@app.get('/api/download')
def download():
    p,_=storage()
    if not p.exists(): return jsonify(error='No hay un archivo cargado.'),400
    return send_file(BytesIO(p.read_bytes()),as_attachment=True,download_name='FORM19_LECTURAS_CAPTURADAS.xlsm',mimetype='application/vnd.ms-excel.sheet.macroEnabled.12')

@app.get('/api/audit')
def download_audit():
    _,p=storage()
    if not p.exists(): return jsonify(error='Todavía no hay registros.'),400
    return send_file(BytesIO(p.read_bytes()),as_attachment=True,download_name='FORM19_TRAZABILIDAD.csv',mimetype='text/csv')

def recognize_display(image: Image.Image, fast: bool):
    """OCR on several display-oriented variants, without assuming a nominal reference value.

    Return only decimal-shaped readouts. Reject lone digits and long numbers from labels
    and instrument serial numbers (which previously could win the majority vote).
    """
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    w, h = gray.size
    # Upsample small cellphone/video crops to make narrow decimal points visible.
    factor = min(3.0, max(1.0, 1050 / max(w, 1)))
    if factor > 1.01:
        gray = gray.resize((round(w * factor), round(h * factor)), Image.Resampling.LANCZOS)
    gray = ImageEnhance.Contrast(gray).enhance(1.65)
    variants = [('grayscale', gray)]
    variants.append(('bright', ImageOps.autocontrast(ImageEnhance.Brightness(gray).enhance(1.35))))
    variants.append(('inverted', ImageOps.invert(gray)))
    for threshold in (110, 160):
        variants.append((f'threshold-{threshold}', gray.point(lambda x, t=threshold: 255 if x > t else 0)))
    # Alternate PSMs help on LCD/7-segment screens; psm 6 can find digits
    # alongside units when a still photo is used.
    modes = (7, 13, 8) if fast else (7, 13, 8, 6)
    observations = []
    raw_texts = []
    for name, variant in variants:
        for psm in modes:
            txt = pytesseract.image_to_string(
                variant,
                config=(f'--oem 3 --psm {psm} '
                        '-c tessedit_char_whitelist=0123456789.,OoIl|S ')
            ).strip()
            if txt:
                raw_texts.append(txt[:90])
            # Keep digit groups, repair common OCR errors on 7-segment LCDs.
            normalized = txt.replace('O','0').replace('o','0').replace('I','1').replace('l','1').replace('|','1').replace('S','5')
            normalized = re.sub(r'(?<=\d)\s*[.,]\s*(?=\d)', '.', normalized)
            for m in re.finditer(r'(?<![\d.,])([0-3])[.,](\d{1,4})(?![\d.,])', normalized):
                token = m.group(0)
                try:
                    value = parse_value(token)
                except ValueError:
                    continue
                # Repetition across variants is useful but isn't proof of correctness.
                observations.append((round(value, 4), name, psm))
    if not observations:
        return None, [], raw_texts[:4], 'No se detectaron dígitos con separador decimal. Acerque la cámara y ajuste el recuadro.'
    count = {}
    for value, name, mode in observations:
        count[value] = count.get(value, 0) + 1
    ordered = sorted(count, key=lambda x: (-count[x], x))
    winner = ordered[0]
    # Do not silently choose between similarly supported conflicting readouts.
    runner_up = count.get(ordered[1], 0) if len(ordered) > 1 else 0
    confident = count[winner] >= 2 and count[winner] >= runner_up + 2
    fmt = lambda n: f'{n:.3f}'.replace('.', ',') if round(n, 4) == round(n, 3) else f'{n:.4f}'.replace('.', ',')
    warning = '' if confident else 'Lectura poco clara o diferente entre filtros. Ajuste encuadre e iluminación.'
    return fmt(winner) if confident else None, [fmt(v) for v in ordered[:5]], raw_texts[:4], warning


@app.post('/api/ocr')
def ocr():
    up = request.files.get('image')
    if not up:
        return jsonify(error='Falta la fotografía.'), 400
    try:
        fast = request.form.get('fast') == '1'
        img = Image.open(BytesIO(up.read(8*1024*1024)))
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((1300 if fast else 1800, 1300 if fast else 1800))
        detected, candidates, raw, warning = recognize_display(img, fast)
        return jsonify(detected=detected, candidates=candidates, raw=raw, warning=warning)
    except Exception as e:
        return jsonify(error='Error procesando imagen: ' + str(e)[:150]), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT','10000')))
