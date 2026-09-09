# Compartir por WhatsApp y abrir desde el celular

El destinatario abre un enlace HTTPS en Safari o Chrome. No instala Python ni abre
Terminal. El panel consulta el último dato disponible de cada fuente al abrir y al
recuperar la conexión, conservando el respaldo cuando una fuente falla.

También puede descargar «HTML para compartir». Ese archivo incluye el histórico
y la dirección del servicio: al abrirlo en un navegador consulta el mismo servicio.
La vista previa de una aplicación puede no ejecutar JavaScript; para ese caso se
comparte el enlace. Un HTML sin servicio conectado solo actualiza las fuentes que
permiten consultas directas desde el navegador.

## Estado

Código preparado para publicación. Aún no hay servicio público ni URL configurada.
No confundir la verificación local con un sitio ya publicado.

## Publicación desde el navegador, una sola vez

Se incluye `Dockerfile` y `render.yaml` para Render. El servicio puede alojarse también
en cualquier plataforma compatible con Docker y HTTPS.

1. Crear un repositorio con el contenido del paquete de publicación. El paquete
   incluye solamente el panel y sus datos económicos; no los archivos de postulaciones.
2. En Render, conectar el repositorio y crear un Web Service con runtime Docker,
   o utilizar el Blueprint `render.yaml`.
3. Verificar `/healthz`. Render asigna una dirección HTTPS y la proporciona mediante
   `RENDER_EXTERNAL_URL`. En otro alojamiento, configurar `PUBLIC_URL` con la dirección
   HTTPS del servicio (sin barra final).
4. Abrir esa dirección, comprobar que responden las 16 series y usar «Compartir enlace».
5. Descargar el HTML desde la versión publicada para que incluya la dirección real.
   El archivo descargado puede enviarse por WhatsApp como documento.

El plan gratuito de Render se suspende después de 15 minutos sin visitas y puede
tardar alrededor de un minuto en despertar. Su disco es temporal: tras reiniciar,
se recupera el respaldo incluido en el despliegue y se consultan las fuentes otra vez.
Para uso frecuente y arranque inmediato, elegir un alojamiento que permanezca activo.
No se contrata ningún plan ni se publica nada automáticamente con estos archivos.

## Servicio y verificación

`web_publica.py` sirve el sitio y endpoints de solo lectura para las fuentes registradas.
La respuesta permite CORS sin credenciales para que los archivos HTML puedan consultarla.
No acepta URLs arbitrarias, no publica archivos del directorio y comparte los resultados
durante cinco minutos. Se ejecuta con un worker y doce hilos para compartir caché y
las escrituras de respaldo. El proxy del alojamiento termina HTTPS.

`verificar_portatil.py` verifica en Chrome una pantalla móvil, descarga del HTML,
consulta desde `file://`, CORS real, ausencia de red y reconexión. Usa fuentes simuladas;
la consulta real anterior consta en `verificacion_red.json`. La vista previa nativa de
WhatsApp y un dispositivo físico no están cubiertos por esa simulación.

Fuentes técnicas:
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- https://render.com/docs/web-services
- https://render.com/docs/free
