"""
Lo que comparten todas las páginas: cargas con caché, el contexto de la
corrida (sitio, ventana, datos) y utilidades de gráficos.

Las cargas usan ttl + refresh_mode="background": cuando una entrada vence,
el visitante recibe al instante la versión anterior y la nueva se baja por
detrás. Además app.py (st.App) las toca cada pocos minutos desde el
servidor, así que casi nadie espera una descarga. Para que eso funcione las
claves de caché son fijas: se pide siempre la ventana máxima y se recorta
después.
"""
import base64
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import fuentes as F

RAIZ = Path(__file__).resolve().parent
VERSION = (RAIZ / "VERSION").read_text().strip()
LOGO_SOLO = RAIZ / "static" / "logo_solo.png"  # ícono de la pestaña (page_icon no acepta SVG)
NEGRO, ROJO, BANDA = "#111111", "#B5323C", "rgba(120,150,190,.22)"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
EJE_T = dict(tickformat="%d/%m<br>%H:%M", nticks=8, tickangle=0)
HORAS_OBS = F.DIAS_PUBLICADOS * 24 + 2
VARS_VIPNET = ("precipitacion", "temperatura", "humedad")
VACIO = {"det": {}, "pct": {}, "pp": None, "raf6h": None}
VIEJO = pd.Timedelta(hours=3)
INSTAGRAM = "https://www.instagram.com/metgeo.spa/"
LINKEDIN = "https://www.linkedin.com/company/metgeo-spa/"
REPO = "https://github.com/Heszo/monitor-meteo-concepcion"
METGEO = "https://metgeo.cl"
NEWSLETTER = "https://metgeo-newsletter.metgeo.workers.dev/"


# ------------------------------------------------------------------ modo claro / oscuro
# config.toml define [theme.light] y [theme.dark] sin fijar `base`, así que Streamlit sigue el modo del
# navegador. Lo que se dibuja desde Python (logos, colores de los gráficos, tarjetas HTML) lo elige aquí.
# Los logos "claro" son los de trazo claro, para fondo oscuro.
CLARO = SimpleNamespace(
    oscuro=False, logo=RAIZ / "static" / "logo_completo.svg", icono=RAIZ / "static" / "logo_solo.svg",
    tinta=NEGRO, azul="#1F5A96", ens="#56708f", lluvia_esp="#6FA3D2", lluvia_obs="#1F4E8C", rafaga="#5B4B8A",
    niveles=("#9DBFDD", "#6FA3D2", "#1F4E8C"), grupos=F.GRUPOS,
    plantilla="plotly_white", fondo="#FFFFFF")
OSCURO = SimpleNamespace(
    oscuro=True, logo=RAIZ / "static" / "logo_completo_claro.svg", icono=RAIZ / "static" / "logo_solo_claro.svg",
    tinta="#F2F2F2", azul="#6FA8DC", ens="#9DB3CC", lluvia_esp="#4E94C3", lluvia_obs="#BFE0F7", rafaga="#B9A6E8",
    niveles=("#5A7FA3", "#6FA8DC", "#A8D4F5"), grupos={"costa": "#3CC6C9", "ciudad": "#F28C3E", "interior": "#B08AE0"},
    plantilla="plotly_dark", fondo="#0E1117")


def paleta():
    """Colores y logos del modo en que el navegador muestra la app (claro si no se sabe)."""
    return OSCURO if st.context.theme.type == "dark" else CLARO


# Que el navegador cambie de modo con la app abierta no vuelve a correr el script, así que los gráficos quedaban con los
# colores del modo anterior. Este componente invisible mira el fondo de la app y, si no coincide con el modo con
# que se dibujó, pide un rerun; el navegador manda el modo nuevo con ese rerun y st.context.theme se actualiza.
_VIGIA_JS = """
export default function ({ data, setTriggerValue }) {
    const modo = () => {
        const app = document.querySelector('.stApp') || document.body;
        const m = getComputedStyle(app).backgroundColor.match(/\\d+(\\.\\d+)?/g);
        if (!m) return null;
        const [r, g, b] = m.map(Number);
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5 ? 'dark' : 'light';
    };
    let pedido = null;  // un solo rerun por cambio, para no entrar en bucle si el servidor no se entera
    const revisa = () => {
        const actual = modo();
        if (actual && actual !== data.tema && actual !== pedido) {
            pedido = actual;
            setTriggerValue('cambio', actual);
        }
    };
    revisa();
    const reloj = setInterval(revisa, 400);
    return () => clearInterval(reloj);
}
"""

