# Monitor meteorológico · Gran Concepción

App Streamlit que junta en un solo lugar lo **observado** en las estaciones del Gran Concepción y lo
**pronosticado** por 7 modelos globales y un super-ensamble de 143 miembros, para lluvia, temperatura,
humedad, viento, ráfagas, dirección del viento y presión. Sirve para ver qué viene y, sobre todo,
para **comparar modelos entre sí y contra la observación**.

Se actualiza sola: descarga los datos al abrirse y los guarda en caché una hora. No necesita claves
ni base de datos.

## Vistas

| Vista | Qué muestra |
|---|---|
| **Comparar modelos** | Una variable a la vez en el sitio elegido: los 7 modelos, la banda p10–p90 del super-ensamble y lo observado. Debajo, una tabla con sesgo, MAE, RMSE y correlación de cada modelo en las horas ya ocurridas. La lluvia se dibuja como histograma horario. |
| **Lluvia** | Mapa satelital con el acumulado observado por estación, histograma horario (mediana y p10–p90 del ensamble contra el observado por grupo o estación), acumulado y tarjetas de lluvia esperada cada 6 h con ráfaga. |
| **Meteograma** | Las 6 variables apiladas en un mismo eje de tiempo, para un modelo o la mediana de los modelos elegidos. |
| **Mapa de estaciones** | Última medición (o lluvia acumulada en las últimas N horas) de cada estación sobre imagen satelital. |
| **Acerca de** | Fuentes y advertencias. |

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

## Estructura

```
app.py              interfaz (Streamlit + Plotly)
fuentes.py          descarga y ordena los datos; catálogo de variables, modelos y estaciones
.streamlit/         tema de la app
requirements.txt    dependencias
```

Para agregar o quitar estaciones, o cambiar qué variables mide cada una, editar `SITIOS` en
`fuentes.py`. El catálogo completo de VIPNet sale de
`POST https://vipnet.mop.gob.cl/v1/vipnet/estaciones` con `{"tipoEstacion": 0}`
(tipos: 0 lluvia, 1 temperatura, 4 humedad, 5 viento).

## Correr en tu computador

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Publicar en Streamlit Community Cloud (gratis)

1. Entrar a [share.streamlit.io](https://share.streamlit.io) con la cuenta de GitHub.
2. *Create app* → elegir este repositorio, rama `main`, archivo `app.py`.
3. Elegir la URL (por ejemplo `monitor-meteo-concepcion.streamlit.app`) y *Deploy*.

La app se duerme tras unos días sin visitas; la primera visita la despierta.

## Autoría y licencia

Bruno Herrera · METGEO. Código bajo licencia [MIT](LICENSE).
