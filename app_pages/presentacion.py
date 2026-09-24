"""Presentación: portada del proyecto, condiciones actuales, accesos a cada vista, fuentes y autoría."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import comun as C
import fuentes as F
from comun import BANDA, DIAS, EJE_T, NEGRO, ROJO, barra, fmt, linea_ahora, nombre_modelo


FOTO_PORTADA = "app/static/caracol.jpg"  # cerro Caracol, Concepción (servida desde static/)
TARJETAS = [
    ("Comparar modelos", "comparar", ":material/stacked_line_chart:",
     "Una variable a la vez: los 7 modelos, la banda del super-ensamble y lo observado. Debajo, qué modelo "
     "anduvo mejor en los últimos días (sesgo, error medio, correlación)."),
    ("Lluvia", "lluvia", ":material/water_drop:",
     "Acumulado por estación sobre imagen satelital, histograma hora a hora, acumulado del evento y lluvia "
     "esperada cada 6 horas con ráfagas."),
    ("Meteograma", "meteograma", ":material/monitoring:",
     "Temperatura, humedad, viento, dirección, presión y lluvia apiladas en un mismo eje de tiempo, para un "
     "modelo o la mediana de todos."),
    ("Mapa de estaciones", "mapa", ":material/map:",
     "La última medición de cada estación sobre imagen satelital: dónde hace más frío, dónde llueve más."),
]

st.markdown(f"""
<div style="position:relative;border-radius:18px;padding:3rem 2.4rem 2.4rem;margin:.4rem 0 1.4rem;color:white;
        background:linear-gradient(115deg,rgba(0,32,80,.90) 30%,rgba(0,64,144,.40)),
                   url('{FOTO_PORTADA}') center 60%/cover;">
  <div style="font-size:.85rem;letter-spacing:.12em;text-transform:uppercase;opacity:.85">
    Monitor meteorológico del Gran Concepción</div>
  <div style="font-size:2.9rem;font-weight:800;line-height:1.1;margin:.35rem 0 .8rem">MetGeo Concepción</div>
  <div style="font-size:1.15rem;max-width:46rem;opacity:.95;line-height:1.5">
Lo que está pasando y lo que viene, contado a la vez por las estaciones de la zona y por
los principales modelos del mundo. Y, sobre todo, <b>qué tan bien le está acertando cada modelo</b>.</div>
  <div style="display:flex;flex-wrap:wrap;gap:.6rem;margin-top:1.4rem">
{"".join(f'<span style="background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.3);'
         f'border-radius:999px;padding:.35rem .9rem;font-size:.92rem"><b>{a}</b> {b}</span>'
         for a, b in [("17", "sitios de observación"), ("7", "variables"), ("7", "modelos globales"),
                      ("143", "miembros de ensamble"), ("cada hora", "se actualiza")])}
  </div>
  <div style="position:absolute;right:1rem;bottom:.6rem;font-size:.72rem;opacity:.7">Foto: cerro Caracol, Concepción</div>