_vigias = {}  # montador del componente por runtime (las pruebas crean uno nuevo por app sin reimportar este módulo)


def vigila_tema():
    """Vuelve a dibujar la página cuando el tema cambia a mano. Va una vez por corrida, arriba de la página."""
    from streamlit.components.v2.get_bidi_component_manager import get_bidi_component_manager

    registro = id(get_bidi_component_manager())
    if registro not in _vigias:
        _vigias[registro] = st.components.v2.component("vigia_tema", js=_VIGIA_JS)
    _vigias[registro](key="vigia_tema", data={"tema": st.context.theme.type or "light"}, height=0,
                      on_cambio_change=lambda: None)


# ------------------------------------------------------------------ cargas con caché
# Las funciones con caché lanzan la excepción (así no se guarda una falla) y quien las
# llama la atrapa.
@st.cache_data(ttl="15m", refresh_mode="background", show_spinner="Leyendo los pronósticos publicados…")
def carga_publicados():
    return F.lee_pronosticos()


@st.cache_data(ttl="15m", refresh_mode="background", show_spinner="Descargando METAR de Carriel Sur…")
def carga_metar():
    return F.metar("SCIE", HORAS_OBS)


@st.cache_data(ttl="15m", refresh_mode="background", show_spinner="Descargando estaciones VIPNet…")
def carga_vipnet(variable):
    return F.vipnet_variable(variable, HORAS_OBS)


@st.cache_data(ttl="1h", max_entries=40, show_spinner="Consultando Open-Meteo en vivo…")
def carga_vivo(lat, lon):
    return F.pronostico_vivo(lat, lon, F.DIAS_PUBLICADOS, F.DIAS_PUBLICADOS)


def calienta_caches():
    """La llama app.py al arrancar y cada pocos minutos: con las entradas frescas es
    casi gratis; con las vencidas dispara su refresco en segundo plano."""
    for f, args in [(carga_publicados, ()), (carga_metar, ()), *[(carga_vipnet, (v,)) for v in VARS_VIPNET]]:
        f(*args)


def metar_seguro():
    try:
        return carga_metar()
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def vipnet_seguro(variable):
    try:
        return carga_vipnet(variable)
    except Exception as ex:  # noqa: BLE001
        return {}, [f"VIPNet {variable}: {str(ex)[:120]}"]


def pronostico(s):
    """(pronóstico, origen, error). Primero la copia que publica la GitHub Action cada hora; si
    falta o tiene más de 3 h, Open-Meteo en vivo; si eso también falla, la copia vieja o nada."""
    ahora_utc = pd.Timestamp.now(tz="UTC")
    try:
        generado, pub = carga_publicados()
    except Exception:  # noqa: BLE001
        generado, pub = None, {}
    local = lambda t: t.tz_convert(F.ZONA).strftime("%d/%m %H:%M")  # noqa: E731
    if generado is not None and s["id"] in pub and ahora_utc - generado < VIEJO:
        return pub[s["id"]], f"copia publicada a las {local(generado)}", None
    try:
        return carga_vivo(s["lat"], s["lon"]), "Open-Meteo en vivo", None
    except Exception as ex:  # noqa: BLE001
        if generado is not None and s["id"] in pub:
            return pub[s["id"]], f"copia publicada a las {local(generado)} (desactualizada)", str(ex)
        return VACIO, None, str(ex)


# ------------------------------------------------------------------ contexto de la corrida
def prepara_contexto(sitio_id, pasado, futuro, modelos, con_ensamble):
    """Arma el contexto de esta corrida y lo deja en st.session_state para las páginas."""
    sitio = F.SITIO[sitio_id]
    ahora = F.ahora_local()
    t0 = pd.Timestamp(ahora).floor("h") - pd.Timedelta(days=pasado)
    t_fin = pd.Timestamp(ahora).floor("D") + pd.Timedelta(days=futuro)
    metar = metar_seguro()
    pron, origen, error = pronostico(sitio)
    avisos = []

    def recorta(df):
        if df is None or df.empty:
            return df
        return df[(df.index >= t0) & (df.index < t_fin)]

    def det_var(v):
        return pron["det"].get(v, pd.DataFrame())

    def observado(s, variable):
        """Serie horaria observada de 'variable' en el sitio s (o None), ventana completa."""
        if variable not in s["vars"]:
            return None
        if s["fuente"] == "metar":
            col = F.VARIABLES[variable]["metar"]
            o = metar[col].dropna() if not metar.empty and col in metar else None
        else:
            series, av = vipnet_seguro(variable)
            avisos.extend(av)
            o = series.get(s["id"])
        return None if o is None else o[o.index >= t0]

    c = SimpleNamespace(sitio=sitio, pasado=pasado, futuro=futuro, modelos=modelos, con_ensamble=con_ensamble,
                        ahora=ahora, t0=t0, t_fin=t_fin, metar=metar, pron=pron, det=pron["det"],
                        pct=pron["pct"], origen_pron=origen, error_pron=error, avisos=avisos,
                        recorta=recorta, det_var=det_var, observado=observado)
    st.session_state["_ctx"] = c
    return c


