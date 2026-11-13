"""Browser regression with simulated API and camera, not a real Render deployment.
Requires Playwright and Chromium. Run: python tests/browser_smoke.py
"""
from io import BytesIO
from pathlib import Path
import json
import sys
from urllib.parse import urlparse
from zipfile import ZipFile

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from form19_core import get_values, patch_cell, READINGS

book = (ROOT / 'data' / 'FORM19_PLANTILLA.xlsm').read_bytes()
values = get_values(book)
saved_requests = []
ocr_requests = []
last = None
fail_download = False
page_errors = []
env = Environment(loader=FileSystemLoader(ROOT / 'templates'), autoescape=True)
env.globals['url_for'] = lambda endpoint, filename: '/static/' + filename


def route_request(route):
    global book, values, last
    path = urlparse(route.request.url).path
    if path == '/':
        html = env.get_template('index.html').render(logged=False, version='V5 · 2026-11-13')
        route.fulfill(status=200, content_type='text/html', body=html)
    elif path.startswith('/static/'):
        file = ROOT / path.lstrip('/')
        route.fulfill(status=200, content_type='text/css' if path.endswith('.css') else 'application/javascript', body=file.read_bytes())
    elif path == '/api/login':
        route.fulfill(json={'ok': True})
    elif path == '/api/status':
        route.fulfill(json={'ok': True, 'uploaded': True, 'values': values, 'series': 'test-series', 'version': 'V5 · 2026-11-13', 'last': last, 'ocr_available': True})
    elif path == '/api/ocr':
        ocr_requests.append(route.request.post_data_buffer)
        route.fulfill(json={'detected': '0,300', 'candidates': ['0,300'], 'raw': ['0.300'] * 3, 'warning': '', 'blank': False, 'token': 'a' * 48, 'elapsed_ms': 75})
    elif path == '/api/save':
        data = route.request.post_data_json
        assert data['value'] == '0,300' and data['cell'] == 'E40' and data['series'] == 'test-series', data
        saved_requests.append(data)
        book = patch_cell(book, data['cell'], 0.3)
        values = get_values(book)
        last = {'ok': True, 'cell': 'E40', 'value': '0,300', 'photo': '/api/photo/E40', 'timestamp': 'test'}
        route.fulfill(json=last)
    elif path.startswith('/api/photo/'):
        from PIL import Image, ImageDraw
        im = Image.new('RGB', (420, 120), 'white'); ImageDraw.Draw(im).text((30, 45), '0.300', fill='black', font_size=55)
        out = BytesIO(); im.save(out, 'JPEG')
        route.fulfill(status=200, content_type='image/jpeg', body=out.getvalue())
    elif path == '/api/download':
        if fail_download:
            route.fulfill(status=503, json={'error': 'Falta data/FORM19_PLANTILLA.xlsm en el servidor.'})
        else:
            route.fulfill(status=200, content_type='application/vnd.ms-excel.sheet.macroEnabled.12', body=book)
    elif path == '/api/reset':
        book = (ROOT / 'data' / 'FORM19_PLANTILLA.xlsm').read_bytes(); values = get_values(book); last = None
        route.fulfill(json={'ok': True, 'values': values, 'series': 'test-series'})
    else:
        route.fulfill(status=404, json={'error': 'Not found in test harness'})


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1180, 'height': 1000}, accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(8000)
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.route('**/*', route_request)
    page.evaluate('''
      Object.defineProperty(window, 'isSecureContext', {value:true, configurable:true});
      Object.defineProperty(navigator, 'mediaDevices', {value: {
        getUserMedia: async () => {
          const c = document.createElement('canvas'); c.width = 1280; c.height = 720;
          const paint = () => {
            const ctx = c.getContext('2d'); ctx.fillStyle = '#dce7dd'; ctx.fillRect(0,0,c.width,c.height);
            ctx.fillStyle = '#142d21'; ctx.font = '110px monospace'; ctx.fillText('0.300',475,390);
          };
          paint(); const interval = setInterval(paint, 100);
          const stream = c.captureStream(10);
          for(const track of stream.getTracks()) {const stop=track.stop.bind(track); track.stop=()=>{clearInterval(interval);stop();};}
          return stream;
        }
      }, configurable:true});
    ''')
    html = env.get_template('index.html').render(logged=False, version='V5 · 2026-11-13')
    html = html.replace('<head>', '<head><base href="http://127.0.0.1:18799/">')
    page.set_content(html)
    page.locator('#password').fill('admin')
    page.locator('#login').click()
    page.wait_for_function("!document.getElementById('start').disabled")
    assert page.locator('#progress').inner_text() == '0 / 21 lecturas'
    print('OK: login and initialized workbook state (simulated API)')
    page.locator('#start').click()
    page.wait_for_function("document.getElementById('saveMsg').textContent.includes('Lectura y fotografía guardadas')")
    assert page.locator('#last').inner_text() == '0,300 g/L'
    assert page.locator('#target').inner_text() == 'F40'
    page.wait_for_timeout(1600)
    assert len(saved_requests) == 1, saved_requests
    assert len(ocr_requests) >= 3
    assert page.locator('#photoPanel').is_visible()
    assert page.locator('[data-cell=E40]').inner_text().endswith('0,300')
    print('OK: automatic two-frame capture, photo preview, next cell, duplicate protection')
    # The overlay and video share geometry; no letterbox offset.
    roi = page.locator('#roi').bounding_box(); video = page.locator('#video').bounding_box()
    assert abs(roi['width'] / video['width'] - .65) < .015
    assert abs(roi['height'] / video['height'] - .28) < .015
    print('OK: ROI geometry matches video dimensions')
    with page.expect_download() as item:
        page.locator('#downloadExcel').click()
    download = item.value
    output = Path('/mnt/data/FORM19_TEST_NAVEGADOR.xlsm')
    download.save_as(output)
    assert download.suggested_filename == 'FORM19_LECTURAS_CAPTURADAS.xlsm'
    assert get_values(output.read_bytes())['E40'] == '0.3000'
    with ZipFile(BytesIO((ROOT / 'data' / 'FORM19_PLANTILLA.xlsm').read_bytes())) as original, ZipFile(output) as generated:
        assert original.read('xl/vbaProject.bin') == generated.read('xl/vbaProject.bin')
    assert page.locator('#downloadMsg').inner_text().startswith('Archivo preparado')
    print('OK: browser downloaded XLSM with the captured value and identical VBA binary')
    fail_download = True
    page.locator('#downloadExcel').click()
    page.wait_for_function("document.getElementById('downloadMsg').textContent.includes('Falta data')")
    print('OK: download failure displayed explicitly instead of a broken file')
    fail_download = False
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path='/mnt/data/FORM19_V5_MOVIL.png', full_page=True)
    print('OK: mobile layout without horizontal page overflow')
    page.set_viewport_size({'width': 1180, 'height': 1050})
    page.screenshot(path='/mnt/data/FORM19_V5_ESCRITORIO.png', full_page=True)
    page.on('dialog', lambda d: d.accept())
    page.locator('#reset').click()
    page.wait_for_function("document.getElementById('progress').textContent==='0 / 21 lecturas'")
    assert not page.locator('#photoPanel').is_visible()
    assert not page_errors, page_errors
    print('OK: reset clears readings/preview; no JavaScript errors')
    browser.close()
print('Browser smoke test passed (camera and HTTP API simulated).')