</div>""", unsafe_allow_html=True)

# --- ahora mismo
st.subheader("Ahora mismo", icon=":material/schedule:", anchor=False)
c = C.controles()
sitio, ahora, metar, pron, avisos = c.sitio, c.ahora, c.metar, c.pron, c.avisos
origen_pron, observado, det_var = c.origen_pron, c.observado, c.det_var
C.metricas_ahora(c)
ahora_h = pd.Timestamp(ahora).floor("h")
prox = lambda df: df[(df.index > ahora_h) & (df.index <= ahora_h + pd.Timedelta(hours=24))]  # noqa: E731
temp = det_var("temperatura")
raf = det_var("rafaga")
if not temp.empty:
    st.markdown(f"**Próximas 24 horas en {sitio['nombre']}** (mediana de los 7 modelos; la lluvia, del "
                "super-ensamble)")
    fila = st.container(horizontal=True, gap="small")
    tm = prox(temp).median(axis=1)
    fila.metric("Temperatura mínima", fmt(tm.min(), 0, "°C"), border=True)
    fila.metric("Temperatura máxima", fmt(tm.max(), 0, "°C"), border=True)
    fila.metric("Ráfaga máxima", fmt(prox(raf).median(axis=1).max(), 0, "km/h") if not raf.empty else "—", border=True)
    if pron["pp"] is not None:
        ll = prox(pron["pp"]).sum().values
        q10, q50, q90 = np.percentile(ll, [10, 50, 90])
        fila.metric("Lluvia esperada", fmt(q50, 0, "mm"), f"rango {q10:.0f}–{q90:.0f} mm", delta_color="off", border=True)

    # adelanto: 24 h hacia atrás y 72 h hacia adelante
    ventana = lambda df: df[(df.index > ahora_h - pd.Timedelta(hours=24)) &  # noqa: E731
                            (df.index <= ahora_h + pd.Timedelta(hours=72))]
    fp = make_subplots(specs=[[{"secondary_y": True}]])
    if pron["pp"] is not None:
        q = F.percentiles(ventana(pron["pp"]))
        fp.add_trace(go.Bar(x=q.index - pd.Timedelta(minutes=30), y=q.p50, width=3.6e6 * 0.85,
                            marker_color="#6FA3D2", name="lluvia esperada (mm/h)", opacity=.9),
                     secondary_y=True)
    tv = ventana(temp).median(axis=1)
    fp.add_trace(go.Scatter(x=tv.index, y=tv.values, line=dict(color="#d6604d", width=3),
                            name="temperatura pronosticada (°C)"), secondary_y=False)
    o = observado(sitio, "temperatura")
    if o is not None:
        o = o[o.index > ahora_h - pd.Timedelta(hours=24)]
        fp.add_trace(go.Scatter(x=o.index, y=o.values, line=dict(color=NEGRO, width=2.4),
                                name="temperatura observada (°C)"), secondary_y=False)
    linea_ahora(fp, pd.Timestamp(ahora))
    fp.update_yaxes(title_text="°C", secondary_y=False)
    tope = float(q.p50.max()) if pron["pp"] is not None and len(q) else 1.0
    fp.update_yaxes(title_text="mm/h", secondary_y=True, showgrid=False, tickmode="auto",
                    range=[0, max(tope, 1.0) * 2.2])  # la lluvia queda en la mitad de abajo
    fp.update_layout(title=f"Ayer, hoy y los próximos 3 días · {sitio['nombre']}", height=330,
                     margin=dict(l=10, r=10, t=45, b=10), hovermode="x unified", bargap=0,
                     legend=dict(orientation="h", y=-0.25, yanchor="top"))
    fp.update_xaxes(**EJE_T)
    st.plotly_chart(fp, config=barra(), key="adelanto")
    st.caption("El sitio se cambia arriba, en «Sitio». La línea punteada roja marca la hora actual.")

# --- qué se puede hacer
st.subheader("Qué puedes hacer aquí", icon=":material/explore:", anchor=False)
cols = st.columns(4)
for col, (nombre, archivo, icono, texto) in zip(cols, TARJETAS):
    with col.container(border=True, height=235):
        st.markdown(f"**{nombre}**")
        st.caption(texto)
        st.page_link(f"app_pages/{archivo}.py", label="Abrir", icon=icono, width="stretch")

# --- cómo funciona
st.subheader("Cómo funciona", icon=":material/settings_suggest:", anchor=False)
col_red, col_pasos = st.columns([5, 6], gap="large")
with col_red:
    fred = go.Figure()
    for g, color in F.GRUPOS.items():
        ss = [x for x in F.SITIOS if x["grupo"] == g]
        fred.add_trace(go.Scattermap(lat=[x["lat"] for x in ss], lon=[x["lon"] for x in ss], mode="markers",
                                     marker=dict(size=13, color=color), name=g,
                                     text=[x["nombre"] for x in ss], hovertemplate="%{text}<extra></extra>"))
    fred.update_layout(map=dict(style="white-bg", center=dict(lat=-36.86, lon=-72.95), zoom=8.3,
                                layers=[dict(sourcetype="raster", source=[F.ESRI], below="traces")]),
                       margin=dict(l=0, r=0, t=0, b=0), height=380,
                       legend=dict(orientation="h", y=0.02, x=0.02, bgcolor="rgba(255,255,255,.85)"))
    st.plotly_chart(fred, config=barra("resetViewMap"), key="mapa_red")
    st.caption("La red: 16 estaciones VIPNet y el aeropuerto Carriel Sur, agrupadas en costa, ciudad e "
               "interior. Imagen: Esri World Imagery.")
with col_pasos:
    for n, titulo, texto in [
        ("1", "Observa", "Cada hora se leen las 16 estaciones de la red VIPNet (DGA/MOP), que miden lluvia "
                         "cada 30 minutos (9 de ellas también temperatura y humedad), y el reporte METAR del "
                         "aeropuerto Carriel Sur, la única fuente pública de viento, ráfagas y presión."),
        ("2", "Pronostica", "Una GitHub Action baja cada hora, para cada sitio, el pronóstico de 7 modelos "
                            "globales (GFS, IFS, ICON, GEM, GSM, UM y ARPEGE) y de 143 miembros de "
                            "ensamble de cuatro centros, que dan la banda de incertidumbre."),
        ("3", "Compara", "Lo ya ocurrido se contrasta con lo que cada modelo pronosticó para esas mismas "
                         "horas: sesgo, error medio y correlación, para saber en quién confiar esta semana."),
    ]:
        st.markdown(
            f'<div style="display:flex;gap:1rem;align-items:flex-start;margin-bottom:1.1rem">'
            f'<div style="flex:0 0 2.4rem;height:2.4rem;border-radius:50%;background:#004090;color:white;'
            f'font-weight:800;display:flex;align-items:center;justify-content:center">{n}</div>'
            f'<div><div style="font-weight:700;font-size:1.05rem">{titulo}</div>'
            f'<div style="color:#444;line-height:1.5">{texto}</div></div></div>', unsafe_allow_html=True)

# --- fuentes y advertencias
st.subheader("Fuentes y advertencias", icon=":material/fact_check:", anchor=False)
col_f, col_c = st.columns([7, 5], gap="large")
col_f.markdown("""
| Fuente | Qué aporta | Frecuencia |
|---|---|---|
| [VIPNet](https://vipnet.mop.gob.cl) (DGA/MOP) | lluvia (16 estaciones), temperatura y humedad (9) | 30 min |
| [METAR SCIE](https://aviationweather.gov) (Carriel Sur, NOAA AWC) | temperatura, humedad, viento, ráfaga, dirección, presión QNH | 1 h |
| [Open-Meteo](https://open-meteo.com) | GFS (NOAA), IFS (ECMWF), ICON (DWD), GEM (Canadá), GSM (JMA), UM (UK Met Office), ARPEGE (Météo-France) | 1 h |
| [Open-Meteo Ensemble](https://open-meteo.com/en/docs/ensemble-api) | GEFS (31) + IFS-ENS (51) + ICON-EPS (40) + GEPS (21) = 143 miembros | 1 h |
| Esri World Imagery | imagen satelital de los mapas | — |
""")
col_c.markdown("""
- Datos observados **preliminares**, sin control de calidad.
- Los METAR informan ráfaga solo cuando es significativa.
- La presión del METAR es QNH, equivalente en la práctica a la presión al nivel del mar.
- Los días pasados de Open-Meteo son pronósticos de corto plazo, no reanálisis; parte del error medido es de
  representatividad (punto de grilla contra estación).
- Es una herramienta de divulgación: **no reemplaza los avisos de SENAPRED ni de la DMC**.
""")

# --- autoría
st.space("medium")
with st.container(horizontal=True, vertical_alignment="center", gap="large"):
    st.image(str(C.LOGO_COMPLETO), width=300)
    st.markdown(
        "Hecho por **Bruno Herrera** · MetGeo Spa  \n"
        ":material/code: [github.com/Heszo](https://github.com/Heszo) · código abierto (MIT) en "
        "[github.com/Heszo/monitor-meteo-concepcion](https://github.com/Heszo/monitor-meteo-concepcion)")
st.caption(f"Consultado el {ahora:%d/%m/%Y %H:%M} (hora de Chile) · pronóstico: "
           f"{origen_pron or 'no disponible'}. Open-Meteo gratuito limita las consultas por IP, así que los "
           "pronósticos los publica cada hora una GitHub Action y la app lee esa copia.")
for v in ("precipitacion", "temperatura", "humedad"):
    avisos.extend(C.vipnet_seguro(v)[1])
if metar.empty:
    avisos.append("METAR SCIE: sin datos")
if avisos:
    with st.expander("Avisos de descarga"):
        st.write("\n".join(f"- {a}" for a in sorted(set(avisos))))
