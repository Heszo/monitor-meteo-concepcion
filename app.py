"""
Monitor meteorológico del Gran Concepción: lluvia, temperatura, humedad,
viento y presión, observados (VIPNet DGA/MOP y METAR de Carriel Sur) y
pronosticados por 7 modelos globales y un super-ensamble de 143 miembros
(Open-Meteo). Permite comparar modelos entre sí y contra lo observado.

    streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import fuentes as F

st.set_page_config(page_title="Monitor meteorológico · Gran Concepción", page_icon="🌦️", layout="wide")

NEGRO, ROJO, BANDA = "#111111", "#B5323C", "rgba(120,150,190,.22)"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
EJE_T = dict(tickformat="%d/%m<br>%H:%M", nticks=8, tickangle=0)
TTL = 3600

st.markdown("""<style>
[data-testid="stButtonGroup"], [data-testid="stButtonGroup"] > div { flex-wrap: wrap; }
@media (max-width: 640px) {
  .st-key-metricas [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .5rem 1rem; }
  .st-key-metricas [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 1rem) !important; min-width: calc(50% - 1rem) !important; }
}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ caché
# 'clave' (año-mes-día-hora) solo sirve para renovar la caché cada hora.
@st.cache_data(ttl=TTL, show_spinner="Descargando METAR de Carriel Sur…")
def _carga_metar(horas, clave):
    return F.metar("SCIE", horas)


def carga_metar(horas, clave):
    try:
        return _carga_metar(horas, clave)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=TTL, show_spinner="Descargando estaciones VIPNet…")
def carga_vipnet(variable, horas, clave):
    return F.vipnet_variable(variable, horas)


@st.cache_data(ttl=900, show_spinner="Leyendo los pronósticos publicados…")
def carga_publicados(clave15):
    return F.lee_pronosticos()


@st.cache_data(ttl=TTL, show_spinner="Consultando Open-Meteo en vivo…")
def carga_vivo(lat, lon, pasado, futuro, clave):
    return F.pronostico_vivo(lat, lon, pasado, futuro)


VACIO = {"det": {}, "pct": {}, "pp": None, "raf6h": None}
VIEJO = pd.Timedelta(hours=3)


def pronostico(s, pasado, futuro):
    """(pronóstico, origen, error). Primero la copia que publica la GitHub Action cada hora; si falta
    o tiene más de 3 h, Open-Meteo en vivo; si eso también falla, la copia vieja o nada.
    Las funciones con caché lanzan la excepción (así no se cachea una falla) y se atrapa aquí."""
    ahora_utc = pd.Timestamp.now(tz="UTC")
    clave15 = ahora_utc.floor("15min").isoformat()
    try:
        generado, pub = carga_publicados(clave15)
    except Exception:  # noqa: BLE001
        generado, pub = None, {}
    local = lambda t: t.tz_convert(F.ZONA).strftime("%d/%m %H:%M")  # noqa: E731
    if generado is not None and s["id"] in pub and ahora_utc - generado < VIEJO:
        return pub[s["id"]], f"copia publicada a las {local(generado)}", None
    try:
        return carga_vivo(s["lat"], s["lon"], pasado, futuro, ahora_utc.strftime("%Y%m%d%H")), \
            "Open-Meteo en vivo", None
    except Exception as ex:  # noqa: BLE001
        if generado is not None and s["id"] in pub:
            return pub[s["id"]], f"copia publicada a las {local(generado)} (desactualizada)", str(ex)
        return VACIO, None, str(ex)


def barra(boton="resetScale2d"):
    return {"displayModeBar": True, "displaylogo": False, "modeBarButtons": [[boton]]}


def linea_ahora(fig, ahora, xref="x", yref="paper"):
    """add_shape en vez de add_vline: add_vline falla con Timestamps de pandas."""
    x = ahora.isoformat()
    fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, xref=xref, yref=yref,
                  line=dict(color=ROJO, width=1.4, dash="dot"))


def fmt(v, dec, unidad=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dec}f}{(' ' + unidad) if unidad else ''}"


def nombre_modelo(m):
    corto, centro, _ = F.MODELOS[m]
    return f"{corto} ({centro})"


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.markdown("### Ajustes")
    sitio_id = st.selectbox("Sitio", [s["id"] for s in F.SITIOS], format_func=lambda i: F.SITIO[i]["nombre"],
                            help="Los modelos se consultan en las coordenadas del sitio elegido.")
    pasado = st.slider("Días hacia atrás", 1, 7, 3)
    futuro = st.slider("Días de pronóstico", 1, 7, 5)
    modelos = st.multiselect("Modelos", list(F.MODELOS), default=list(F.MODELOS), format_func=nombre_modelo)
    con_ensamble = st.toggle("Banda del super-ensamble (p10–p90)", value=True)
    if st.button("Forzar actualización"):
        st.cache_data.clear()
    st.caption("Los datos se renuevan solos cada hora.")
    st.markdown("[Código en GitHub](https://github.com/Heszo/monitor-meteo-concepcion) · "
                "[github.com/Heszo](https://github.com/Heszo)")

