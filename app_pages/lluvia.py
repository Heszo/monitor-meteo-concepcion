"""Lluvia: mapa del acumulado observado, histograma horario, acumulado y tarjetas de 6 h."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import comun as C
import fuentes as F
from comun import BANDA, DIAS, EJE_T, NEGRO, ROJO, barra, fmt, linea_ahora, nombre_modelo

PAL = C.paleta()
c = C.contexto()
sitio, pasado, futuro, modelos, con_ensamble = c.sitio, c.pasado, c.futuro, c.modelos, c.con_ensamble
ahora, t0, t_fin, metar, pron, det, pct, avisos = c.ahora, c.t0, c.t_fin, c.metar, c.pron, c.det, c.pct, c.avisos
origen_pron = c.origen_pron
observado, recorta, det_var = c.observado, c.recorta, c.det_var

ESCALA_LLUVIA = [(25, "#FFF3B0"), (50, "#B8E186"), (75, "#41B6C4"), (100, "#2C7FB8"), (150, "#8856A7"),
                 (np.inf, "#E7298A")]
NIVELES_6H = list(zip((10, 25, np.inf), ("débil", "moderada", "fuerte"), PAL.niveles))
AZUL = PAL.azul

lluvia_obs, av = C.vipnet_seguro("precipitacion")
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

# La estación elegida aquí es el «Sitio» de toda la app: al cambiarla cambian también el pronóstico y las
# tarjetas de arriba. Se elige pinchando el mapa o en «Estación», que las agrupa en costa, ciudad e interior.
# Carriel Sur no mide lluvia: con ella elegida no se destaca ninguna estación, solo los promedios por grupo.
elegida = sitio["id"] if sitio["id"] in lluvia_obs else None
NOMBRE_GRUPO = {"costa": "Costa", "ciudad": "Ciudad", "interior": "Interior"}


def al_pinchar():
    """Callback del mapa: el punto pinchado pasa a ser el sitio (corre antes del script, así los controles
    de arriba ya lo ven)."""
    puntos = st.session_state["mapa_lluvia"].selection.points
    if puntos:
        i = puntos[0].get("customdata")
        i = i[0] if isinstance(i, list) else i
        if i in F.SITIO:
            st.session_state["sitio"] = i


def al_elegir(g):
    if st.session_state[f"lluvia_{g}"]:
        st.session_state["sitio"] = st.session_state[f"lluvia_{g}"]


col_mapa, col_graf = st.columns([5, 7], gap="medium")
with col_mapa:
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown("**Acumulado observado\\*** · pincha una estación para elegirla")
        with st.popover(F.SITIO[elegida]["nombre"] if elegida else "Estación", icon=":material/location_on:"):
            for g, colg in PAL.grupos.items():
                ids = [s["id"] for s in activas if s["grupo"] == g]
                if not ids:
                    continue
                st.markdown(f'<span style="color:{colg}">●</span> **{NOMBRE_GRUPO[g]}**', unsafe_allow_html=True)
                st.session_state[f"lluvia_{g}"] = elegida if elegida in ids else None
                st.pills(NOMBRE_GRUPO[g], ids, format_func=lambda i: F.SITIO[i]["nombre"], key=f"lluvia_{g}",
                         on_change=al_elegir, args=(g,), label_visibility="collapsed")
    mm = [tot[s["id"]] for s in activas]
    ids = [s["id"] for s in activas]
    lat, lon = [s["lat"] for s in activas], [s["lon"] for s in activas]
    fmap = go.Figure()
    if elegida:  # halo de la estación elegida
        fmap.add_trace(go.Scattermap(lat=[F.SITIO[elegida]["lat"]], lon=[F.SITIO[elegida]["lon"]], mode="markers",
                                     marker=dict(size=20, color="white"), customdata=[elegida],
                                     hoverinfo="none"))
    # anillo del color del grupo bajo el punto del color del acumulado
    fmap.add_trace(go.Scattermap(lat=lat, lon=lon, mode="markers", customdata=ids, hoverinfo="none",
                                 marker=dict(size=14, color=[PAL.grupos[s["grupo"]] for s in activas])))
    fmap.add_trace(go.Scattermap(
        lat=lat, lon=lon, mode="markers+text", customdata=ids,
        marker=dict(size=8, color=[next(cc for lim, cc in ESCALA_LLUVIA if v < lim) for v in mm]),
        text=[f"{s['nombre'].split(' (')[0]} {v:.0f}" for s, v in zip(activas, mm)],
        textposition="middle right", textfont=dict(color="white", size=10),
        hovertext=[f"{s['nombre']} · {NOMBRE_GRUPO[s['grupo']].lower()}<br>{v:.0f} mm" for s, v in zip(activas, mm)],
        hovertemplate="%{hovertext}<extra></extra>"))
    C.mapa_satelital(fmap, F.SITIOS, ancho=430, alto=470, der=110)  # 'der': etiquetas a la derecha de cada punto
    # al pinchar, Plotly atenúa los puntos no seleccionados y les borra la etiqueta: aquí todos se ven igual
    fmap.update_traces(unselected=dict(marker=dict(opacity=1)),
                       selected=dict(marker=dict(opacity=1)))
    fmap.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False, clickmode="event+select")
    fmap.add_annotation(  # leyenda chica de los grupos, abajo a la izquierda
        text="  ".join(f'<span style="color:{colg}">●</span> {NOMBRE_GRUPO[g]}' for g, colg in PAL.grupos.items()),
        xref="paper", yref="paper", x=.01, y=.01, xanchor="left", yanchor="bottom", showarrow=False,
        font=dict(color="white", size=11), bgcolor="rgba(0,0,0,.5)", borderpad=4)
    C.grafico(fmap, "mapa_lluvia", config=barra("resetViewMap"), key="mapa_lluvia", on_select=al_pinchar,
              selection_mode="points")
    st.caption("Número: mm acumulados. Imagen: Esri World Imagery.")
    if not elegida:
        st.caption(f":material/info: {sitio['nombre']} no mide lluvia: se muestran los promedios por grupo.")

# promedios por grupo (siempre) y, encima, la estación elegida
curvas = [(f"{NOMBRE_GRUPO[g].lower()} (promedio {sum(s['grupo'] == g for s in activas)} est.)",
           [s["id"] for s in activas if s["grupo"] == g], colg)
          for g, colg in PAL.grupos.items() if any(s["grupo"] == g for s in activas)]

def ensamble_grupos():
    """({grupo: miembros horarios}, hora de la copia): el super-ensamble de cada grupo, promedio miembro a miembro de la lluvia
    pronosticada en sus estaciones. Sale de la copia publicada (trae todas las estaciones); sin ella, {}."""
    try:
        generado, pub = C.carga_publicados()
    except Exception:  # noqa: BLE001
        return {}, None
    out = {}
    for g in PAL.grupos:
        pps = [pub[s["id"]]["pp"] for s in activas
               if s["grupo"] == g and s["id"] in pub and pub[s["id"]]["pp"] is not None]
        if pps:
            m = recorta(sum(pps) / len(pps))
            out[g] = m[m.index > ini]
    return out, generado.tz_convert(F.ZONA)


def tenue(hexa, a):
    """'#RRGGBB' -> 'rgba(r,g,b,a)' para las bandas de los grupos."""
    return f"rgba({int(hexa[1:3], 16)},{int(hexa[3:5], 16)},{int(hexa[5:7], 16)},{a})"


with col_graf:
    vista = st.segmented_control("Ver", ["Estación", "Por grupo"], default="Estación", required=True,
                                 key="lluvia_vista", label_visibility="collapsed", disabled=not elegida,
                                 help="«Por grupo»: promedio de las estaciones de la costa, la ciudad y el interior.")
    destacada = elegida if vista == "Estación" else None  # None: se destacan los promedios por grupo
    PG, PG_HORA = ({}, None) if destacada else ensamble_grupos()
    if P is None or P.empty:
        st.warning("El super-ensamble no respondió; los datos se renuevan solos cada hora.")
    else:
        q = F.percentiles(P)
        fa = go.Figure()
        fa.add_trace(go.Scatter(x=q.index, y=q.p90, line=dict(width=0, shape="vh"), showlegend=False,
                                hoverinfo="skip"))
        fa.add_trace(go.Scatter(x=q.index, y=q.p10, line=dict(width=0, shape="vh"), fill="tonexty",
                                fillcolor="rgba(157,191,221,.55)", name="pronóstico p10–p90", hoverinfo="skip"))
        fa.add_trace(go.Bar(x=q.index - pd.Timedelta(minutes=30), y=q.p50, width=3.6e6 * 0.85,
                            marker_color=AZUL, opacity=.85, name=f"pronóstico {sitio['nombre']} (mediana)"))
        for g, m in PG.items():
            qg = F.percentiles(m)
            fa.add_trace(go.Scatter(x=qg.index - pd.Timedelta(minutes=30), y=qg.p50, mode="lines",
                                    line=dict(color=PAL.grupos[g], width=1.6, dash="dash"),
                                    name=f"pronóstico {NOMBRE_GRUPO[g].lower()} (mediana)"))
        for nombre, ids, colg in curvas:
            tab = pd.concat([obs_ll[i] for i in ids], axis=1, sort=True)
            fa.add_trace(go.Scatter(x=tab.index - pd.Timedelta(minutes=30), y=tab.mean(axis=1), mode="lines",
                                    line=dict(color=colg, width=1.4 if destacada else 2.4,
                                              dash="dot" if destacada else "solid"),
                                    opacity=.8 if destacada else 1, name=f"observado* {nombre}"))
        if destacada:
            o = obs_ll[destacada]
            fa.add_trace(go.Scatter(x=o.index - pd.Timedelta(minutes=30), y=o, mode="lines",
                                    line=dict(color=PAL.grupos[F.SITIO[destacada]["grupo"]], width=3.2),
                                    name=f"observado* {F.SITIO[destacada]['nombre']}"))
        linea_ahora(fa, ahora_h)
        fa.update_layout(title="Precipitación por hora (mm)", height=360, margin=dict(l=10, r=10, t=40, b=10),
                         bargap=0, legend=dict(orientation="h", y=-.3, yanchor="top"), hovermode="x unified")
        fa.update_xaxes(**EJE_T)
        C.grafico(fa, f"lluvia_por_hora_{sitio['id']}", key="hist_lluvia")

        A = F.percentiles(P.fillna(0).cumsum())
        fb = go.Figure()
        fb.add_trace(go.Scatter(x=np.r_[A.index, A.index[::-1]], y=np.r_[A.p90, A.p10[::-1]], fill="toself",
                                fillcolor="rgba(157,191,221,.55)", line=dict(width=0),
                                name="pronóstico p10–p90", hoverinfo="skip"))
        fb.add_trace(go.Scatter(x=A.index, y=A.p50, line=dict(color=AZUL, width=3),
                                name=f"pronóstico {sitio['nombre']} (mediana)"))
        totales = [f"{sitio['nombre']} {A.p50.iloc[-1]:.0f} mm ({A.p10.iloc[-1]:.0f}–{A.p90.iloc[-1]:.0f})"]
        for g, m in PG.items():  # ensamble de cada grupo: banda tenue y mediana a trazos
            Ag = F.percentiles(m.fillna(0).cumsum())
            colg = PAL.grupos[g]
            fb.add_trace(go.Scatter(x=np.r_[Ag.index, Ag.index[::-1]], y=np.r_[Ag.p90, Ag.p10[::-1]],
                                    fill="toself", fillcolor=tenue(colg, .13), line=dict(width=0),
                                    legendgroup=g, showlegend=False, hoverinfo="skip"))
            fb.add_trace(go.Scatter(x=Ag.index, y=Ag.p50, line=dict(color=colg, width=2, dash="dash"),
                                    legendgroup=g, name=f"pronóstico {NOMBRE_GRUPO[g].lower()} (mediana, p10–p90)"))
            totales.append(f"{NOMBRE_GRUPO[g].lower()} {Ag.p50.iloc[-1]:.0f} "
                           f"({Ag.p10.iloc[-1]:.0f}–{Ag.p90.iloc[-1]:.0f})")
        for nombre, ids, colg in curvas:
            for i in ids:
                o = obs_ll[i]
                fb.add_trace(go.Scatter(x=[ini, *o.index], y=[0, *o.cumsum()], name=F.SITIO[i]["nombre"],
                                        line=dict(color=colg, width=3.2 if i == destacada else 1.2),
                                        opacity=1 if i == destacada else .3, showlegend=False))
            if not destacada:  # acumulado promedio del grupo
                m = pd.concat([obs_ll[i] for i in ids], axis=1, sort=True).mean(axis=1).fillna(0).cumsum()
                fb.add_trace(go.Scatter(x=[ini, *m.index], y=[0, *m], line=dict(color=colg, width=3.2),
                                        name=f"observado* {nombre}"))
        # la estación destacada encima de las demás
        fb.data = sorted(fb.data, key=lambda t: t.name == F.SITIO.get(destacada, {}).get("nombre"))
        linea_ahora(fb, ahora_h)
        fb.update_layout(title=dict(text="Acumulado desde el inicio (mm)",
                                    subtitle=dict(text="pronóstico total: " + " · ".join(totales))),
                         height=380 if not destacada else 290, margin=dict(l=10, r=10, t=60, b=10),
                         showlegend=not destacada, legend=dict(orientation="h", y=-.3, yanchor="top"),
                         hovermode="x unified")
        fb.update_xaxes(**EJE_T)
        C.grafico(fb, f"lluvia_acumulada_{sitio['id']}", key="acum_lluvia")
        if PG:
            st.caption(f"Ensamble por grupo: promedio, miembro a miembro, del super-ensamble en las estaciones de "
                       f"cada grupo (copia publicada a las {PG_HORA:%d/%m %H:%M}). El de {sitio['nombre']}: "
                       f"{origen_pron or 'no disponible'}.")

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
            for g, colg in PAL.grupos.items():
                v = [float(lluvia_obs[s["id"]][(lluvia_obs[s["id"]].index > b0) &
                                               (lluvia_obs[s["id"]].index <= b1)].sum())
                     for s in activas if s["grupo"] == g]
                if v:
                    partes.append(f'<span style="color:{colg}">{g} {min(v):.0f}'
                                  f'{"–%.0f" % max(v) if round(min(v)) != round(max(v)) else ""}</span>')
            obs_txt = "<br>".join(partes)
        fin_h = "24" if b1.hour == 0 else f"{b1:%H}"
        html.append(
            f'<div style="flex:1 1 92px;max-width:130px;border:{"2px solid " + ROJO if actual else "1px solid rgba(128,128,128,.35)"};'
            f'border-radius:10px;padding:8px 6px;text-align:center;opacity:{.55 if pasado_b else 1};'
            f'font-family:sans-serif">'
            f'<div style="font-weight:700">{DIAS[b0.weekday()].capitalize()} {b0.day}</div>'
            f'<div style="font-size:12px;opacity:.7">{b0:%H}–{fin_h} h</div>'
            f'<div style="font-size:26px;font-weight:800;color:{color}">{q50:.0f}</div>'
            f'<div style="font-size:11px;opacity:.7">mm · {q10:.0f}–{q90:.0f}</div>'
            f'<div style="font-size:11px;margin-top:4px;font-weight:700">{obs_txt}</div>'
            + (f'<div style="font-size:11px;color:{PAL.rafaga}">ráfaga {rf:.0f} km/h</div>'
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