def contexto():
    return st.session_state["_ctx"]


# ------------------------------------------------------------------ utilidades de gráficos y texto
def barra(boton="resetScale2d"):
    return {"displayModeBar": True, "displaylogo": False, "modeBarButtons": [[boton]]}


def linea_ahora(fig, ahora, xref="x", yref="paper"):
    """add_shape en vez de add_vline: add_vline falla con Timestamps de pandas."""
    x = pd.Timestamp(ahora).isoformat()
    fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, xref=xref, yref=yref,
                  line=dict(color=ROJO, width=1.4, dash="dot"))


def fmt(v, dec, unidad=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dec}f}{(' ' + unidad) if unidad else ''}"


# ------------------------------------------------------------------ mapas satelitales
MARCO_MAPA = "rgba(128,128,128,.45)"  # gris semitransparente: se ve igual de discreto sobre fondo claro u oscuro
# El mapa de MapLibre es un div aparte dentro del gráfico: se le redondean las esquinas y se le pone un filete
# fino, así la imagen satelital no termina en un corte seco contra el fondo de la página.
CSS_MAPAS = f"""<style>
.stPlotlyChart .maplibregl-map {{ border-radius: 12px; overflow: hidden; box-shadow: 0 0 0 1px {MARCO_MAPA}; }}
</style>"""


def encuadre(lats, lons, ancho, alto, borde=36, der=0):
    """Centro y zoom que dejan todos los puntos dentro de un mapa de ancho × alto px, con 'borde' px libres
    por lado y 'der' px más de ancho para las etiquetas a la derecha de cada punto. Los puntos quedan
    centrados: si el mapa sale más angosto, se recortan primero las etiquetas del este y no las estaciones
    de la costa. Proyección de Mercator con mosaicos de 512 px, que es lo que usa MapLibre."""
    y = np.log(np.tan(np.pi / 4 + np.radians(np.asarray(lats, float)) / 2))  # latitud en Mercator (rad)
    x = np.radians(np.asarray(lons, float))
    zx = np.log2((ancho - 2 * borde - der) / 512 * 2 * np.pi / max(x.max() - x.min(), 1e-4))
    zy = np.log2((alto - 2 * borde) / 512 * 2 * np.pi / max(y.max() - y.min(), 1e-4))
    zoom = float(min(zx, zy))
    lon_c = (x.max() + x.min()) / 2
    lat_c = 2 * np.arctan(np.exp((y.max() + y.min()) / 2)) - np.pi / 2
    return dict(center=dict(lat=float(np.degrees(lat_c)), lon=float(np.degrees(lon_c))), zoom=round(zoom, 2))


def mapa_satelital(fig, sitios, ancho, alto, der=0):
    """Fondo Esri World Imagery y encuadre que muestra todas las estaciones. 'ancho' es el ancho más angosto con
    que se espera ver el gráfico: si el mapa sale más ancho, manda el alto y solo se ve más terreno a los lados."""
    fig.update_layout(map=dict(style="white-bg", **encuadre([s["lat"] for s in sitios], [s["lon"] for s in sitios],
                                                            ancho, alto, der=der),
                               layers=[dict(sourcetype="raster", source=[F.ESRI], below="traces")]),
                      height=alto)


def _data_uri(ruta):
    return "data:image/svg+xml;base64," + base64.b64encode(ruta.read_bytes()).decode()


_LOGO_URI = {False: _data_uri(CLARO.logo), True: _data_uri(OSCURO.logo)}
_kaleido = threading.Lock()
_kaleido_listo = False
ANCHO_EXPORTA = 1400
LOGO_ALTO = 46  # px; el logo completo mide 780 × 199,5 (proporción 3,91)


