"""Servidor local del panel. Solo escucha en este equipo; sin dependencias externas."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import csv
import datetime as dt
import math
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlparse, parse_qs
import webbrowser
import sys
from fuentes import EXTRA, load_extra, get, RAW, today

ROOT = Path(__file__).resolve().parent.parent
TOKEN = secrets.token_urlsafe(24)
CACHE = {}
LOCK = threading.Lock()
SERIES_LOCKS = {c['id']: threading.Lock() for c in EXTRA}

def persist(result, year=None):
    # Mantener un respaldo portátil actualizado, sin guardar el token del servidor.
    with LOCK:
        path = ROOT / 'panel' / 'panel_datos.json'
        payload = json.loads(path.read_text())
        if year is not None:
            original = next(c for c in payload['series'] if c['id'] == result['codigo'])
            if result.get('unidad_medida') != original['api_unit']: raise ValueError('Unidad incorrecta')
            rows = {}
            for r in result['serie']:
                date, value = r['fecha'][:10], r['valor']
                dt.date.fromisoformat(date)
                if not date.startswith(year) or not math.isfinite(value): raise ValueError('Dato incorrecto')
                if original['kind'] == 'level' and value <= 0: raise ValueError('Nivel incorrecto')
                if date <= today().isoformat(): rows[date] = value
            result = dict(original, data=sorted({**dict(original['data']), **rows}.items()), checked=dt.datetime.now(dt.timezone.utc).isoformat())
        payload['series'] = [result if c['id'] == result['id'] else c for c in payload['series']]
        payload['cutoff'] = today().isoformat()
        body = json.dumps(payload, ensure_ascii=False)
        temp = path.with_suffix('.tmp')
        temp.write_text(body); temp.replace(path)
        template = (ROOT / 'panel' / 'plantilla.html').read_text()
        page = ROOT / 'panel_economico.html'
        temp = page.with_suffix('.tmp')
        temp.write_text(template.replace('__PAYLOAD__', body.replace('</', '<\\/')))
        temp.replace(page)
        csv_path = ROOT / 'panel' / 'panel_datos.csv'
        temp = csv_path.with_suffix('.tmp')
        with temp.open('w', newline='') as f:
            w = csv.writer(f); w.writerow(['fecha','serie','valor','unidad','frecuencia','proveedor'])
            for c in payload['series']:
                w.writerows([date,c['id'],v,c['unit'],c['freq'],c['provider']] for date,v in c['data'])
        temp.replace(csv_path)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send_error(403); return
        if parsed.path == '/':
            body = (ROOT / 'panel_economico.html').read_text().replace('__LOCAL_TOKEN__', TOKEN).encode()
            self.respond(body, 'text/html; charset=utf-8'); return
        if parsed.path == '/api/mindicador':
            if self.headers.get('X-Panel-Token') != TOKEN:
                self.send_error(403); return
            args = parse_qs(parsed.query)
            id = args.get('id', [''])[0]
            year = args.get('year', [''])[0]
            if id not in ('dolar','libra_cobre','tpm','ipc','imacec','uf') or not year.isdigit() or not 2000 <= int(year) <= today().year:
                self.send_error(400); return
            try:
                body = get(f'https://mindicador.cl/api/{id}/{year}', RAW/f'{id}_{year}.json', renew=True)
                data = json.loads(body)
                if data.get('codigo') != id or not isinstance(data.get('serie'), list): raise ValueError('Respuesta incorrecta')
                persist(data, year)
                self.respond(body, 'application/json')
            except Exception:
                self.respond(b'{"error":"Fuente no disponible"}', 'application/json', 502)
            return
        if parsed.path == '/api/serie':
            if self.headers.get('X-Panel-Token') != TOKEN:
                self.send_error(403); return
            id = parse_qs(parsed.query).get('id', [''])[0]
            c = next((c for c in EXTRA if c['id'] == id), None)
            if not c:
                self.send_error(404); return
            try:
                # Se reutiliza dentro de la misma consulta para las dos series de microdatos.
                with SERIES_LOCKS[id]:
                    item = CACHE.get(id)
                    if not item or time.monotonic() - item[0] > 30:
                        result = load_extra(c, renew=True)
                        CACHE[id] = (time.monotonic(), result)
                    else:
                        result = item[1]
                persist(result)
                self.respond(json.dumps(result, ensure_ascii=False).encode(), 'application/json')
            except Exception as exc:
                print(f'Consulta fallida {id}: {type(exc).__name__}', flush=True)
                self.respond(json.dumps({'error': 'No se pudo consultar la fuente; se conserva el respaldo.'}).encode(), 'application/json', 502)
            return
        self.send_error(404)

    def respond(self, body, mime, code=200):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def log_message(self, *args): pass

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('Panel económico: ' + url, flush=True)
    print('Mantén esta ventana abierta para actualizar las fuentes. Ctrl+C para cerrar.', flush=True)
    if '--sin-abrir' not in sys.argv: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
