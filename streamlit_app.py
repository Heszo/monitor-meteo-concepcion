"""
Monitor meteorológico del Gran Concepción: lluvia, temperatura, humedad,
viento y presión, observados (VIPNet DGA/MOP y METAR de Carriel Sur) y
pronosticados por 7 modelos globales y un super-ensamble de 143 miembros
(Open-Meteo). Página principal: navegación, controles compartidos y
encabezado; cada vista vive en app_pages/.

Se lanza con `streamlit run app.py` (app.py envuelve este script en st.App
para mantener la caché caliente); `streamlit run streamlit_app.py` también
funciona, sin ese precalentamiento.
"""
import streamlit as st

import comun as C
import fuentes as F

st.set_page_config(page_title="Monitor meteorológico · Gran Concepción", page_icon=":material/partly_cloudy_day:",
                   layout="wide")

PAGINAS = {
    "presentacion": st.Page("app_pages/presentacion.py", title="Presentación", icon=":material/home:", default=True),
    "comparar": st.Page("app_pages/comparar.py", title="Comparar modelos", icon=":material/stacked_line_chart:"),
    "lluvia": st.Page("app_pages/lluvia.py", title="Lluvia", icon=":material/water_drop:"),
    "meteograma": st.Page("app_pages/meteograma.py", title="Meteograma", icon=":material/monitoring:"),
    "mapa": st.Page("app_pages/mapa.py", title="Mapa de estaciones", icon=":material/map:"),
}
pagina = st.navigation(list(PAGINAS.values()), position="top")

# controles compartidos: enlazados a la URL (?sitio=lota&pasado=5…) para poder compartir una vista
with st.sidebar:
    st.subheader("Ajustes")
    sitio_id = st.selectbox("Sitio", [s["id"] for s in F.SITIOS], format_func=lambda i: F.SITIO[i]["nombre"],
                            key="sitio", bind="query-params",
                            help="Los modelos se consultan en las coordenadas del sitio elegido.")
    pasado = st.slider("Días hacia atrás", 1, F.DIAS_PUBLICADOS, 3, key="pasado", bind="query-params")
    futuro = st.slider("Días de pronóstico", 1, F.DIAS_PUBLICADOS, 5, key="futuro", bind="query-params")
    modelos = st.multiselect("Modelos", list(F.MODELOS), default=list(F.MODELOS), format_func=C.nombre_modelo,
                             key="modelos")
    con_ensamble = st.toggle("Banda del super-ensamble (p10–p90)", value=True, key="banda")
    if st.button("Forzar actualización", icon=":material/refresh:"):
        st.cache_data.clear()
    st.caption("Los datos se renuevan solos cada 15 minutos.")
    st.markdown(":material/code: [Código en GitHub](https://github.com/Heszo/monitor-meteo-concepcion) · "
                "[github.com/Heszo](https://github.com/Heszo)")
    aviso_origen = st.empty()

c = C.prepara_contexto(sitio_id, pasado, futuro, modelos, con_ensamble)
aviso_origen.caption(f"Pronóstico: {c.origen_pron or 'no disponible'}.")

if c.error_pron and c.origen_pron is None:
    st.warning("No se pudo obtener el pronóstico (Open-Meteo no respondió y todavía no hay copia publicada). "
               "Se muestran solo las observaciones; vuelve a intentar en unos minutos.  \n"
               f"Detalle: `{c.error_pron[:160]}`", icon=":material/cloud_off:")
elif c.error_pron:
    st.info(f"Open-Meteo no respondió; se muestra la {c.origen_pron}.", icon=":material/info:")

if pagina.title != "Presentación":
    st.title(f"{pagina.title} · Gran Concepción", anchor=False)
    C.metricas_ahora(c)
    st.divider()

pagina.run()
