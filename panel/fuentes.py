"""Fuentes adicionales. Python estándar; respuestas y cálculos auditables en disco."""
import csv
import datetime as dt
import gzip
import hashlib
import io
import html
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
from collections import defaultdict
from urllib.parse import quote
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
RAW = BASE / 'datos_originales'
INE = 'https://www.ine.gob.cl/estadisticas-por-tema/mercado-laboral/ocupacion-y-desocupacion/'
LOCK = threading.Lock()

def today():
    return dt.datetime.now(ZoneInfo('America/Santiago')).date()

FETCH_LOCKS = defaultdict(threading.Lock)
FETCHED = {}

def get(url, path, renew=False, data=None, validator=None):
    path = Path(path)
    with FETCH_LOCKS[str(path)]:
        recent = time.monotonic() - FETCHED.get(str(path), -1000) < 20
        result = _get(url, path, renew and not recent, data, validator)
        if renew and not recent:
            FETCHED[str(path)] = time.monotonic()
        return result

def _get(url, path, renew=False, data=None, validator=None):
    path = Path(path)
    if path.exists() and not renew:
        return path.read_bytes()
    args = ['curl', '-sS', '-L', '--fail', '--connect-timeout', '6', '--max-time', '25', '-A', 'Mozilla/5.0', url]
    if data:
        args += ['--data', data]
    for attempt in range(2):
        try:
            result = subprocess.run(args, check=True, capture_output=True).stdout
            break
        except subprocess.CalledProcessError as exc:
            # Solo reintentar errores transitorios de transporte; no páginas inválidas.
            if attempt or 'si3.bcentral.cl/' not in url or exc.returncode not in (6, 7, 28, 52, 56):
                raise
            time.sleep(0.5)
    # Rechazar páginas de error antes de reemplazar una respuesta guardada.
    if path.suffix == '.json':
        decoded = json.loads(result)
        if path.name.endswith('_yahoo.json') and not decoded.get('chart', {}).get('result'):
            raise ValueError('Respuesta bursátil vacía')
        if re.fullmatch(r'(dolar|libra_cobre|tpm|ipc|imacec|uf)_\d{4}\.json', path.name):
            if decoded.get('codigo') != path.name.rsplit('_', 1)[0] or not isinstance(decoded.get('serie'), list):
                raise ValueError('Respuesta de indicador incorrecta')
    elif path.suffix == '.csv' and not result.decode('utf-8-sig').startswith('DATAFLOW,'):
        raise ValueError('CSV SDMX inesperado')
    elif path.name == 'ipsa_bcentral.html' and b'data-header="F013.IBC.IND.N.7.LAC.CL.CLP.BLO.M"' not in result:
        raise ValueError('Cuadro BDE inesperado')
    if validator:
        validator(result)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(result)
    tmp.replace(path)
    return result