sitio = F.SITIO[sitio_id]
ahora = F.ahora_local()
clave = ahora.strftime("%Y%m%d%H")
horas_obs = pasado * 24 + 2
t0 = pd.Timestamp(ahora).floor("h") - pd.Timedelta(days=pasado)

metar = carga_metar(max(horas_obs, 30), clave)
pron, origen_pron, error_pron = pronostico(sitio, pasado, futuro)
det, pct = pron["det"], pron["pct"]
t_fin = pd.Timestamp(ahora).floor("D") + pd.Timedelta(days=futuro)
avisos = []


def det_var(v):
    return det.get(v, pd.DataFrame())


def observado(s, variable):
    """Serie horaria observada de 'variable' en el sitio s (o None)."""
    if variable not in s["vars"]:
        return None
    if s["fuente"] == "metar":
        col = F.VARIABLES[variable]["metar"]
        return metar[col].dropna() if not metar.empty and col in metar else None
    series, av = carga_vipnet(variable, horas_obs, clave)
    avisos.extend(av)
    return series.get(s["id"])


def recorta(df):
    if df is None or df.empty:
        return df
    return df[(df.index >= t0) & (df.index < t_fin)]


# ------------------------------------------------------------------ encabezado
st.markdown("## Monitor meteorológico · Gran Concepción")
st.markdown("Observado en estaciones y pronóstico de 7 modelos globales y un super-ensamble de 143 miembros")
if error_pron and origen_pron is None:
    st.warning("No se pudo obtener el pronóstico (Open-Meteo no respondió y todavía no hay copia publicada). "
               "Se muestran solo las observaciones; vuelve a intentar en unos minutos.  \n"
               f"Detalle: `{error_pron[:160]}`")
elif error_pron:
    st.info(f"Open-Meteo no respondió; se muestra la {origen_pron}.")
with st.sidebar:
    st.caption(f"Pronóstico: {origen_pron or 'no disponible'}.")

if not metar.empty:
    ult = metar.iloc[-1]
    hace3 = metar.loc[metar.index <= metar.index[-1] - pd.Timedelta(hours=3), "presion"]
    tend = ult.presion - hace3.iloc[-1] if len(hace3) else np.nan
    lluvia, _ = carga_vipnet("precipitacion", max(horas_obs, 30), clave)
    pp24 = lluvia.get("concepcion")
    pp24 = pp24[pp24.index > pp24.index.max() - pd.Timedelta(hours=24)].sum() if pp24 is not None else np.nan
    st.caption(f"Ahora en Carriel Sur · METAR de las {metar.index[-1]:%H:%M} del {metar.index[-1]:%d/%m} "
               f"(hora de Chile) · `{ult.texto}`")
    c = st.container(key="metricas").columns(6)
    c[0].metric("Temperatura", fmt(ult.temperatura, 0, "°C"))
    c[1].metric("Humedad", fmt(ult.humedad, 0, "%"))
    c[2].metric("Viento", fmt(ult.viento, 0, "km/h"), F.cardinal(ult.direccion), delta_color="off")
    c[3].metric("Ráfaga", fmt(ult.rafaga, 0, "km/h") if not np.isnan(ult.rafaga) else "sin ráfagas")
    c[4].metric("Presión", fmt(ult.presion, 0, "hPa"),
                None if np.isnan(tend) else f"{tend:+.0f} hPa en 3 h", delta_color="off")
    c[5].metric("Lluvia 24 h (Concepción DGA)", fmt(pp24, 1, "mm"))

# selector con estado en vez de st.tabs: solo se dibuja (y descarga) la vista elegida, no se pierde al
# interactuar, y los mapas no se inicializan dentro de una pestaña oculta
VISTAS = ["Comparar modelos", "Lluvia", "Meteograma (todas las variables)", "Mapa de estaciones", "Acerca de"]
vista = st.segmented_control("Vista", VISTAS, default=VISTAS[0], key="vista", label_visibility="collapsed")
if vista is None:  # al volver a tocar la opción activa se desmarca: mantener la última
    vista = st.session_state.get("vista_ultima", VISTAS[0])
st.session_state["vista_ultima"] = vista
st.divider()

