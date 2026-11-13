"""FORM19: XLSM preservation and display recognition, independent of Flask.

Only E40:K42 are written. ZIP members not belonging to the data worksheet are
copied without changing their contents, including the VBA binary and images.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
from posixpath import normpath
import re
from zipfile import ZipFile

from lxml import etree
from PIL import Image, ImageOps, ImageFilter, UnidentifiedImageError
import pytesseract

READINGS = tuple(f'{col}{row}' for row in (40, 41, 42) for col in 'EFGHIJK')
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
MAX_IMAGE_BYTES = 8 * 1024 * 1024
XML_PARSER = dict(resolve_entities=False, no_network=True)


def xml(data):
    return etree.fromstring(data, parser=etree.XMLParser(**XML_PARSER))


def worksheet_path(z: ZipFile) -> str:
    book = xml(z.read('xl/workbook.xml'))
    links = xml(z.read('xl/_rels/workbook.xml.rels'))
    sheets = book.findall(f'{{{NS}}}sheets/{{{NS}}}sheet')
    sheet = next((s for s in sheets if s.get('name') == 'REGISTRO DE DATOS'), None)
    if sheet is None:
        raise ValueError('Falta la hoja REGISTRO DE DATOS.')
    rid = sheet.get(f'{{{REL_NS}}}id')
    target = next((e.get('Target') for e in links if e.get('Id') == rid), None)
    if not target:
        raise ValueError('No se encuentra la hoja en el XLSM.')
    return normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)


def is_valid_book(data: bytes) -> str:
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('La plantilla supera 16 MB.')
    with ZipFile(BytesIO(data)) as z:
        path = worksheet_path(z)
        root = xml(z.read(path))
        cells = {c.get('r') for c in root.findall(f'.//{{{NS}}}sheetData/{{{NS}}}row/{{{NS}}}c')}
        if any(addr not in cells for addr in READINGS):
            raise ValueError('Faltan celdas E40:K42 en la plantilla FORM19.')
        if 'xl/vbaProject.bin' not in z.namelist():
            raise ValueError('La plantilla FORM19 no contiene el proyecto VBA original.')
    return path


def get_values(data: bytes) -> dict:
    with ZipFile(BytesIO(data)) as z:
        root = xml(z.read(worksheet_path(z)))
        cells = {c.get('r'): c for c in root.findall(f'.//{{{NS}}}sheetData/{{{NS}}}row/{{{NS}}}c')}
        result = {}
        for addr in READINGS:
            c = cells.get(addr)
            v = None if c is None else c.find(f'{{{NS}}}v')
            if v is not None:
                result[addr] = v.text
            elif c is not None and c.find(f'{{{NS}}}is') is not None:
                # An existing string must not be treated as an empty measurement.
                result[addr] = ''.join(c.find(f'{{{NS}}}is').itertext()) or None
            else:
                result[addr] = None
        return result


def parse_value(s: str) -> float:
    if not isinstance(s, str) or not re.fullmatch(r'\s*\d{1,2}(?:[.,]\d{1,4})?\s*', s):
        raise ValueError('Valor inválido. Ejemplos: 0,300; 0,45; 1,2. No escriba la unidad.')
    value = float(s.strip().replace(',', '.'))
    if not 0 <= value <= 3:
        raise ValueError('Valor fuera de 0 a 3 g/L. No se ha guardado.')
    return value


def format_value(value: float) -> str:
    decimals = 3 if round(value, 4) == round(value, 3) else 4
    return f'{value:.{decimals}f}'.replace('.', ',')


def patch_cell(original: bytes, addr: str, value: float) -> bytes:
    if addr not in READINGS:
        raise ValueError('Solo se permite escribir E40:K42.')
    value = parse_value(str(value))
    output = BytesIO()
    with ZipFile(BytesIO(original)) as src, ZipFile(output, 'w') as dst:
        path = worksheet_path(src)
        root = xml(src.read(path))
        cells = root.xpath(f'.//m:sheetData/m:row/m:c[@r="{addr}"]', namespaces={'m': NS})
        if len(cells) != 1:
            raise ValueError(f'La celda {addr} no existe en la plantilla.')
        cell = cells[0]
        for child in list(cell):
            if child.tag in (f'{{{NS}}}f', f'{{{NS}}}v', f'{{{NS}}}is'):
                cell.remove(child)
        cell.attrib.pop('t', None)
        etree.SubElement(cell, f'{{{NS}}}v').text = format(value, '.4f')
        replacement = etree.tostring(root, encoding='UTF-8', xml_declaration=True)
        for meta in src.infolist():
            dst.writestr(meta, replacement if meta.filename == path else src.read(meta.filename))
    return output.getvalue()


def decode_image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('La foto está vacía o supera 8 MB.')
    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height > 16_000_000:
            raise ValueError('La imagen supera 16 megapíxeles. Use un recorte del display.')
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1400, 1400))
        if min(image.size) < 16:
            raise ValueError('El recorte es demasiado pequeño.')
        return image
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError('No se pudo abrir la fotografía.') from exc


def jpeg_bytes(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format='JPEG', quality=94)
    return stream.getvalue()


def parse_ocr_text(text: str):
    """Accept explicit decimals only. Never insert a missing decimal separator.

    A leading decimal (.300) can represent 0.300; multiple/ambiguous readouts
    are rejected. A value must appear in at least two lines of the contact sheet.
    """
    count = Counter()
    raw = [s.strip()[:120] for s in text.splitlines() if s.strip()][:8]
    for line in raw:
        line = re.sub(r'(?<=\d)\s*([.,])\s*(?=\d)', r'\1', line)
        line = re.sub(r'(?<![\d.,])([.,])\s*(?=\d)', r'0\1', line)
        found = set()
        for m in re.finditer(r'(?<![\w.,])([0-3][.,]\d{1,4})(?![\w.,])', line):
            try:
                found.add(round(parse_value(m.group(1)), 4))
            except ValueError:
                pass
        for value in found:
            count[value] += 1
    ranked = count.most_common()
    candidates = [format_value(value) for value, _ in ranked[:5]]
    # Conservatively reject competing values instead of guessing a nominal MRC.
    if len(ranked) == 1 and ranked[0][1] >= 2:
        return candidates[0], candidates, raw, '', False
    if not ranked:
        warning = 'No se reconoce un número con decimal. Ajuste el recuadro y el enfoque; no se guardó ninguna lectura.'
    else:
        warning = 'Lectura ambigua o insuficiente. Ajuste la cámara; no se guardó ningún valor.'
    return None, candidates, raw, warning, not raw


def recognize_display(image: Image.Image, timeout: float = 12.0):
    """One Tesseract process per frame, not the original 15 invocations.

    Three contrast versions are stacked into a single contact sheet. Matching
    results across image variants and successive frames are still required.
    This is not a validation of accuracy on an actual instrument display.
    """
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    corners = [gray.getpixel(p) for p in ((0, 0), (gray.width - 1, 0), (0, gray.height - 1), (gray.width - 1, gray.height - 1))]
    if sorted(corners)[len(corners) // 2] < 110:
        gray = ImageOps.invert(gray)
    factor = min(3.0, 1000 / max(gray.width, 1), 260 / max(gray.height, 1))
    gray = gray.resize((max(1, round(gray.width * factor)), max(1, round(gray.height * factor))), Image.Resampling.LANCZOS)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1, percent=130, threshold=3))
    variants = [gray, gray.point(lambda x: 255 if x > 125 else 0), gray.point(lambda x: 255 if x > 180 else 0)]
    margin = 24
    canvas = Image.new('L', (gray.width + margin * 2, (gray.height + margin * 2) * 3), 255)
    for index, variant in enumerate(variants):
        canvas.paste(variant, (margin, index * (gray.height + margin * 2) + margin))
    text = pytesseract.image_to_string(canvas, lang='eng', config='--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.,', timeout=timeout)
    return parse_ocr_text(text)