def config():
    out = []
    for id, name, symbol, unit, color in [
        ('sp500', 'S&P 500', '^GSPC', 'puntos', '#4b7d9e'),
        ('ipsa', 'S&P IPSA · Chile', '^IPSA', 'puntos', '#a65a26'),
        ('nvda', 'NVIDIA · NASDAQ: NVDA', 'NVDA', 'USD / acción', '#548621')]:
        out.append(dict(id=id, name=name, symbol=symbol, unit=unit, start=2000,
                        freq='Diaria', kind='level', color=color, provider='Yahoo Finance',
                        backend='market', note='Cierre diario del proveedor; la sesión en curso puede ser provisional. '
                        + ('Precio ajustado por splits, sin reinversión de dividendos.' if id == 'nvda' else 'Índice de precios, sin reinversión de dividendos.')
                        + (' Se interpreta «SPY500» como el índice S&P 500 (^GSPC); SPY es un ETF distinto.' if id == 'sp500' else '')))
    for id, name, backend, start, note in [
        ('tasa_desempleo', 'Tasa de desocupación · total', 'ine', 2010, 'Población de 15 años o más, ambos sexos.'),
        ('desempleo_femenino', 'Desocupación · mujeres', 'ine', 2010, 'Mujeres de 15 años o más.'),
        ('desempleo_juvenil', 'Desocupación · jóvenes 15–24', 'ine', 2010, 'Ambos sexos, de 15 a 24 años.'),
        ('desempleo_50', 'Desocupación · 50 años o más', 'micro', 2026, 'Ambos sexos, edad ≥ 50. Cálculo propio con microdatos ENE y factor fact_cal.'),
        ('desempleo_profesional', 'Desocupación · profesionales', 'micro', 2026, 'Educación universitaria completa o posgrado (nivel 9 completo o nivel 10–12). Cálculo propio con microdatos ENE y factor fact_cal; no clasifica por ocupación.')]:
        out.append(dict(id=id, name=name, unit='%', start=start, freq='Trimestre móvil',
                        kind='rate', color='#b45375', provider='INE · ENE' if backend == 'ine' else 'Cálculo propio · microdatos INE ENE',
                        backend=backend, group='desempleo', note=note + ' Fecha = primer día del último mes del trimestre móvil. '
                        + ('Cobertura calculada desde los archivos de 2026; no se ha calculado el histórico anterior. Estimación puntual sin intervalos de confianza ni evaluación de precisión muestral.' if backend == 'micro' else 'Serie oficial SIMEL desde 2010.')))
    ipsa = next(c for c in out if c['id'] == 'ipsa')
    ipsa.update(name='IPSA · Chile', freq='Mensual', backend='bcentral', provider='Banco Central de Chile · BDE',
                note='Cierre mensual del IPSA, índice enero 2003=1000. Serie BDE F013.IBC.IND.N.7.LAC.CL.CLP.BLO.M. Fecha = mes de referencia. Se utiliza esta serie oficial porque el histórico diario de Yahoo tiene vacíos y rezago; no se empalman ambas fuentes.')
    for id, name, unit, code, table, color, note in [
        ('ipc', 'IPC · variación mensual', '% mensual', 'F074.IPC.VAR.Z.Z.C.M', 'CAP_PRECIOS/MN_CAP_PRECIOS/IPC_VAR_MEN1_HIST_NEW', '#d48229', 'Variación mensual oficial del IPC general, elaborado por INE y publicado en BDE. No es el nivel del índice.'),
        ('inflacion', 'Inflación · últimos 12 meses', '% interanual', 'F074.IPC.IND.Z.EP09.C.M', 'CAP_PRECIOS/MN_CAP_PRECIOS/IPC_VAR_ANUAL_HIST_NEW', '#c65b45', 'Variación oficial del IPC respecto del mismo mes del año anterior. No se calcula sumando tasas mensuales redondeadas.'),
        ('expectativa_inflacion_2a', 'Inflación esperada · 2 años', '% interanual', 'F089.IPC.V12.15.M', 'CAP_BDP/MN_EXP_EC11/EXE_BCCH_01/EXE_BCCH_01', '#7460ce', 'Mediana EEE: en 23 meses, variación a 12 meses. Fecha = mes de la encuesta, no mes del pronóstico. La brecha respecto de 3% describe alineación; una observación no demuestra anclaje o desanclaje persistente.')]:
        out.append(dict(id=id, name=name, unit=unit, start=2000, freq='Mensual', kind='rate',
                        backend='bde_prices', provider='Banco Central de Chile · EEE/BDE' if id.startswith('expectativa') else 'INE · vía BDE del Banco Central de Chile',
                        color=color, note=note, series_code=code, table=table,
                        **({'target': 3.0} if id != 'ipc' else {})))
    return out

EXTRA = config()

def bcentral(c, renew=False):
    return bde_series(c, 'F013.IBC.IND.N.7.LAC.CL.CLP.BLO.M',
                      'CAP_ESTADIST_MACRO/MN_EST_MACRO_IV/PEM_INDBUR/PEM_INDBUR',
                      'ipsa_bcentral.html', renew)

