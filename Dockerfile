FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY panel/requirements-web.txt /app/panel/requirements-web.txt
RUN pip install --no-cache-dir -r panel/requirements-web.txt
COPY panel/agenda.py panel/agenda_respaldo.json panel/fuentes.py panel/servidor.py panel/web_publica.py panel/plantilla.html panel/panel_datos.json /app/panel/
ADD datos_1.tar.gz /app/panel/
ADD datos_2.tar.gz /app/panel/
ADD datos_3.tar.gz /app/panel/
RUN useradd --create-home panel && chown -R panel:panel /app
USER panel
ENV PORT=10000 PYTHONUNBUFFERED=1
CMD ["sh", "-c", "exec gunicorn --chdir panel --bind 0.0.0.0:${PORT} --workers 1 --threads 12 --timeout 180 web_publica:application"]