# ------------------------------------------------------------------ comparar modelos
if vista == VISTAS[0]:
    var = st.segmented_control("Variable", list(F.VARIABLES), default="temperatura",
                               format_func=lambda k: F.VARIABLES[k]["nombre"], key="var_comp") or "temperatura"
    V = F.VARIABLES[var]
    acumular = False
    if var == "precipitacion":
        acumular = st.toggle("Mostrar acumulado desde el inicio de la ventana", value=False)
    histograma = var == "precipitacion" and not acumular

    dv = det_var(var)
    mod_df = recorta(dv[[m for m in modelos if m in dv]])
    obs = recorta(observado(sitio, var))
    banda = None
    if acumular:
        mod_df = mod_df.fillna(0).cumsum()
        obs = obs.cumsum() if obs is not None else None
        if con_ensamble and pron["pp"] is not None:
            banda = F.percentiles(recorta(pron["pp"]).fillna(0).cumsum())
    elif con_ensamble and pct.get(var) is not None:
        banda = recorta(pct[var])
    unidad = "mm" if acumular else V["unidad"]

    # en el histograma de lluvia, el valor de T es lo caído en (T-1h, T]: escalón "vh" y barras
    # centradas media hora antes
    forma = "vh" if histograma else "linear"
    fig = go.Figure()
    if banda is not None:
        x = banda.index
        if histograma:
            fig.add_trace(go.Scatter(x=x, y=banda.p90, line=dict(width=0, shape=forma), showlegend=False,
                                     hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=x, y=banda.p10, line=dict(width=0, shape=forma), fill="tonexty",
                                     fillcolor=BANDA, name="super-ensamble p10–p90", hoverinfo="skip"))
        else:
            fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[banda.p90, banda.p10[::-1]], fill="toself",
                                     fillcolor=BANDA, line=dict(width=0), name="super-ensamble p10–p90",
                                     hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=banda.p50, line=dict(color="#56708f", width=1.5, dash="dash", shape=forma),
                                 name="super-ensamble mediana"))
    if histograma and obs is not None and len(obs):
        fig.add_trace(go.Bar(x=obs.index - pd.Timedelta(minutes=30), y=obs.values, width=3.6e6 * 0.85,
                             marker_color=NEGRO, opacity=0.8, name=f"observado · {sitio['nombre']}"))
    modo = "markers" if var == "direccion" else "lines"
    for m in mod_df.columns:
        fig.add_trace(go.Scatter(x=mod_df.index, y=mod_df[m], mode=modo, name=nombre_modelo(m),
                                 line=dict(color=F.MODELOS[m][2], width=1.6, shape=forma), marker=dict(size=4)))
    if not histograma and obs is not None and len(obs):
        fig.add_trace(go.Scatter(x=obs.index, y=obs.values, mode="lines+markers" if var != "direccion" else "markers",
                                 name=f"observado · {sitio['nombre']}", line=dict(color=NEGRO, width=2.6),
                                 marker=dict(size=5, color=NEGRO)))
    linea_ahora(fig, pd.Timestamp(ahora))
    fig.update_layout(title=f"{V['nombre']}{' acumulada' if acumular else ''} ({unidad}) · {sitio['nombre']}",
                      height=460, hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=-0.18, yanchor="top"))
    if var == "direccion":
        fig.update_yaxes(range=[0, 360], tickvals=[0, 90, 180, 270, 360], ticktext=["N", "E", "S", "O", "N"])
    fig.update_xaxes(**EJE_T)
    st.plotly_chart(fig, config=barra())
    if obs is None:
        disponibles = [F.SITIO[s["id"]]["nombre"] for s in F.SITIOS if var in s["vars"]]
        st.info(f"{sitio['nombre']} no mide {V['nombre'].lower()}. "
                + (f"Sitios que sí: {', '.join(disponibles)}." if disponibles else
                   "Ninguna estación abierta del Gran Concepción la mide."))

    # verificación
    st.markdown(f"**¿Qué modelo anduvo mejor?** Pronóstico contra lo observado en {sitio['nombre']}, "
                f"horas ya ocurridas de la ventana ({pasado} días)")
    if obs is not None and len(obs) and not acumular:
        tabla = F.verificacion(mod_df, obs, var, pd.Timestamp(ahora))
        if banda is not None:
            t_ens = F.verificacion(banda[["p50"]].rename(columns={"p50": "super-ensamble"}), obs, var,
                                   pd.Timestamp(ahora))
            tabla = pd.concat([tabla, t_ens]).sort_values("mae")
        if tabla.empty:
            st.caption("Todavía no hay horas en común entre observado y pronóstico.")
        else:
            tabla["Modelo"] = [nombre_modelo(m) if m in F.MODELOS else "Super-ensamble (mediana)"
                               for m in tabla.modelo]
            col_t, col_g = st.columns([3, 2])
            dec = V["decimales"] + 1
            col_t.dataframe(
                tabla[["Modelo", "n", "sesgo", "mae", "rmse", "r"]].rename(columns={
                    "n": "Horas", "sesgo": f"Sesgo ({V['unidad']})", "mae": f"MAE ({V['unidad']})",
                    "rmse": f"RMSE ({V['unidad']})", "r": "Correlación"}),
                hide_index=True, width="stretch",
                column_config={c: st.column_config.NumberColumn(format=f"%.{dec}f")
                               for c in [f"Sesgo ({V['unidad']})", f"MAE ({V['unidad']})",
                                         f"RMSE ({V['unidad']})"]} |
                {"Correlación": st.column_config.NumberColumn(format="%.2f")})
            fb = go.Figure(go.Bar(
                x=tabla.mae, y=tabla.Modelo, orientation="h",
                marker_color=[F.MODELOS[m][2] if m in F.MODELOS else "#56708f" for m in tabla.modelo],
                text=[f"{v:.{dec}f}" for v in tabla.mae], textposition="outside"))
            fb.update_layout(title=f"Error absoluto medio ({V['unidad']}) · menor es mejor", height=300,
                             margin=dict(l=10, r=30, t=40, b=10), yaxis=dict(autorange="reversed"))
            col_g.plotly_chart(fb, config=barra())
            st.caption("Sesgo > 0: el modelo sobrestima. Los días pasados de Open-Meteo son pronósticos de "
                       "corto plazo de las corridas recientes, no reanálisis. El modelo se compara en el punto "
                       "de grilla más cercano a la estación, así que parte del error es de representatividad.")
    elif acumular:
        st.caption("Desactiva el acumulado para ver las métricas por hora.")
    else:
        st.caption("Sin observación en este sitio para esta variable.")

