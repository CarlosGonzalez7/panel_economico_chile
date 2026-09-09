"""Calendario e IPoM oficiales. Respaldo explícito ante bloqueo o cambio de formato."""
import copy
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import unicodedata
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
CALENDAR = 'https://www.bcentral.cl/es/web/banco-central/noticias-y-publicaciones/prensa/calendario-de-politica-monetaria-y-financiera'
REPORTS = 'https://www.bcentral.cl/areas/politica-monetaria/informe-de-politica-monetaria'
MONTHS = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()
LOCK = threading.Lock()
CACHE = None
BROWSER_ENABLED = os.environ.get("AGENDA_BROWSER", "0") == "1"

def normalized(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c)).split())

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.parts=[]; self.links=[]; self.anchor=None
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        if tag in ('h1','h2','h3','h4','li','p','br','div'): self.parts.append('\n')
        if tag == 'a': self.anchor=[dict(attrs).get('href',''), '']
    def handle_data(self, data):
        self.parts.append(data)
        if self.anchor is not None: self.anchor[1]+=data
    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor is not None:
            self.links.append(self.anchor); self.anchor=None
        if tag in ('h1','h2','h3','h4','li','p','div'): self.parts.append('\n')

def parse_calendar(text):
    lines=[normalized(s) for s in ''.join(Page(text).parts).splitlines() if s.strip()]
    events=[]; kind=None; year=None
    for line in lines:
        heading=re.search(r'(reuniones|informes) de politica monetaria.*?(20\d{2})',line)
        if heading:
            kind='rpm' if heading[1]=='reuniones' else 'ipom'; year=int(heading[2]); continue
        if re.search(r'minutas|politica financiera|estabilidad financiera',line): kind=None
        if not kind: continue
        match=re.fullmatch(r'(\d{1,2})(?: y (\d{1,2}))? de (\w+)',line)
        if not match or match[3] not in MONTHS: continue
        month=MONTHS.index(match[3])+1
        start=dt.date(year,month,int(match[1])); end=dt.date(year,month,int(match[2] or match[1]))
        if end<start: raise ValueError('Intervalo de calendario incorrecto')
        events.append(dict(kind=kind,start=start.isoformat(),end=end.isoformat()))
    if not all(any(e['kind']==k for e in events) for k in ('rpm','ipom')):
        raise ValueError('Calendario no reconocido')
    return sorted({(e['kind'],e['start']):e for e in events}.values(),key=lambda e:e['start'])

def official_pdf(url):
    p=urlsplit(url)
    return p.scheme=='https' and p.hostname=='www.bcentral.cl' and p.path.startswith('/documents/') and not p.username

def parse_report(text):
    candidates=[]
    for href,title in Page(text).links:
        label=normalized(title)
        match=re.fullmatch(r'(?:informe de politica monetaria|ipom) (?:de )?('+'|'.join(MONTHS)+r') (20\d{2})',label)
        url=urljoin(REPORTS,href)
        if match and official_pdf(url):
            period=f'{match[2]}-{MONTHS.index(match[1])+1:02d}'
            candidates.append(dict(period=period,title=f'IPoM · {match[1]} {match[2]}',url=url))
    if not candidates: raise ValueError('Enlace del informe completo no reconocido')
    return max(candidates,key=lambda r:r['period'])

def download(url):
    if url not in (CALENDAR,REPORTS) and not official_pdf(url): raise ValueError('Fuente no autorizada')
    return subprocess.run(['curl','-fLsS','--connect-timeout','5','--max-time','20','--max-filesize','30000000',url],check=True,capture_output=True).stdout

def snapshot():
    return json.loads((BASE/'agenda_respaldo.json').read_text())

def browser_read(keys):
    """Navegador estándar, sin técnicas de ocultación; una instancia por consulta."""
    from playwright.sync_api import sync_playwright
    variants={
        'events': [CALENDAR, 'https://www.bcentral.cl/noticias-y-publicaciones/prensa/calendario-de-politica-monetaria-y-financiera'],
        'latest': [REPORTS, 'https://www.bcentral.cl/es/areas/politica-monetaria/informe-de-politica-monetaria']}
    parsers={'events':parse_calendar,'latest':parse_report}
    results={}
    with sync_playwright() as playwright:
        options={'headless':True,'args':['--disable-dev-shm-usage']}
        if os.environ.get('AGENDA_CHROME_CHANNEL'): options['channel']=os.environ['AGENDA_CHROME_CHANNEL']
        else:
            options['executable_path']=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium')
            options['args'].append('--no-sandbox')
        browser=playwright.chromium.launch(**options)
        try:
            page=browser.new_page()
            page.route('**/*',lambda route:route.abort() if route.request.resource_type in ('image','media','font') else route.continue_())
            deadline=time.monotonic()+75
            for key in keys:
                for url in variants[key]:
                    remaining=deadline-time.monotonic()
                    if remaining<2: break
                    try:
                        page.goto(url,wait_until='domcontentloaded',timeout=min(18000,remaining*1000))
                        page.wait_for_function("document.body && document.body.innerText.includes('Política Monetaria')",timeout=min(8000,max(1000,(deadline-time.monotonic())*1000)))
                        results[key]=parsers[key](page.content())
                        break
                    except Exception as exc:
                        print(f'Agenda navegador {key}: {type(exc).__name__}',flush=True)
        finally:
            browser.close()
    return results

def load_agenda():
    global CACHE
    with LOCK:
        if CACHE and time.monotonic()-CACHE[0]<(60 if CACHE[1]['errors'] else 300): return copy.deepcopy(CACHE[1])
        data=snapshot(); errors=[]; values={}; methods={}
        from concurrent.futures import ThreadPoolExecutor
        def read(url,parser): return parser(download(url).decode('utf-8'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[('events',pool.submit(read,CALENDAR,parse_calendar)),('latest',pool.submit(read,REPORTS,parse_report))]
            for key,job in jobs:
                try:
                    values[key]=job.result();methods[key]='http'
                except Exception as exc:
                    print(f'Agenda consulta directa {key}: {type(exc).__name__}',flush=True)
        missing=[k for k in ('events','latest') if k not in values]
        if missing and BROWSER_ENABLED:
            try:
                recovered=browser_read(missing)
                values.update(recovered);methods.update({k:'browser' for k in recovered})
            except Exception as exc:
                print(f'Agenda navegador no disponible: {type(exc).__name__}',flush=True)
        stamp=dt.datetime.now(dt.timezone.utc).isoformat()
        data['attempted_at']=stamp
        for key,checked in [('events','calendar_checked'),('latest','report_checked')]:
            value=values.get(key)
            if value is None or (key=='latest' and value['period']<data['latest']['period']):
                errors.append(key);continue
            data[key]=value;data[checked]=stamp
        data['errors']=errors;data['methods']={k:v for k,v in methods.items() if k not in errors}
        path=BASE/'agenda_respaldo.json'; temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False));temp.replace(path)
        CACHE=(time.monotonic(),data)
        return copy.deepcopy(data)

def latest_pdf():
    data=load_agenda()
    # No etiquetar un informe guardado como el último si no se pudo verificar.
    if 'latest' in data['errors']: raise ValueError('No se pudo comprobar el último IPoM')
    report=data['latest']; body=download(report['url'])
    if not body.startswith(b'%PDF-'): raise ValueError('La fuente no entregó un PDF')
    return body, 'IPoM-'+report['period']+'.pdf'
