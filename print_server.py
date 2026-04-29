"""
Price Tag Print Server v4 — Sri Murugan Trading
Port 44444

ESC/POS size reference (what thermal printers actually support):
  GS ! n  where n = (width_mult-1)*16 + (height_mult-1)
    0x00 = 1x1 normal
    0x10 = 2x wide, 1x tall
    0x01 = 1x wide, 2x tall
    0x11 = 2x wide, 2x tall  ← standard "big price"
    0x22 = 3x wide, 3x tall
    0x33 = 4x wide, 4x tall  ← largest

ESC ! n  (character style):
    bit 3 (0x08) = bold
    bit 4 (0x10) = double height
    bit 5 (0x20) = double width
    0x00 = normal
    0x08 = bold
    0x18 = bold + double height
    0x38 = bold + double height + double width
"""

import sys, os, json, subprocess

def ensure_deps():
    try:
        import win32print
    except ImportError:
        print("Installing pywin32...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32", "--quiet"])
        os.execv(sys.executable, [sys.executable] + sys.argv)

ensure_deps()

import win32print
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 44444

def build_escpos(tag):
    b = bytearray()
    def push(*v): b.extend(v)
    def text(s):
        for c in str(s):
            n = ord(c)
            b.append(n if n < 256 else 63)
    def lf(): b.append(0x0A)

    # Price size
    price_size = int(tag.get('priceSize', 52))
    if price_size >= 52:
        price_gs  = 0x33   # 4x wide + 4x tall (max)
    elif price_size >= 44:
        price_gs  = 0x22   # 3x wide + 3x tall
    elif price_size >= 36:
        price_gs  = 0x11   # 2x wide + 2x tall
    else:
        price_gs  = 0x10   # 2x wide

    # Name size
    name_size = int(tag.get('nameSize', 13))
    if name_size >= 18:
        name_esc = 0x38; name_gs = 0x11
    elif name_size >= 15:
        name_esc = 0x18; name_gs = 0x01
    elif name_size >= 12:
        name_esc = 0x08; name_gs = 0x00
    else:
        name_esc = 0x00; name_gs = 0x00

    # Border separator
    border = tag.get('border', 'solid')
    if border == 'none':      sep = None
    elif border == 'double':  sep = '========================================'
    elif border == 'dashed':  sep = '- - - - - - - - - - - - - - - - - - - -'
    else:                     sep = '----------------------------------------'

    # Init
    push(0x1B, 0x40)
    push(0x1B, 0x74, 0x00)

    # ── Store name (small, centered) ──
    if tag.get('showStore') and tag.get('storeName'):
        push(0x1B, 0x61, 0x01)   # center
        push(0x1D, 0x21, 0x00)   # normal size
        push(0x1B, 0x21, 0x00)
        text(tag['storeName'][:40]); lf()
        if sep:
            text(sep); lf()

    # ── Product name (bold, left, compact) ──
    if tag.get('showName') and tag.get('name'):
        push(0x1B, 0x61, 0x00)        # left
        push(0x1D, 0x21, name_gs)
        push(0x1B, 0x21, name_esc)
        wrap = 42 if name_gs == 0x00 else 21
        words = tag['name'][:200].split(' ')
        line = ''
        for w in words:
            candidate = (line + ' ' + w).strip()
            if len(candidate) > wrap:
                text(line.strip()); lf(); line = w
            else:
                line = candidate
        if line:
            text(line.strip()); lf()
        push(0x1D, 0x21, 0x00)
        push(0x1B, 0x21, 0x00)

    # ── Price label (tiny) ──
    if tag.get('showLabel'):
        push(0x1B, 0x61, 0x00)
        push(0x1D, 0x21, 0x00)
        push(0x1B, 0x21, 0x00)
        text('PRICE (' + tag.get('currency', 'AUD') + ')'); lf()

    # ── Price (big, bold, centered, $ and number on same line) ──
    push(0x1B, 0x61, 0x01)        # center
    push(0x1D, 0x21, price_gs)    # size
    push(0x1B, 0x21, 0x38)        # bold + double-height + double-width (thickest)
    text((tag.get('prefix') or '$') + (tag.get('price') or '0.00')); lf()
    push(0x1D, 0x21, 0x00)
    push(0x1B, 0x21, 0x00)

    # ── SKU (small, left) ──
    if tag.get('showSku') and tag.get('sku'):
        push(0x1B, 0x61, 0x00)
        push(0x1D, 0x21, 0x00)
        push(0x1B, 0x21, 0x00)
        text('SKU: ' + tag['sku'][:40]); lf()

    # ── Barcode (small, left, under SKU) ──
    if tag.get('showSku') and tag.get('sku'):
        sku_val = tag['sku'][:20].strip()
        push(0x1B, 0x61, 0x00)   # left
        push(0x1D, 0x68, 0x28)   # height = 40 dots
        push(0x1D, 0x77, 0x01)   # width = 1 (thin)
        push(0x1D, 0x48, 0x00)   # no text under barcode
        push(0x1D, 0x6B, 0x04)   # CODE39
        text('*' + sku_val + '*')
        b.append(0x00)
        lf()

    # ── Date ──
    if tag.get('showDate'):
        from datetime import date
        push(0x1B, 0x61, 0x00)
        push(0x1D, 0x21, 0x00)
        push(0x1B, 0x21, 0x00)
        text(date.today().strftime('%d/%m/%Y')); lf()

    # Bottom border
    if sep and border == 'box':
        text(sep); lf()

    # 1 line feed then cut (reduced from 3 to make tag shorter)
    lf()
    push(0x1D, 0x56, 0x41, 0x03)
    return bytes(b)