# ------------------------------------------------------------------ lluvia
ESCALA_LLUVIA = [(25, "#FFF3B0"), (50, "#B8E186"), (75, "#41B6C4"), (100, "#2C7FB8"), (150, "#8856A7"),
                 (np.inf, "#E7298A")]
NIVELES_6H = [(10, "débil", "#9DBFDD"), (25, "moderada", "#6FA3D2"), (np.inf, "fuerte", "#1F4E8C")]
AZUL = "#1F5A96"

if vista == VISTAS[1]:
    lluvia_obs, av = carga_vipnet("precipitacion", horas_obs, clave)
    avisos.extend(av)
    activas = [s for s in F.SITIOS if s["id"] in lluvia_obs]
    ahora_h = pd.Timestamp(ahora).floor("h")
    ini = t0
    obs_ll = {i: o[o.index > ini] for i, o in lluvia_obs.items()}
    tot = {i: float(o.sum()) for i, o in obs_ll.items()}
    P = recorta(pron["pp"])
    P = P[P.index > ini] if P is not None else None
    R = pron["raf6h"]

    st.caption(f"Lluvia observada desde el {DIAS[ini.weekday()]} {ini:%d/%m %H:%M} (inicio de la ventana; "
               f"se cambia con «Días hacia atrás») y pronóstico del super-ensamble en {sitio['nombre']}.")
    c = st.columns(4)
    for col, g in zip(c[:3], F.GRUPOS):
        v = [tot[s["id"]] for s in activas if s["grupo"] == g]
        col.metric(f"Observado* {g} (mm)",
                   "—" if not v else (f"{min(v):.0f}–{max(v):.0f}" if len(v) > 1 else f"{v[0]:.0f}"))
    if P is not None and not P.empty:
        resto = P[P.index > ahora_h].sum().values
        r10, r50, r90 = np.percentile(resto, [10, 50, 90])
        c[3].metric(f"Faltan desde las {ahora_h:%H} h (mm)", f"{r50:.0f}", f"rango {r10:.0f}–{r90:.0f}",
                    delta_color="off", help=f"Lluvia pronosticada de aquí al fin del horizonte ({futuro} días).")

    col_mapa, col_graf = st.columns([5, 7], gap="medium")
    with col_mapa:
        st.markdown("**Acumulado observado\\*** · elige una estación en los botones bajo el mapa")
        mm = [tot[s["id"]] for s in activas]
        fmap = go.Figure(go.Scattermap(
            lat=[s["lat"] for s in activas], lon=[s["lon"] for s in activas], mode="markers+text",
            marker=dict(size=15, color=[next(cc for lim, cc in ESCALA_LLUVIA if v < lim) for v in mm]),
            text=[f"{s['nombre'].split(' (')[0]} {v:.0f}" for s, v in zip(activas, mm)],
            textposition="middle right", textfont=dict(color="white", size=11),
            hovertemplate="%{text} mm<extra></extra>"))
        fmap.update_layout(map=dict(style="white-bg", center=dict(lat=-36.86, lon=-72.95), zoom=8.6,
                                    layers=[dict(sourcetype="raster", source=[F.ESRI], below="traces")]),
                           margin=dict(l=0, r=0, t=0, b=0), height=470, showlegend=False)
        st.plotly_chart(fmap, config=barra("resetViewMap"), key="mapa_lluvia")
        st.caption("Colores: < 25 · 25–50 · 50–75 · 75–100 · 100–150 · > 150 mm. Imagen: Esri World Imagery.")
        opciones = {"Grupos": None} | {s["nombre"].split(" (")[0]: s["id"] for s in activas}
        boton = st.pills("Ver", list(opciones), default="Grupos", key="pick_lluvia", label_visibility="collapsed")
    elegida = opciones.get(boton) if boton else None
    if elegida:
        curvas = [(F.SITIO[elegida]["nombre"], [elegida], F.GRUPOS[F.SITIO[elegida]["grupo"]])]
    else:
        curvas = [(f"{g} ({sum(s['grupo'] == g for s in activas)} est.)",
                   [s["id"] for s in activas if s["grupo"] == g], colg)
                  for g, colg in F.GRUPOS.items() if any(s["grupo"] == g for s in activas)]

    with col_graf:
        if P is None or P.empty:
            st.warning("El super-ensamble no respondió; prueba «Forzar actualización».")
        else:
            q = F.percentiles(P)
            fa = go.Figure()
            fa.add_trace(go.Scatter(x=q.index, y=q.p90, line=dict(width=0, shape="vh"), showlegend=False,
                                    hoverinfo="skip"))
            fa.add_trace(go.Scatter(x=q.index, y=q.p10, line=dict(width=0, shape="vh"), fill="tonexty",
                                    fillcolor="rgba(157,191,221,.55)", name="pronóstico p10–p90", hoverinfo="skip"))
            fa.add_trace(go.Bar(x=q.index - pd.Timedelta(minutes=30), y=q.p50, width=3.6e6 * 0.85,
                                marker_color=AZUL, opacity=.85, name="pronóstico mediana"))
            for nombre, ids, colg in curvas:
                tab = pd.concat([obs_ll[i] for i in ids], axis=1)
                fa.add_trace(go.Scatter(x=tab.index - pd.Timedelta(minutes=30), y=tab.mean(axis=1), mode="lines",
                                        line=dict(color=colg, width=2.4), name=f"observado* {nombre}"))
            linea_ahora(fa, ahora_h)
            fa.update_layout(title="Precipitación por hora (mm)", height=360, margin=dict(l=10, r=10, t=40, b=10),
                             bargap=0, legend=dict(orientation="h", y=-.3, yanchor="top"), hovermode="x unified")
            fa.update_xaxes(**EJE_T)
            st.plotly_chart(fa, config=barra(), key="hist_lluvia")

            A = F.percentiles(P.fillna(0).cumsum())
            fb = go.Figure()
            fb.add_trace(go.Scatter(x=np.r_[A.index, A.index[::-1]], y=np.r_[A.p90, A.p10[::-1]], fill="toself",
                                    fillcolor="rgba(157,191,221,.55)", line=dict(width=0),
                                    name="pronóstico p10–p90", hoverinfo="skip"))
            fb.add_trace(go.Scatter(x=A.index, y=A.p50, line=dict(color=AZUL, width=3), name="pronóstico mediana"))
            for nombre, ids, colg in curvas:
                for i in ids:
                    o = obs_ll[i]
                    fb.add_trace(go.Scatter(x=[ini, *o.index], y=[0, *o.cumsum()], line=dict(color=colg, width=1.6),
                                            name=F.SITIO[i]["nombre"], showlegend=False))
            linea_ahora(fb, ahora_h)
            fb.update_layout(title=dict(text="Acumulado desde el inicio (mm)",
                                        subtitle=dict(text=f"pronóstico total {A.p50.iloc[-1]:.0f} mm "
                                                           f"({A.p10.iloc[-1]:.0f}–{A.p90.iloc[-1]:.0f})")),
                             height=290, margin=dict(l=10, r=10, t=60, b=10), showlegend=False,
                             hovermode="x unified")
            fb.update_xaxes(**EJE_T)
            st.plotly_chart(fb, config=barra(), key="acum_lluvia")

    if P is not None and not P.empty:
        st.markdown("**Lluvia esperada cada 6 horas** (mediana del pronóstico; rango p10–p90)")
        html = ['<div style="display:flex;flex-wrap:wrap;gap:8px">']
        b0 = max(ini, ahora_h - pd.Timedelta(hours=24)).floor("6h")  # 24 h de pasado + todo el pronóstico
        fin = P.index.max()
        while b0 < fin:
            b1 = b0 + pd.Timedelta(hours=6)
            m = (P.index > b0) & (P.index <= b1)
            q10, q50, q90 = np.percentile(P[m].sum().values, [10, 50, 90])
            rf = None
            if R is not None and b0 in R.index:
                rf = float(R.loc[b0])
            pasado_b, actual = b1 <= ahora_h, b0 <= ahora_h < b1
            color = next(cc for lim, _, cc in NIVELES_6H if q50 < lim)
            obs_txt = ""
            if pasado_b:
                partes = []
                for g, colg in F.GRUPOS.items():
                    v = [float(lluvia_obs[s["id"]][(lluvia_obs[s["id"]].index > b0) &
                                                   (lluvia_obs[s["id"]].index <= b1)].sum())
                         for s in activas if s["grupo"] == g]
                    if v:
                        partes.append(f'<span style="color:{colg}">{g} {min(v):.0f}'
                                      f'{"–%.0f" % max(v) if round(min(v)) != round(max(v)) else ""}</span>')
                obs_txt = "<br>".join(partes)
            fin_h = "24" if b1.hour == 0 else f"{b1:%H}"
            html.append(
                f'<div style="flex:1 1 92px;max-width:130px;border:{"2px solid " + ROJO if actual else "1px solid #D6D2CA"};'
                f'border-radius:10px;padding:8px 6px;text-align:center;opacity:{.55 if pasado_b else 1};'
                f'font-family:sans-serif">'
                f'<div style="font-weight:700">{DIAS[b0.weekday()].capitalize()} {b0.day}</div>'
                f'<div style="font-size:12px;color:#666">{b0:%H}–{fin_h} h</div>'
                f'<div style="font-size:26px;font-weight:800;color:{color}">{q50:.0f}</div>'
                f'<div style="font-size:11px;color:#666">mm · {q10:.0f}–{q90:.0f}</div>'
                f'<div style="font-size:11px;margin-top:4px;font-weight:700">{obs_txt}</div>'
                + (f'<div style="font-size:11px;color:#5B4B8A">ráfaga {rf:.0f} km/h</div>'
                   if rf is not None and not np.isnan(rf) and not pasado_b else "")
                + (f"<div style='font-size:10px;color:white;background:{ROJO};border-radius:4px;margin-top:4px'>"
                   "AHORA</div>" if actual else "")
                + "</div>")
            b0 = b1
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)
        st.caption("Ráfaga: mediana del máximo del bloque entre los miembros que la informan (GEFS e IFS-ENS). "
                   "Intensidad descriptiva (débil < 10, moderada 10–25, fuerte > 25 mm en 6 h): no reemplaza los "
                   "avisos de SENAPRED y la DMC. * Observado: VIPNet (DGA/MOP), datos preliminares.")

