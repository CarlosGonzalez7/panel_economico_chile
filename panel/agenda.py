"""Calendario e IPoM oficiales. Respaldo explícito ante bloqueo o cambio de formato."""
import copy
import datetime as dt
from html.parser import HTMLParser
import json
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

def load_agenda():
    global CACHE
    with LOCK:
        if CACHE and time.monotonic()-CACHE[0]<300: return copy.deepcopy(CACHE[1])
        data=snapshot(); errors=[]
        # Cada fuente conserva su fecha de comprobación; una falla no invalida la otra.
        from concurrent.futures import ThreadPoolExecutor
        def read(url,parser): return parser(download(url).decode('utf-8'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[('events','calendar_checked',pool.submit(read,CALENDAR,parse_calendar)),('latest','report_checked',pool.submit(read,REPORTS,parse_report))]
            for key,checked,job in jobs:
                try:
                    value=job.result()
                    if key=='latest' and value['period']<data['latest']['period']: raise ValueError('Informe anterior al respaldo')
                    data[key]=value; data[checked]=dt.datetime.now(dt.timezone.utc).isoformat()
                except Exception:
                    errors.append(key)
        data['errors']=errors
        if len(errors)<2:
            path=BASE/'agenda_respaldo.json'; temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps(data,ensure_ascii=False)); temp.replace(path)
        CACHE=(time.monotonic(),data)
        return copy.deepcopy(data)

def latest_pdf():
    data=load_agenda()
    # No etiquetar un informe guardado como el último si no se pudo verificar.
    if 'latest' in data['errors']: raise ValueError('No se pudo comprobar el último IPoM')
    report=data['latest']; body=download(report['url'])
    if not body.startswith(b'%PDF-'): raise ValueError('La fuente no entregó un PDF')
    return body, 'IPoM-'+report['period']+'.pdf'