def parse_bde(raw, code):
    text = raw.decode('utf-8-sig')
    headers = re.findall(r'<th class="thData"[^>]*>(.*?)</th>', text, re.S)
    headers = [h for h in headers if re.fullmatch(r'[A-Za-z]+\.\d{4}', h)]
    matches = [t for t in re.findall(r'<tr\b[^>]*>.*?</tr>', text, re.S) if f'data-header="{code}"' in t]
    if len(matches) != 1 or not headers:
        raise ValueError('Serie o fechas BDE inesperadas')
    values = re.findall(r'<td class="ar col">(.*?)</td>', matches[0], re.S)
    if len(values) != len(headers):
        raise ValueError('Columnas BDE desalineadas')
    months = {m:i+1 for i,m in enumerate(['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'])}
    rows = []
    for h,v in zip(headers, values):
        v = html.unescape(re.sub('<[^>]+>', '', v)).strip()
        if v in ('', '-', '—'): continue
        m,y = h.split('.')
        value = float(v.replace('.', '').replace(',', '.'))
        if not math.isfinite(value): raise ValueError('Valor BDE inválido')
        rows.append([f'{y}-{months[m]:02d}-01', value])
    if not rows: raise ValueError('BDE sin observaciones')
    return rows

def bde_prices(c, renew=False):
    return bde_series(c, c['series_code'], c['table'], c['id'] + '_bde.html', renew)


def bde_series(c, code, table, filename, renew=False):
    root = 'https://si3.bcentral.cl/Siete/ES/Siete/Cuadro/' + table
    def url(year):
        return root + '?cbFechaInicio=' + str(year) + '&cbFechaTermino=' + str(today().year) + '&cbFrecuencia=MONTHLY&cbCalculo=NONE'
    baseline = RAW / filename
    recent = RAW / (baseline.stem + '_reciente.html')
    validate = lambda body: parse_bde(body, code)
    rows = dict(validate(get(url(2000), baseline, validator=validate)))
    files = [(baseline, url(2000))]
    if recent.exists():
        previous = validate(recent.read_bytes())
        rows.update(previous)
    # Recuperar también años transcurridos si el panel no se abrió en mucho tiempo.
    start = min(today().year - 1, int(max(rows)[:4]))
    if renew:
        incoming = validate(get(url(start), recent, True, validator=validate))
        rows.update(incoming)
    if recent.exists():
        files.append((recent, url(start)))
    return pack(c, sorted(rows.items()), files)