# ------------------------------------------------------------------ meteograma
if vista == VISTAS[2]:
    fuente_mod = st.selectbox("Pronóstico a mostrar", ["mediana"] + modelos,
                              format_func=lambda m: "Mediana de los modelos elegidos" if m == "mediana"
                              else nombre_modelo(m), key="fuente_meteo")
    filas = ["temperatura", "humedad", "viento", "direccion", "presion", "precipitacion"]
    titulos = {"temperatura": "Temperatura (°C)", "humedad": "Humedad relativa (%)",
               "viento": "Viento y ráfaga (km/h)", "direccion": "Dirección del viento",
               "presion": "Presión al nivel del mar (hPa)", "precipitacion": "Precipitación (mm/h)"}
    fm = make_subplots(rows=len(filas), cols=1, shared_xaxes=True, vertical_spacing=0.045,
                       subplot_titles=[titulos[f] for f in filas])
    fm.update_annotations(x=0, xanchor="left", font=dict(size=13, color="#333"))
    color_mod = "#1F5A96" if fuente_mod == "mediana" else F.MODELOS[fuente_mod][2]
    etiqueta_mod = "mediana de modelos" if fuente_mod == "mediana" else F.MODELOS[fuente_mod][0]

    def serie_mod(v):
        dv = det_var(v)
        df = recorta(dv[[m for m in modelos if m in dv]])
        if df is None or df.empty:
            return None
        if fuente_mod != "mediana":
            return df[fuente_mod] if fuente_mod in df else None
        if v == "direccion":  # mediana circular aproximada: por componentes
            rad = np.deg2rad(df)
            return (np.rad2deg(np.arctan2(np.sin(rad).mean(axis=1), np.cos(rad).mean(axis=1))) % 360)
        return df.median(axis=1)

    ya = set()
    for fila, v in enumerate(filas, start=1):
        leyenda = lambda nombre: nombre not in ya and not ya.add(nombre)  # noqa: E731
        if con_ensamble and pct.get(v) is not None:
            b = recorta(pct[v])
            if b is not None:
                fm.add_trace(go.Scatter(x=np.r_[b.index, b.index[::-1]], y=np.r_[b.p90, b.p10[::-1]],
                                        fill="toself", fillcolor=BANDA, line=dict(width=0), hoverinfo="skip",
                                        name="super-ensamble p10–p90", legendgroup="ens",
                                        showlegend=leyenda("ens")), row=fila, col=1)
        s = serie_mod(v)
        if s is not None:
            if v == "precipitacion":
                fm.add_trace(go.Bar(x=s.index, y=s.values, marker_color=color_mod, opacity=.8, name=etiqueta_mod,
                                    legendgroup="mod", showlegend=leyenda("mod")), row=fila, col=1)
            else:
                fm.add_trace(go.Scatter(x=s.index, y=s.values, mode="markers" if v == "direccion" else "lines",
                                        line=dict(color=color_mod, width=2), marker=dict(size=4, color=color_mod),
                                        name=etiqueta_mod, legendgroup="mod", showlegend=leyenda("mod")),
                             row=fila, col=1)
        if v == "viento":
            r = serie_mod("rafaga")
            if r is not None:
                fm.add_trace(go.Scatter(x=r.index, y=r.values, line=dict(color=color_mod, width=1.2, dash="dot"),
                                        name=f"ráfaga ({etiqueta_mod})", legendgroup="raf",
                                        showlegend=leyenda("raf")), row=fila, col=1)
        o = recorta(observado(sitio, v))
        if o is not None and len(o):
            fm.add_trace(go.Scatter(x=o.index, y=o.values, mode="markers" if v == "direccion" else "lines",
                                    line=dict(color=NEGRO, width=2.2), marker=dict(size=4, color=NEGRO),
                                    name=f"observado · {sitio['nombre']}", legendgroup="obs",
                                    showlegend=leyenda("obs")), row=fila, col=1)
        if v == "viento":
            o = recorta(observado(sitio, "rafaga"))
            if o is not None and len(o):
                fm.add_trace(go.Scatter(x=o.index, y=o.values, mode="markers", marker=dict(color=NEGRO, size=7,
                                        symbol="triangle-up"), name="ráfaga observada", legendgroup="rafo",
                                        showlegend=leyenda("rafo")), row=fila, col=1)
        linea_ahora(fm, pd.Timestamp(ahora), xref=f"x{fila if fila > 1 else ''}",
                    yref=f"y{fila if fila > 1 else ''} domain")
    fm.update_yaxes(range=[0, 360], tickvals=[0, 90, 180, 270, 360], ticktext=["N", "E", "S", "O", "N"],
                    row=filas.index("direccion") + 1, col=1)
    fm.update_layout(height=1300, hovermode="x unified", margin=dict(l=10, r=10, t=70, b=10), bargap=0.1,
                     legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0, xanchor="left"))
    fm.update_layout(legend_y=1.035)
    fm.update_xaxes(**EJE_T, showgrid=True)
    fm.update_xaxes(showticklabels=True, row=len(filas), col=1)
    st.plotly_chart(fm, config=barra())
    faltan = [F.VARIABLES[v]["nombre"].lower() for v in filas if v not in sitio["vars"]]
    if faltan:
        st.caption(f"{sitio['nombre']} no mide: {', '.join(faltan)} (solo pronóstico en esos paneles).")

