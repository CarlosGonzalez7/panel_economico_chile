# panel_economico_chile
# Observatorio Económico de Chile

Dashboard interactivo para consultar, explorar y descargar indicadores macroeconómicos y financieros de Chile.

🔗 **Demo:** https://panel-economico-chile.onrender.com/

## Objetivo

El proyecto busca centralizar en una sola herramienta indicadores económicos provenientes de distintas fuentes públicas y facilitar su consulta, visualización y descarga reproducible.

Además de presentar el último dato disponible, el panel permite explorar series históricas, seleccionar rangos temporales, cambiar la frecuencia de visualización y exportar los datos para análisis posterior.

## Funcionalidades

* Seguimiento de indicadores macroeconómicos y financieros.
* Agenda de Reuniones de Política Monetaria e IPoM.
* Exploración interactiva de series históricas.
* Actualización automática de datos.
* Validación de fechas y observaciones.
* Descarga de series en CSV.
* Construcción de panel mensual.
* Exportación de instantáneas en JSON.
* Metadatos sobre frecuencia, cobertura y fuente.
* Estimaciones propias de algunos indicadores laborales a partir de microdatos agregados de la Encuesta Nacional de Empleo.

## Fuentes de datos

El proyecto integra información proveniente de:

* Banco Central de Chile — Base de Datos Estadísticos (BDE) y publicaciones oficiales.
* Instituto Nacional de Estadísticas (INE).
* mindicador.cl.
* Yahoo Finance.

Las fuentes y metodologías específicas de cada indicador se identifican dentro del propio panel.

## Flujo de datos

```text
Fuentes externas
      ↓
Extracción de datos
      ↓
Validación y limpieza
      ↓
Transformaciones y agregaciones
      ↓
Construcción del payload
      ↓
Dashboard interactivo
      ↓
CSV / JSON para análisis
```

## Tecnologías

* Python
* HTML
* CSS
* JavaScript
* APIs y fuentes de datos web
* Git / GitHub
* Codex como herramienta de apoyo al desarrollo

## Decisiones metodológicas

El panel no interpola observaciones faltantes ni construye series artificiales para completar períodos sin cobertura.

Las series conservan sus frecuencias originales y, cuando se genera un panel mensual, se explicita el método utilizado para agregar observaciones diarias.

Las estimaciones construidas a partir de microdatos de la Encuesta Nacional de Empleo se presentan únicamente de forma agregada.

El panel tampoco corrige revisiones históricas ni reconstruye vintages de información. Por ello, no debe interpretarse como una base real-time para ejercicios econométricos que requieran conocer exactamente la información disponible en cada fecha histórica.

## Reproducibilidad

La aplicación permite descargar:

* la serie actualmente seleccionada;
* todas las series en formato largo;
* un panel mensual;
* una instantánea en JSON con datos y metadatos.

Esto facilita llevar los datos posteriormente a R, Stata, Python u otras herramientas de análisis.

## Limitaciones

Los datos pueden estar sujetos a revisiones, cambios metodológicos, rezagos de publicación e interrupciones de las fuentes originales.

Antes de utilizar los resultados en investigación, informes o toma de decisiones, se recomienda contrastarlos con las fuentes oficiales.

## Licencias y atribución

Este es un proyecto personal e independiente y no está afiliado, patrocinado ni respaldado por el Banco Central de Chile, INE, Yahoo Finance, mindicador.cl u otros proveedores.

Los datos del INE se utilizan conforme a su licencia de datos abiertos CC BY-SA 4.0.

Las transformaciones, visualizaciones, agregaciones y cálculos propios son responsabilidad del autor.

Para información detallada sobre fuentes y condiciones de uso, consultar la sección correspondiente dentro del dashboard.

## Autor

**Carlos González**

Magíster en Economía
Pontificia Universidad Católica de Chile

Intereses: economía aplicada, macroeconomía, econometría, análisis de datos y programación.