def print_raw(printer_name, data):
    # Method 1: Direct TMUSB port write (bypasses spooler)
    for port in ['\\\\.\\TMUSB001', '\\\\.\\TMUSB002', '\\\\.\\TMUSB003']:
        try:
            with open(port, 'wb') as f:
                f.write(data)
            print(f'  ✓ {port}', flush=True)
            return
        except Exception as e:
            print(f'  ✗ {port}: {e}', flush=True)

    # Method 2: win32print RAW
    try:
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ("PriceTag", None, "RAW"))
            try:
                win32print.StartPagePrinter(h)
                win32print.WritePrinter(h, data)
                win32print.EndPagePrinter(h)
            finally:
                win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        print('  ✓ win32print RAW', flush=True)
        return
    except Exception as e:
        print(f'  ✗ win32print: {e}', flush=True)

    raise Exception('Printing failed. Check EPSON TM Utility: Port Type=USB, Port=TMUSB001.')


def list_printers():
    try:
        return [
            {'name': name, 'isEpson': any(k in name.lower() for k in ['epson','tm-t','receipt','thermal'])}
            for flags, desc, name, comment in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        ]
    except: return []

def get_default():
    try: return win32print.GetDefaultPrinter()
    except: return ''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/status':
            self.send_json(200, {'ok': True, 'version': '4.0'})
        elif p == '/printers':
            self.send_json(200, {'printers': list_printers(), 'default': get_default(),
                                  'ports': ['TMUSB001','TMUSB002','USB001']})
        elif p == '/debug':
            self.send_json(200, {'ok': True, 'default': get_default()})
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path.split('?')[0] == '/print':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                tag = payload.get('tag', {})
                printer = (payload.get('printer') or '').strip() or get_default()
                data = build_escpos(tag)
                ps = int(tag.get('priceSize', 0))
                ns = int(tag.get('nameSize', 0))
                print(f'\n  → "{printer}" | {len(data)}b | price={ps}pt name={ns}pt', flush=True)
                print_raw(printer, data)
                print(f'  ✓ {tag.get("name","?")}', flush=True)
                self.send_json(200, {'ok': True, 'method': 'tmusb-direct'})
            except Exception as e:
                print(f'  ✗ {e}', flush=True)
                self.send_json(500, {'ok': False, 'error': str(e)})
        else:
            self.send_response(404); self.end_headers()


if __name__ == '__main__':
    print()
    print('╔══════════════════════════════════════════╗')
    print('║  Price Tag Print Server v4  — Port 44444 ║')
    print('║  Sri Murugan Trading — AUS               ║')
    print('╚══════════════════════════════════════════╝')
    print()
    print('  ESC/POS size guide:')
    print('  Price slider:  18-25pt = normal bold')
    print('                 26-35pt = 2x wide bold')
    print('                 36-45pt = 2x wide+tall bold  ← recommended')
    print('                 46-52pt = 4x wide+tall bold')
    print('  Name slider:    9-11pt = normal')
    print('                 12-14pt = bold  ← recommended')
    print('                 15-17pt = bold + 2x tall')
    print('                 18-20pt = bold + 2x wide+tall')
    print()
    for p in list_printers():
        mark = '  ← EPSON' if p['isEpson'] else ''
        print(f'    • "{p["name"]}"{mark}')
    print(f'  Default: "{get_default()}"')
    print(f'\n  Running on http://localhost:{PORT}')
    print('  Open PriceTagPrinter.html in Chrome → Print tab\n')
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  Stopped.')