# ------------------------------------------------------------------ mapa
if vista == VISTAS[3]:
    medibles = ["temperatura", "humedad", "precipitacion", "viento", "rafaga", "presion"]
    var_m = st.segmented_control("Variable", medibles, default="temperatura",
                                 format_func=lambda k: F.VARIABLES[k]["nombre"], key="var_mapa") or "temperatura"
    ventana_pp = 24
    if var_m == "precipitacion":
        ventana_pp = st.slider("Lluvia acumulada en las últimas … horas", 1, pasado * 24, min(24, pasado * 24))
    filas_m = []
    for s in F.SITIOS:
        o = observado(s, var_m)
        if o is None or not len(o):
            continue
        if var_m == "precipitacion":
            valor, hora = o[o.index > o.index.max() - pd.Timedelta(hours=ventana_pp)].sum(), o.index.max()
        else:
            o = o.dropna()
            if not len(o):
                continue
            valor, hora = float(o.iloc[-1]), o.index[-1]
        filas_m.append(dict(Estación=s["nombre"].split(" (")[0], Grupo=s["grupo"], lat=s["lat"], lon=s["lon"], valor=valor,
                            Hora=hora, Fuente="METAR" if s["fuente"] == "metar" else "VIPNet"))
    Vm = F.VARIABLES[var_m]
    unidad_m = "mm" if var_m == "precipitacion" else Vm["unidad"]
    if not filas_m:
        st.info("Ninguna estación informó esta variable en la ventana.")
    else:
        dm = pd.DataFrame(filas_m)
        escala = {"temperatura": "RdYlBu_r", "humedad": "YlGnBu", "precipitacion": "Blues",
                  "viento": "Viridis", "rafaga": "Viridis", "presion": "Plasma"}[var_m]
        fmap = go.Figure(go.Scattermap(
            lat=dm.lat, lon=dm.lon, mode="markers+text",
            marker=dict(size=17, color=dm.valor, colorscale=escala, showscale=True,
                        colorbar=dict(title=unidad_m, thickness=12)),
            text=[f"{e} {fmt(v, Vm['decimales'])}" for e, v in zip(dm["Estación"], dm.valor)],
            textposition="middle right", textfont=dict(color="white", size=12),
            hovertemplate="%{text} " + unidad_m + "<extra></extra>"))
        fmap.update_layout(map=dict(style="white-bg", center=dict(lat=-36.86, lon=-72.95), zoom=8.7,
                                    layers=[dict(sourcetype="raster", source=[F.ESRI], below="traces")]),
                           margin=dict(l=0, r=0, t=0, b=0), height=560)
        col_map, col_tab = st.columns([3, 2])
        col_map.plotly_chart(fmap, config=barra("resetViewMap"))
        col_tab.dataframe(dm[["Estación", "Grupo", "valor", "Hora", "Fuente"]]
                          .rename(columns={"valor": f"{Vm['nombre']} ({unidad_m})"}).sort_values("Grupo"),
                          hide_index=True, width="stretch",
                          column_config={"Hora": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
                                         f"{Vm['nombre']} ({unidad_m})": st.column_config.NumberColumn(
                                             format=f"%.{Vm['decimales']}f")})
        titulo = (f"acumulado de las últimas {ventana_pp} h" if var_m == "precipitacion" else "última medición")
        col_tab.caption(f"{Vm['nombre']}: {titulo}. Imagen: Esri World Imagery.")