def end_month(start, offset=2):
    d = dt.date.fromisoformat(start[:10])
    m = d.year * 12 + d.month - 1 + offset
    return dt.date(m // 12, m % 12 + 1, 1).isoformat()

def pack(c, rows, files, **extra):
    seen = {}
    for date, value in rows:
        dt.date.fromisoformat(date)
        if not math.isfinite(value) or (c['kind'] == 'level' and value <= 0):
            raise ValueError('Valor inválido')
        if date < '2000-01-01' or date > today().isoformat():
            continue
        if date in seen and seen[date] != value:
            raise ValueError('Duplicado contradictorio')
        seen[date] = value
    if not seen:
        raise ValueError('Serie vacía: ' + c['id'])
    manifest = [dict(file=p.name, url=url, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p, url in files]
    return dict(**c, data=sorted(seen.items()), checked=dt.datetime.fromtimestamp(max(p.stat().st_mtime for p, _ in files), dt.timezone.utc).isoformat(),
                manifest=manifest, **extra)

def market(c, renew=False):
    end = int(dt.datetime.combine(today() + dt.timedelta(days=1), dt.time(), dt.timezone.utc).timestamp())
    url = f'https://query2.finance.yahoo.com/v8/finance/chart/{quote(c["symbol"], safe="")}?period1=946684800&period2={end}&interval=1d'
    p = RAW / (c['id'] + '_yahoo.json')
    d = json.loads(get(url, p, renew))['chart']['result'][0]
    if d['meta']['symbol'] != c['symbol']:
        raise ValueError('Símbolo incorrecto')
    tz = ZoneInfo(d['meta']['exchangeTimezoneName'])
    rows = [[dt.datetime.fromtimestamp(t, tz).date().isoformat(), float(v)]
            for t, v in zip(d['timestamp'], d['indicators']['quote'][0]['close']) if v is not None]
    return pack(c, rows, [(p, url)])

def ine(c, renew=False):
    flow = 'DF_TDES_EDAD' if c['id'] == 'desempleo_juvenil' else 'DF_TDES_SEXO'
    url = f'https://sdmx.ine.gob.cl/rest/data/CL01,{flow},1.0?format=csv'
    p = RAW / (flow + '.csv')
    records = list(csv.DictReader(io.StringIO(get(url, p, renew).decode('utf-8-sig'))))
    rows, flags = [], {}
    for r in records:
        if r['AREA_REF'] != '_T':
            continue
        if flow.endswith('EDAD'):
            if r['EDAD'] != 'Y15T24':
                continue
        elif r['SEXO'] != ('F' if c['id'] == 'desempleo_femenino' else 'AS'):
            continue
        if r['INDICADOR'] != 'TDES' or r['UNIDAD'] != 'RT' or not r['TIME_PERIOD'].endswith('/P3M'):
            raise ValueError('Definición INE inesperada')
        date = end_month(r['TIME_PERIOD'])
        rows.append([date, float(r['OBS_VALUE'])])
        flags[date] = r.get('OBS_STATUS', '')
    return pack(c, rows, [(p, url)], quality_flags=flags)

def calculate_micro(raw):
    rows = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';')
    totals = {id: [0., 0., 0, 0] for id in ['total', 'mujeres', 'juvenil', 'desempleo_50', 'desempleo_profesional']}
    period = None
    for r in rows:
        ref = end_month(f'{int(r["ano_trimestre"]):04d}-{int(r["mes_central"]):02d}-01', 1)
        if period and period != ref:
            raise ValueError('Más de un trimestre en el archivo')
        period = ref
        if r['activ'] not in ('1', '2'):
            continue
        age, level = int(r['edad']), int(r['nivel'])
        weight = float(r['fact_cal'].replace(',', '.'))
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError('Ponderador inválido')
        groups = ['total']
        if r['sexo'] == '2': groups.append('mujeres')
        if 15 <= age <= 24: groups.append('juvenil')
        if age >= 50: groups.append('desempleo_50')
        if (level == 9 and r['termino_nivel'] == '1') or level in (10, 11, 12):
            groups.append('desempleo_profesional')
        for g in groups:
            totals[g][1] += weight
            totals[g][3] += 1
            if r['activ'] == '2':
                totals[g][0] += weight
                totals[g][2] += 1
    return dict(period=period, estimates={g: dict(value=100*v[0]/v[1], unemployed_weight=v[0], labour_force_weight=v[1], unemployed_sample=v[2], labour_force_sample=v[3]) for g, v in totals.items() if v[1]})

def micro_all(renew=False):
    """Descubre nuevos CSV de 2026 en adelante; conserva originales comprimidos."""
    with LOCK:
        root = json.loads(get(INE+'hijosCarpeta/', RAW/'ene_folders.json', renew,
                             'idFolder=83b8e18c-5d25-4229-8289-8882d4f21478'))
        estimates, files = [], []
        for folder in root['folder']:
            if not folder['Titulo'].isdigit() or not 2026 <= int(folder['Titulo']) <= today().year:
                continue
            cat = RAW / ('ene_catalogo_' + folder['Titulo'] + '.json')
            docs = json.loads(get(INE+'getArchivos/', cat, renew, 'idFolder='+folder['Id']))['documento']
            for doc in docs:
                if doc['Tipo'].upper() != '.CSV': continue
                url = doc['Url'].replace('http:', 'https:')
                name = url.split('/')[-1].split('?')[0]
                if not re.fullmatch(r'ene-\d{4}-\d{2}-[a-z]+\.csv', name):
                    raise ValueError('Nombre de microdatos inesperado')
                gz = RAW / (name + '.gz')
                calc = RAW / (name + '.estimaciones.json')
                # Las revisiones de INE se identifican por el enlace versionado.
                source_changed = not calc.exists() or json.loads(calc.read_text()).get('url') != url
                if not gz.exists() or (renew and source_changed):
                    raw = subprocess.run(['curl','-sS','-L','--fail','--retry','2','--max-time','120',url], capture_output=True, check=True).stdout
                    result = calculate_micro(raw)
                    tmp = gz.with_suffix('.tmp')
                    tmp.write_bytes(gzip.compress(raw, mtime=0)); tmp.replace(gz)
                    result['url'] = url
                    calc.write_text(json.dumps(result, ensure_ascii=False))
                if not calc.exists():
                    result = calculate_micro(gzip.decompress(gz.read_bytes())); result['url'] = url
                    calc.write_text(json.dumps(result, ensure_ascii=False))
                estimates.append(json.loads(calc.read_text()))
                files.append((gz, url))
        return estimates, files

def load_extra(c, renew=False):
    RAW.mkdir(exist_ok=True)
    if c['backend'] == 'bde_prices': return bde_prices(c, renew)
    if c['backend'] == 'bcentral': return bcentral(c, renew)
    if c['backend'] == 'market': return market(c, renew)
    if c['backend'] == 'ine': return ine(c, renew)
    estimates, files = micro_all(renew)
    return pack(c, [[e['period'], e['estimates'][c['id']]['value']] for e in estimates], files,
                calculation_details={e['period']: e['estimates'][c['id']] for e in estimates})


def parse_uf_sii(raw, year):
    text=raw.decode('utf-8', errors='replace')
    months={m:i+1 for i,m in enumerate('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split())}
    rows={}
    for table in re.findall(r'<table\b[^>]*>.*?</table>',text,re.S|re.I):
        title=re.search(r'<h2[^>]*>\s*([A-Za-z]+)\s*</h2>',table,re.I)
        if not title or title[1].lower() not in months: continue
        month=months[title[1].lower()]
        for day,value in re.findall(r'<th\b[^>]*>\s*<strong>(\d{1,2})</strong>\s*</th>\s*<td\b[^>]*>(.*?)</td>',table,re.S|re.I):
            value=html.unescape(re.sub('<[^>]+>','',value)).strip()
            if not value: continue
            date=dt.date(int(year),month,int(day)).isoformat()
            number=float(value.replace('.','').replace(',','.'))
            if not math.isfinite(number) or number<=0: raise ValueError('UF incorrecta')
            if date in rows and rows[date]!=number: raise ValueError('UF contradictoria')
            if date<=today().isoformat(): rows[date]=number
    if not rows: raise ValueError('SII sin valores UF válidos')
    return sorted(rows.items())

def official_indicator(id, year):
    if id=='uf':
        url=f'https://www.sii.cl/valores_y_fechas/uf/uf{year}.htm'
        path=RAW/f'uf_sii_{year}.html'
        parser=lambda raw:parse_uf_sii(raw,year)
        provider='SII (actualización); mindicador.cl (histórico)'
        note='UF diaria en pesos publicada por SII. Se conserva el histórico previo de mindicador.cl; las fechas consultadas se reemplazan por la fuente oficial. Solo se muestran valores vigentes hasta hoy.'
    elif id=='imacec':
        url=f'https://si3.bcentral.cl/Siete/ES/Siete/Cuadro/CAP_CCNN/MN_CCNN76/CCNN2018_IMACEC_01_A/638131830306828693?cbFechaInicio={year}&cbFechaTermino={year}&cbFrecuencia=MONTHLY&cbCalculo=YTYPCT'
        path=RAW/f'imacec_oficial_{year}.html'
        parser=lambda raw:parse_bde(raw,'F032.IMC.IND.Z.Z.EP18.Z.Z.0.M|YTYPCT')
        provider='Banco Central de Chile · BDE (actualización); mindicador.cl (histórico)'
        note='Imacec original, variación respecto del mismo mes del año anterior publicada por BDE (YTYPCT); no es variación mensual ni serie desestacionalizada. Se conservan los años históricos no consultados de mindicador.cl. Sujeto a revisiones.'
    else: raise ValueError('Indicador oficial desconocido')
    rows=[(date,value) for date,value in parser(get(url,path,renew=True,validator=parser)) if date.startswith(str(year)) and date<=today().isoformat()]
    if not rows: raise ValueError('Año oficial sin observaciones vigentes')
    return dict(codigo=id,unidad_medida='Pesos' if id=='uf' else 'Porcentaje',serie=[dict(fecha=date+'T00:00:00Z',valor=value) for date,value in rows],provider=provider,note=note,source_url=url)
