# Monitor meteorológico · Gran Concepción

**App en línea: [metgeo-concepcion.streamlit.app](https://metgeo-concepcion.streamlit.app/)** ·
por Bruno Herrera · METGEO ([github.com/Heszo](https://github.com/Heszo))

App Streamlit que junta en un solo lugar lo **observado** en las estaciones del Gran Concepción y lo
**pronosticado** por 7 modelos globales y un super-ensamble de 143 miembros, para lluvia, temperatura,
humedad, viento, ráfagas, dirección del viento y presión. Sirve para ver qué viene y, sobre todo,
para **comparar modelos entre sí y contra la observación**.

Se actualiza sola y no necesita claves ni base de datos: las observaciones se descargan al abrir la app
(caché de una hora) y los pronósticos los publica cada hora una GitHub Action (ver más abajo).

## Vistas

| Vista | Qué muestra |
|---|---|
| **Presentación** | Portada: qué es el proyecto, las condiciones de ahora, lo que viene en 24 h y los próximos 3 días, accesos a cada vista, cómo funciona, fuentes y advertencias. |
| **Comparar modelos** | Una variable a la vez en el sitio elegido: los 7 modelos, la banda p10–p90 del super-ensamble y lo observado. Debajo, una tabla con sesgo, MAE, RMSE y correlación de cada modelo en las horas ya ocurridas. La lluvia se dibuja como histograma horario. |
| **Lluvia** | Mapa satelital con el acumulado observado por estación, histograma horario (mediana y p10–p90 del ensamble contra el observado por grupo o estación), acumulado y tarjetas de lluvia esperada cada 6 h con ráfaga. |
| **Meteograma** | Las 6 variables apiladas en un mismo eje de tiempo, para un modelo o la mediana de los modelos elegidos. |
| **Mapa de estaciones** | Última medición (o lluvia acumulada en las últimas N horas) de cada estación sobre imagen satelital. |

Los modelos se consultan en las coordenadas del sitio elegido en la barra lateral.

## Fuentes (todas públicas)

| Fuente | Variables | Cobertura |
|---|---|---|
| [VIPNet](https://vipnet.mop.gob.cl) (DGA/MOP) | lluvia (16 estaciones), temperatura y humedad (9) | costa, ciudad e interior del Gran Concepción, cada 30 min |
| [METAR SCIE](https://aviationweather.gov/data/api/) (Carriel Sur, NOAA Aviation Weather Center) | temperatura, humedad, viento, ráfaga, dirección, presión QNH | aeropuerto, cada hora |
| [Open-Meteo Forecast](https://open-meteo.com/en/docs) | GFS, IFS, ICON, GEM, GSM, UM, ARPEGE | 1–7 días atrás y 1–7 días hacia adelante |
| [Open-Meteo Ensemble](https://open-meteo.com/en/docs/ensemble-api) | GEFS (31) + IFS-ENS (51) + ICON-EPS (40) + GEPS (21) | ídem |
| Esri World Imagery | imagen satelital de los mapas | — |

Advertencias:
- Observaciones preliminares, sin control de calidad.
- Los METAR informan ráfaga solo cuando es significativa.
- Los días pasados de Open-Meteo son pronósticos de corto plazo de corridas recientes, no reanálisis;
  la verificación compara un punto de grilla con una estación, así que incluye error de representatividad.
- Es una herramienta de divulgación: no reemplaza los avisos de SENAPRED ni de la DMC.
- Open-Meteo es gratuito para uso no comercial.

## Cómo se actualizan los pronósticos

Open-Meteo gratuito limita las consultas por dirección IP, y la IP de Streamlit Community Cloud es
compartida con muchas otras apps: consultado desde ahí suele responder `429 Too Many Requests`. Por eso:

1. La GitHub Action [`pronosticos.yml`](.github/workflows/pronosticos.yml) corre cada hora (minuto 17),
   ejecuta `actualiza_pronosticos.py` para los 17 sitios (7 días atrás y 7 adelante) y publica 4 archivos
   parquet más `meta.json` en la rama [`datos`](../../tree/datos). La rama se reescribe en cada corrida,
   sin historial, así el repositorio no crece.
2. La app lee esa copia. Si falta o tiene más de 3 horas, consulta Open-Meteo en vivo (con reintentos);
   si tampoco responde, muestra un aviso y sigue mostrando las observaciones.

Para forzar una actualización: pestaña *Actions* → *Actualizar pronósticos* → *Run workflow*.
GitHub pausa las Actions programadas de un repositorio público tras 60 días sin actividad; si pasa,
basta reactivarla desde la misma pestaña.

## Estructura

```
app.py                     punto de entrada: st.App que mantiene la caché caliente
streamlit_app.py           navegación (st.navigation), controles de la barra lateral y encabezado
app_pages/                 una página por vista: presentación, comparar, lluvia, meteograma, mapa
comun.py                   cargas con caché y utilidades compartidas por las páginas
fuentes.py                 descarga y ordena los datos; catálogo de variables, modelos y estaciones
actualiza_pronosticos.py   baja los pronósticos de todos los sitios (lo corre la GitHub Action)
tests/                     pruebas de humo con st.testing.AppTest
.github/workflows/         Actions: pronósticos cada hora y pruebas en cada push
.streamlit/                tema y configuración de la caché
requirements.txt           dependencias
```

## Velocidad

- Las cargas usan caché con `ttl` de 15 minutos y `refresh_mode="background"`: cuando una entrada
  vence, el visitante recibe al instante la versión anterior y la nueva se baja por detrás.
- `app.py` envuelve la app en `st.App` y, desde el servidor, toca esas cargas al arrancar y cada 5
  minutos, así que la caché está caliente aunque nadie haya entrado en horas.
- Las claves de caché no dependen de los controles: siempre se pide la ventana máxima (7 días) y se
  recorta en la página.
- Solo se ejecuta la página abierta.

## Enlaces compartibles

El sitio, los días, la variable y la estación elegida quedan en la URL, así que se puede compartir una
vista exacta; por ejemplo
`/comparar?sitio=Lota&variable=Presión+al+nivel+del+mar&pasado=5`.

Para agregar o quitar estaciones, o cambiar qué variables mide cada una, editar `SITIOS` en
`fuentes.py`. El catálogo completo de VIPNet sale de
`POST https://vipnet.mop.gob.cl/v1/vipnet/estaciones` con `{"tipoEstacion": 0}`
(tipos: 0 lluvia, 1 temperatura, 4 humedad, 5 viento).

## Correr en tu computador

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Pruebas: `cd tests && python -m pytest -q`.

Para usar una copia local de los pronósticos (por ejemplo, recién generada con
`python actualiza_pronosticos.py salida`), definir `MONITOR_DATOS=salida` antes de lanzar la app.

## Publicar en Streamlit Community Cloud (gratis)

1. Entrar a [share.streamlit.io](https://share.streamlit.io) con la cuenta de GitHub.
2. *Create app* → elegir este repositorio, rama `main`, archivo `app.py`.
3. Elegir la URL (por ejemplo `monitor-meteo-concepcion.streamlit.app`) y *Deploy*.

La app se duerme tras unos días sin visitas; la primera visita la despierta.

## Autoría y licencia

Bruno Herrera · METGEO · [github.com/Heszo](https://github.com/Heszo). Código bajo licencia [MIT](LICENSE).