# ------------------------------------------------------------------ acerca de
if vista == VISTAS[4]:
    st.markdown(f"""
**Qué muestra.** Observaciones del Gran Concepción comparadas con el pronóstico de 7 modelos
deterministas globales y la dispersión de un super-ensamble de 143 miembros. Los modelos se consultan
en las coordenadas del sitio elegido, en la hora local de Chile.

**Fuentes (todas públicas y sin clave):**

| Fuente | Qué aporta | Frecuencia |
|---|---|---|
| [VIPNet](https://vipnet.mop.gob.cl) (DGA/MOP) | lluvia (16 estaciones), temperatura y humedad (9) | 30 min |
| [METAR SCIE](https://aviationweather.gov) (Carriel Sur, vía NOAA Aviation Weather Center) | temperatura, humedad (desde el punto de rocío), viento, ráfaga, dirección, presión QNH | 1 h |
| [Open-Meteo Forecast](https://open-meteo.com) | GFS (NOAA), IFS (ECMWF), ICON (DWD), GEM (Canadá), GSM (JMA), UM (UK Met Office), ARPEGE (Météo-France) | 1 h |
| [Open-Meteo Ensemble](https://open-meteo.com/en/docs/ensemble-api) | GEFS (31) + IFS-ENS (51) + ICON-EPS (40) + GEPS (21) = 143 miembros | 1 h |
| Esri World Imagery | imagen satelital del mapa | — |

**Cuidado al interpretar.**
- Datos observados preliminares, sin control de calidad.
- Los METAR informan ráfaga solo cuando es significativa; sin ráfaga informada no hay dato.
- La presión del METAR es QNH, equivalente en la práctica a la presión al nivel del mar de los modelos.
- Intensidades y valores son descriptivos: no reemplazan los avisos oficiales de SENAPRED y la DMC.
- Open-Meteo es gratuito para uso no comercial.

Hecho por Bruno Herrera · METGEO ([github.com/Heszo](https://github.com/Heszo)). Código abierto (MIT) en
[github.com/Heszo/monitor-meteo-concepcion](https://github.com/Heszo/monitor-meteo-concepcion).
Consultado el {ahora:%d/%m/%Y %H:%M} (hora de Chile); pronóstico: {origen_pron or "no disponible"}.

**Cómo se actualiza el pronóstico.** Open-Meteo gratuito limita las consultas por dirección IP, y la de
Streamlit Community Cloud es compartida con muchas otras apps. Por eso una GitHub Action baja los
pronósticos de todos los sitios cada hora y los publica en la rama `datos` del repositorio; la app lee esa
copia y solo consulta Open-Meteo en vivo si la copia falta o tiene más de 3 horas.
""")
    for v in ("precipitacion", "temperatura", "humedad"):
        avisos.extend(carga_vipnet(v, horas_obs, clave)[1])
    if metar.empty:
        avisos.append("METAR SCIE: sin datos")
    if avisos:
        with st.expander("Avisos de descarga"):
            st.write("\n".join(f"- {a}" for a in sorted(set(avisos))))
