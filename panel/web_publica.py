"""Panel compartible: aplicación WSGI de solo lectura para un alojamiento HTTPS.

Sirve únicamente el panel y las 16 fuentes registradas, nunca archivos arbitrarios.
Una instancia con varios hilos comparte caché y descargas entre todos los visitantes.
"""
import copy
import datetime as dt
import gzip
import json
import os
import threading
import time
from urllib.parse import parse_qs, urlsplit
from fuentes import EXTRA, RAW, get, load_extra, today
from servidor import ROOT, LOCK, persist

TTL = 300  # Evita repetir descargas por cada persona que abre el enlace.
CACHE = {}
KEY_LOCKS = {}
CACHE_LOCK = threading.Lock()


def public_url():
    url = os.environ.get('PUBLIC_URL', os.environ.get('RENDER_EXTERNAL_URL', '')).rstrip('/')
    parsed = urlsplit(url)
    if url and (parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment):
        raise ValueError('PUBLIC_URL debe ser la URL HTTPS pública del panel')
    return url


def cached(key, loader):
    with CACHE_LOCK:
        lock = KEY_LOCKS.setdefault(key, threading.Lock())
    with lock:
        item = CACHE.get(key)
        if item and time.monotonic() - item[0] < TTL:
            return copy.deepcopy(item[1])
        value = loader()
        CACHE[key] = (time.monotonic(), value)
        return copy.deepcopy(value)


def render_page():
    with LOCK:
        payload = json.loads((ROOT/'panel'/'panel_datos.json').read_text())
    payload.update(delivery='public', public_api=public_url())
    data = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    return (ROOT/'panel'/'plantilla.html').read_text().replace('__PAYLOAD__', data).encode()


def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')
    status, mime, body = '200 OK', 'application/json; charset=utf-8', b''
    headers = [('Access-Control-Allow-Origin', '*'), ('X-Content-Type-Options', 'nosniff'),
               ('Referrer-Policy', 'no-referrer'), ('Cache-Control', 'no-store')]
    try:
        if method == 'OPTIONS':
            headers += [('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS'), ('Access-Control-Max-Age', '86400')]
            status = '204 No Content'
        elif method not in ('GET', 'HEAD'):
            status, body = '405 Method Not Allowed', b'{"error":"Solo lectura"}'
            headers.append(('Allow', 'GET, HEAD, OPTIONS'))
        elif path == '/healthz':
            body = b'{"ok":true}'
        elif path in ('/', '/panel_economico.html', '/descargar'):
            body, mime = render_page(), 'text/html; charset=utf-8'
            if path == '/descargar':
                if not public_url():
                    raise ValueError('Falta PUBLIC_URL para conectar el archivo compartido')
                headers.append(('Content-Disposition', 'attachment; filename="panel_economico.html"'))
        elif path == '/api/serie':
            id = parse_qs(environ.get('QUERY_STRING', '')).get('id', [''])[0]
            c = next((c for c in EXTRA if c['id'] == id), None)
            if c is None:
                status, body = '404 Not Found', b'{"error":"Serie desconocida"}'
            else:
                def loader():
                    result = load_extra(c, renew=True)
                    result['checked'] = dt.datetime.now(dt.timezone.utc).isoformat()
                    persist(result)
                    return result
                body = json.dumps(cached(id, loader), ensure_ascii=False).encode()
        elif path == '/api/mindicador':
            args = parse_qs(environ.get('QUERY_STRING', ''))
            id, year = args.get('id', [''])[0], args.get('year', [''])[0]
            if id not in ('dolar','libra_cobre','tpm','imacec','uf') or not year.isdigit() or not 2000 <= int(year) <= today().year:
                status, body = '400 Bad Request', b'{"error":"Indicador o fecha incorrectos"}'
            else:
                def loader():
                    data = json.loads(get(f'https://mindicador.cl/api/{id}/{year}', RAW/f'{id}_{year}.json', renew=True))
                    persist(data, year)
                    return data
                body = json.dumps(cached((id, year), loader), ensure_ascii=False).encode()
        else:
            status, body = '404 Not Found', b'{"error":"No encontrado"}'
    except Exception as exc:
        print(f'Fuente web no disponible: {path}: {type(exc).__name__}', flush=True)
        status, body = '502 Bad Gateway', b'{"error":"Fuente no disponible; se conserva el respaldo"}'
    if body and 'gzip' in environ.get('HTTP_ACCEPT_ENCODING', '') and len(body) > 1024:
        body = gzip.compress(body)
        headers += [('Content-Encoding', 'gzip'), ('Vary', 'Accept-Encoding')]
    headers += [('Content-Type', mime), ('Content-Length', str(len(body)))]
    start_response(status, headers)
    return [b'' if method == 'HEAD' else body]