def _area_dibujo(f, ancho, alto):
    """(ancho, alto) en px del área de dibujo ("paper"), que los márgenes automáticos (leyendas, títulos de
    ejes) agrandan sin avisar: se mide en un SVG de prueba, uniendo el recorte de cada subgráfico (los
    recortes de un solo eje ocupan todo el ancho o todo el alto y se descartan)."""
    svg = f.to_image(format="svg", width=ancho, height=alto).decode()
    cajas = [(x, y, w, h) for x, y, w, h in (map(float, c) for c in re.findall(
        r'class="axesclip"><rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg))
        if w < ancho and h < alto]
    if not cajas:  # mapas: sin fondo cartesiano, el área es lo que dejan los márgenes
        m = f.layout.margin
        return ancho - (m.l or 0) - (m.r or 0), alto - (m.t or 0) - (m.b or 0)
    return (max(x + w for x, _, w, _ in cajas) - min(x for x, _, _, _ in cajas),
            max(y + h for _, y, _, h in cajas) - min(y for _, y, _, _ in cajas))


def exporta(fig, formato, oscuro):
    """PNG (al doble de resolución) o PDF vectorial de la figura, con el fondo del modo en que se veía y
    el logo de MetGeo arriba a la derecha. Lo dibuja kaleido con un Chrome que queda abierto (la primera
    exportación tarda unos segundos; las siguientes, décimas)."""
    global _kaleido_listo
    p = OSCURO if oscuro else CLARO
    f = go.Figure(fig)
    alto = (fig.layout.height or 450) + LOGO_ALTO + 10
    m = fig.layout.margin
    f.update_layout(template=p.plantilla, paper_bgcolor=p.fondo, plot_bgcolor=p.fondo, height=alto,
                    margin=dict(l=max(m.l or 0, 30), r=max(m.r or 0, 30), t=(m.t or 0) + LOGO_ALTO + 10,
                                b=max(m.b or 0, 30)))
    if any(t.type == "scattermap" for t in f.data):  # el filete de CSS_MAPAS no llega a kaleido: se dibuja aquí
        f.add_shape(type="rect", xref="paper", yref="paper", x0=0, x1=1, y0=0, y1=1, layer="above",
                    line=dict(color=MARCO_MAPA, width=1))
    with _kaleido:
        if not _kaleido_listo:
            import kaleido
            kaleido.start_sync_server(silence_warnings=True)
            _kaleido_listo = True
        ancho_px, alto_px = _area_dibujo(f, ANCHO_EXPORTA, alto)
        # logo justo encima de la esquina superior derecha del área de dibujo, en el margen que se agregó
        f.add_layout_image(source=_LOGO_URI[oscuro], xref="paper", yref="paper", x=1, y=1 + 4 / alto_px,
                           xanchor="right", yanchor="bottom", sizex=LOGO_ALTO * 3.91 / ancho_px,
                           sizey=LOGO_ALTO / alto_px, sizing="contain", layer="above")
        return f.to_image(format=formato, width=ANCHO_EXPORTA, height=alto, scale=2 if formato == "png" else 1)


def grafico(fig, nombre, config=None, key=None, **kw):
    """st.plotly_chart más los botones para descargar la figura en PNG o PDF. 'nombre' va en el archivo;
    'kw' pasa directo a st.plotly_chart (on_select, selection_mode)."""
    st.plotly_chart(fig, config=config or barra(), key=key, **kw)
    oscuro = paleta().oscuro
    archivo = f"metgeo_{nombre}_{F.ahora_local():%Y%m%d_%H%M}"
    with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
        for formato, mime, ayuda in [("png", "image/png", "Imagen PNG en alta resolución"),
                                     ("pdf", "application/pdf", "PDF vectorial, editable")]:
            st.download_button(formato.upper(), data=lambda formato=formato: exporta(fig, formato, oscuro),
                               file_name=f"{archivo}.{formato}", mime=mime, on_click="ignore", type="tertiary",
                               icon=":material/download:", help=ayuda, key=f"dl_{key or nombre}_{formato}")


def logo():
    """Logo de la barra superior según el modo claro u oscuro."""
    p = paleta()
    st.logo(str(p.logo), icon_image=str(p.icono), size="large")


def nombre_modelo(m):
    corto, centro, _ = F.MODELOS[m]
    return f"{corto} ({centro})"


def metricas_ahora(c):
    """Última observación del sitio elegido; lo que el sitio no mide queda en «—»."""
    sitio = c.sitio

    def ultimo(variable):
        """(valor, hora) de la última medición del sitio; (nan, None) si no la mide o no hay dato."""
        o = c.observado(sitio, variable)
        o = None if o is None else o.dropna()
        if o is None or o.empty:
            return np.nan, None
        return float(o.iloc[-1]), o.index[-1]

    horas = []
    tarjetas = []
    for var, nombre, dec, unidad, icono in [
        ("temperatura", "Temperatura", 0, "°C", "thermostat"),
        ("humedad", "Humedad", 0, "%", "humidity_percentage"),
        ("viento", "Viento", 0, "km/h", "air"),
        ("rafaga", "Ráfaga", 0, "km/h", "storm"),
        ("presion", "Presión", 0, "hPa", "speed"),
    ]:
        v, h = ultimo(var)
        if h is not None:
            horas.append(h)
        delta = None
        if var == "viento" and h is not None:
            delta = F.cardinal(ultimo("direccion")[0])
        elif var == "presion" and h is not None:
            p = c.observado(sitio, "presion").dropna()
            hace3 = p[p.index <= h - pd.Timedelta(hours=3)]
            delta = f"{v - hace3.iloc[-1]:+.0f} hPa en 3 h" if len(hace3) else None
        # el METAR informa ráfaga solo cuando es significativa: sin dato con METAR vigente = sin ráfagas
        sin_rafagas = var == "rafaga" and var in sitio["vars"] and np.isnan(v) and not c.metar.empty
        tarjetas.append((nombre, "sin ráfagas" if sin_rafagas else fmt(v, dec, unidad), delta, icono))

    pp = c.observado(sitio, "precipitacion")
    pp24 = np.nan
    if pp is not None and not pp.empty:
        pp24 = pp[pp.index > pp.index.max() - pd.Timedelta(hours=24)].sum()
        horas.append(pp.index.max())
    tarjetas.append(("Lluvia 24 h", fmt(pp24, 1, "mm"), None, "rainy"))

    if horas:
        h = max(horas)
        st.caption(f"Ahora en {F.etiqueta(sitio)} · última medición a las {h:%H:%M} del {h:%d/%m} "
                   "(hora de Chile). «—»: sin medición de esa variable en esta estación.")
    else:
        st.caption(f"Sin mediciones recientes de {F.etiqueta(sitio)}.")
    # fila horizontal: se reparte en varias líneas sola en pantallas angostas
    with st.container(horizontal=True, gap="small"):
        for nombre, valor, delta, icono in tarjetas:
            st.metric(nombre, valor, delta, delta_color="off", delta_arrow="off", border=True,
                      icon=f":material/{icono}:")


# ------------------------------------------------------------------ controles
def controles():
    """Barra de controles (reemplaza a la barra lateral): el sitio a la vista y el resto dentro de
    "Ajustes". Arma y devuelve el contexto de la corrida. Sitio y días quedan en la URL para
    compartir la vista; modelos y banda se conservan al cambiar de página."""
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        sitio_id = st.selectbox("Sitio", [s["id"] for s in F.SITIOS], format_func=lambda i: F.etiqueta(F.SITIO[i]),
                                key="sitio", bind="query-params", width=290,
                                help="Los modelos se consultan en las coordenadas del sitio elegido.")
        with st.popover("Ajustes", icon=":material/tune:"):
            pasado = st.slider("Días hacia atrás", 1, F.DIAS_PUBLICADOS, 3, key="pasado", bind="query-params")
            futuro = st.slider("Días de pronóstico", 1, F.DIAS_PUBLICADOS, 5, key="futuro", bind="query-params")
            modelos = st.multiselect("Modelos", list(F.MODELOS), default=list(F.MODELOS), format_func=nombre_modelo,
                                     key="modelos", persist_state="session")
            con_ensamble = st.toggle("Banda del super-ensamble (p10–p90)", value=True, key="banda",
                                     persist_state="session")
            st.caption("Los datos se renuevan solos cada hora.")
        origen = st.empty()
    c = prepara_contexto(sitio_id, pasado, futuro, modelos, con_ensamble)
    origen.caption(f":material/schedule: Pronóstico: {c.origen_pron or 'no disponible'}")
    if c.error_pron and c.origen_pron is None:
        st.warning("No se pudo obtener el pronóstico (Open-Meteo no respondió y todavía no hay copia publicada). "
                   "Se muestran solo las observaciones; vuelve a intentar en unos minutos.  \n"
                   f"Detalle: `{c.error_pron[:160]}`", icon=":material/cloud_off:")
    elif c.error_pron:
        st.caption(f":material/info: Open-Meteo no respondió; se muestra la {c.origen_pron}.")
    return c
