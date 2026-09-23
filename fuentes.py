"""
Descarga y ordena los datos del monitor: observaciones (VIPNet DGA/MOP y
METAR de Carriel Sur) y pronósticos (7 modelos deterministas y el
super-ensamble de 143 miembros, ambos vía Open-Meteo).

Todas las series quedan en hora local de Chile (America/Santiago), sin zona
horaria, en pasos horarios. El valor de la hora T es:
- lluvia: lo caído en la hora que TERMINA en T (misma convención que Open-Meteo);
- el resto: el valor instantáneo más cercano a T (media de la hora que termina en T
  para las estaciones VIPNet, que miden cada 30 min).
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ZONA = ZoneInfo("America/Santiago")
UA = {"User-Agent": "monitor-meteo-concepcion (divulgación; github.com/Heszo)"}
URL_VIPNET = "https://vipnet.mop.gob.cl/v1/vipnet/estacion/valores"
URL_METAR = "https://aviationweather.gov/api/data/metar"
URL_OM = "https://api.open-meteo.com/v1/forecast"
URL_ENS = "https://ensemble-api.open-meteo.com/v1/ensemble"
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

# ------------------------------------------------------------------ catálogo
# clave: dict(nombre, unidad, om = variable de Open-Meteo, vipnet = tipoEstacion,
#            metar = columna del METAR, ens = si el super-ensamble la trae)
VARIABLES = {
    "temperatura": dict(nombre="Temperatura", unidad="°C", om="temperature_2m", vipnet=1,
                        metar="temperatura", decimales=1),
    "humedad": dict(nombre="Humedad relativa", unidad="%", om="relative_humidity_2m", vipnet=4,
                    metar="humedad", decimales=0),
    "viento": dict(nombre="Viento medio (10 m)", unidad="km/h", om="wind_speed_10m", vipnet=None,
                   metar="viento", decimales=0),
    "rafaga": dict(nombre="Ráfaga (10 m)", unidad="km/h", om="wind_gusts_10m", vipnet=None,
                   metar="rafaga", decimales=0),
    "direccion": dict(nombre="Dirección del viento", unidad="°", om="wind_direction_10m", vipnet=None,
                      metar="direccion", decimales=0, sin_ensamble=True),
    "presion": dict(nombre="Presión al nivel del mar", unidad="hPa", om="pressure_msl", vipnet=None,
                    metar="presion", decimales=1),
    "precipitacion": dict(nombre="Precipitación", unidad="mm/h", om="precipitation", vipnet=0,
                          metar=None, decimales=1),
}

MODELOS = {
    "gfs_seamless": ("GFS", "NOAA", "#1f77b4"),
    "ecmwf_ifs025": ("IFS", "ECMWF", "#d62728"),
    "icon_seamless": ("ICON", "DWD", "#2ca02c"),
    "gem_seamless": ("GEM", "Canadá", "#9467bd"),
    "jma_seamless": ("GSM", "JMA", "#8c564b"),
    "ukmo_seamless": ("UM", "UK Met Office", "#e377c2"),
    "meteofrance_seamless": ("ARPEGE", "Météo-France", "#ff7f0e"),
}
ENSAMBLES = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_global"]  # 31+51+40+21 = 143

# Sitios: la estación METAR del aeropuerto y las estaciones VIPNet del Gran
# Concepción. "vars" = variables que mide (verificado el 23/09/2026).
SITIOS = [
    dict(id="carrielsur", nombre="Carriel Sur (aeropuerto)", fuente="metar", codigo="SCIE",
         lat=-36.7727, lon=-73.0631, grupo="ciudad",
         vars=["temperatura", "humedad", "viento", "rafaga", "direccion", "presion"]),
    dict(id="concepcion", nombre="Concepción DGA", fuente="vipnet", codigo="08410001-3",
         lat=-36.8332, lon=-73.1005, grupo="ciudad", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="nonguen", nombre="Nonguén", fuente="vipnet", codigo="08220008-8",
         lat=-36.8202, lon=-73.0164, grupo="ciudad", vars=["precipitacion"]),
    dict(id="biobio", nombre="Desembocadura Biobío", fuente="vipnet", codigo="08394001-8",
         lat=-36.8378, lon=-73.0615, grupo="ciudad", vars=["precipitacion"]),
    dict(id="andalien", nombre="Andalién", fuente="vipnet", codigo="08220006-1",
         lat=-36.8130, lon=-72.9390, grupo="ciudad", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="hualqui", nombre="Hualqui", fuente="vipnet", codigo="08393002-0",
         lat=-36.9825, lon=-72.9414, grupo="ciudad", vars=["precipitacion"]),
    dict(id="talcahuano", nombre="Talcahuano", fuente="vipnet", codigo="08230000-7",
         lat=-36.7078, lon=-73.1135, grupo="costa", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="quiriquina", nombre="Isla Quiriquina", fuente="vipnet", codigo="08240000-1",
         lat=-36.6084, lon=-73.0499, grupo="costa", vars=["precipitacion"]),
    dict(id="tome", nombre="Tomé", fuente="vipnet", codigo="08210003-2",
         lat=-36.6396, lon=-72.9494, grupo="costa", vars=["precipitacion"]),
    dict(id="dichato", nombre="Dichato", fuente="vipnet", codigo="08210002-4",
         lat=-36.5456, lon=-72.9311, grupo="costa", vars=["precipitacion"]),
    dict(id="coronel", nombre="Coronel", fuente="vipnet", codigo="08410005-6",
         lat=-36.9892, lon=-73.1178, grupo="costa", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="lota", nombre="Lota", fuente="vipnet", codigo="08420001-8",
         lat=-37.0950, lon=-73.1506, grupo="costa", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="pataguas", nombre="Las Pataguas", fuente="vipnet", codigo="08220005-3",
         lat=-36.7924, lon=-72.8923, grupo="interior", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="rafael", nombre="Rafael", fuente="vipnet", codigo="08140001-6",
         lat=-36.6365, lon=-72.8490, grupo="interior", vars=["precipitacion"]),
    dict(id="florida", nombre="Florida", fuente="vipnet", codigo="08220015-0",
         lat=-36.8228, lon=-72.6669, grupo="interior", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="huinanco", nombre="Huinanco", fuente="vipnet", codigo="08392002-5",
         lat=-36.9939, lon=-72.7297, grupo="interior", vars=["temperatura", "humedad", "precipitacion"]),
    dict(id="santajuana", nombre="Santa Juana", fuente="vipnet", codigo="08391003-8",
         lat=-37.1819, lon=-72.9408, grupo="interior", vars=["temperatura", "humedad", "precipitacion"]),
]
SITIO = {s["id"]: s for s in SITIOS}
GRUPOS = {"costa": "#00797C", "ciudad": "#E0701A", "interior": "#6B3FA0"}


def ahora_local():
    return datetime.now(ZONA).replace(tzinfo=None)


def a_local(utc):
    """DatetimeIndex/Series UTC (con o sin tz) -> hora de Chile sin zona."""
    t = pd.DatetimeIndex(pd.to_datetime(utc, utc=True))
    return t.tz_convert(ZONA).tz_localize(None)


# ------------------------------------------------------------------ VIPNet
def vipnet(codigo, tipo, horas):
    """Serie cruda (cada 30 min) de una estación VIPNet: DataFrame[hora, valor]."""
    t = ahora_local()  # la API arma la ventana en hora chilena
    cuerpo = {"codigoEstacion": codigo, "tipoEstacion": tipo, "fetchHour": t.hour,
              "fetchDay": f"{t:%Y-%m-%d}", "hoursRange": int(horas)}
    r = requests.post(URL_VIPNET, json=cuerpo, headers=UA, timeout=30)
    r.raise_for_status()
    d = r.json().get("data", [])
    if not d:
        return pd.DataFrame(columns=["hora", "valor"])
    df = pd.DataFrame({"hora": a_local([x["fecha"]["$date"] for x in d]),
                       "valor": [np.nan if x.get("instantaneo") is None else float(x["instantaneo"])
                                 for x in d]})
    return df.sort_values("hora").drop_duplicates("hora").reset_index(drop=True)


def a_horaria(df, variable):
    """Pasa una serie cruda a horaria (hora que termina en T). Lluvia: suma,
    solo horas completas; resto: media de la hora."""
    if df.empty:
        return pd.Series(dtype=float)
    g = df.groupby(df.hora.dt.ceil("h"))["valor"]
    if variable != "precipitacion":
        return g.mean()
    paso = df.hora.diff().median()
    por_hora = max(int(round(pd.Timedelta(hours=1) / paso)), 1) if pd.notna(paso) else 1
    tab = g.agg(["sum", "count"])
    return tab.loc[tab["count"] >= por_hora, "sum"]


def vipnet_variable(variable, horas):
    """{id_sitio: Series horaria} para todas las estaciones VIPNet que miden
    'variable', descargadas en paralelo. Devuelve también la lista de avisos."""
    tipo = VARIABLES[variable]["vipnet"]
    sitios = [s for s in SITIOS if s["fuente"] == "vipnet" and variable in s["vars"]]

    def una(s):
        try:
            return s["id"], a_horaria(vipnet(s["codigo"], tipo, horas), variable), None
        except Exception as ex:  # noqa: BLE001
            return s["id"], None, f"{s['nombre']}: {str(ex)[:120]}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        res = list(pool.map(una, sitios))
    series = {i: s for i, s, _ in res if s is not None and not s.empty}
    avisos = [a for _, _, a in res if a]
    avisos += [f"{SITIO[i]['nombre']}: sin datos de {VARIABLES[variable]['nombre'].lower()}"
               for i, s, a in res if a is None and (s is None or s.empty)]
    return series, avisos


# ------------------------------------------------------------------ METAR
def humedad_relativa(t, td):
    """Magnus (Alduchov y Eskridge, 1996)."""
    a, b = 17.625, 243.04
    return 100 * np.exp(a * td / (b + td)) / np.exp(a * t / (b + t))


def metar(estacion="SCIE", horas=72):
    """METAR/SPECI de una estación: DataFrame horario (hora local) con
    temperatura, humedad, viento, ráfaga, dirección y presión (QNH)."""
    r = requests.get(URL_METAR, params={"ids": estacion, "format": "json", "hours": int(horas)},
                     headers=UA, timeout=30)
    r.raise_for_status()
    d = r.json()
    if not d:
        return pd.DataFrame()

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return np.nan  # p. ej. dirección "VRB"

    df = pd.DataFrame({
        "hora": a_local(pd.to_datetime([x["obsTime"] for x in d], unit="s")),
        "tipo": [x.get("metarType") for x in d],
        "temperatura": [num(x.get("temp")) for x in d],
        "rocio": [num(x.get("dewp")) for x in d],
        "viento": [num(x.get("wspd")) * 1.852 for x in d],
        "rafaga": [num(x.get("wgst")) * 1.852 for x in d],
        "direccion": [num(x.get("wdir")) for x in d],
        "presion": [num(x.get("altim")) for x in d],
        "texto": [x.get("rawOb", "") for x in d],
    })
    df["humedad"] = humedad_relativa(df.temperatura, df.rocio)
    # viento calmo: la dirección no tiene sentido
    df.loc[df.viento == 0, "direccion"] = np.nan
    # a la hora más cercana; entre METAR y SPECI de la misma hora, gana el METAR
    df["hora_redonda"] = df.hora.dt.round("h")
    df = (df.sort_values(["hora_redonda", "tipo"])
          .drop_duplicates("hora_redonda", keep="first")
          .set_index("hora_redonda").sort_index())
    df.index.name = "hora"
    return df


# ------------------------------------------------------------------ Open-Meteo
# Open-Meteo gratuito limita las consultas por IP. En Streamlit Community Cloud la IP es compartida
# con otras apps y suele estar agotada (HTTP 429), así que la app lee los pronósticos que una GitHub
# Action publica cada hora en la rama "datos" (ver actualiza_pronosticos.py) y solo consulta en vivo
# si esa copia falta o está vieja.
REPO = "Heszo/monitor-meteo-concepcion"
URL_PUBLICADOS = os.environ.get("MONITOR_DATOS", f"https://raw.githubusercontent.com/{REPO}/datos")  # URL o carpeta
DIAS_PUBLICADOS = 7  # pasado y futuro guardados en la copia publicada (el máximo de la barra lateral)


class OpenMeteoError(RuntimeError):
    pass


def _get_json(url, params, intentos=4, timeout=60):
    """GET con reintentos ante 429, errores 5xx, cortes y respuestas que no son JSON."""
    ultimo = ""
    for k in range(intentos):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                ultimo = f"HTTP {r.status_code}"
            else:
                r.raise_for_status()
                return r.json()
        except (requests.Timeout, requests.ConnectionError, ValueError) as ex:
            ultimo = type(ex).__name__
        except requests.HTTPError as ex:  # 4xx distinto de 429: no tiene sentido reintentar
            raise OpenMeteoError(f"{url.split('/')[2]}: {ex.response.status_code} {ex.response.text[:200]}") from None
        if k < intentos - 1:
            time.sleep(2 * 2 ** k)
    raise OpenMeteoError(f"{url.split('/')[2]}: {ultimo} tras {intentos} intentos")


def _params(lat, lon, variables, pasado, futuro):
    return dict(latitude=lat, longitude=lon, hourly=",".join(variables), past_days=int(pasado),
                forecast_days=int(futuro), timezone="America/Santiago", wind_speed_unit="kmh")


def _serie(valores):
    return np.array([np.nan if x is None else x for x in valores], float)


def deterministas(lat, lon, pasado, futuro):
    """{variable: DataFrame(tiempo x modelo)} de los 7 modelos deterministas."""
    oms = [v["om"] for v in VARIABLES.values()]
    h = _get_json(URL_OM, _params(lat, lon, oms, pasado, futuro) | {"models": ",".join(MODELOS)})["hourly"]
    t = pd.to_datetime(h["time"])
    salida = {}
    for clave, v in VARIABLES.items():
        cols = {m: _serie(h[f"{v['om']}_{m}"]) for m in MODELOS if f"{v['om']}_{m}" in h}
        salida[clave] = pd.DataFrame({m: x for m, x in cols.items() if np.isfinite(x).any()}, index=t)
    return salida


def ensamble(lat, lon, pasado, futuro):
    """{variable: DataFrame(tiempo x miembro)} del super-ensamble (los 4
    centros juntos). La dirección se omite: sus percentiles no tienen sentido.
    Si un centro no responde se sigue con los demás; si no responde ninguno, error."""
    claves = [k for k, v in VARIABLES.items() if not v.get("sin_ensamble")]
    oms = [VARIABLES[k]["om"] for k in claves]

    def uno(modelo):
        try:
            return modelo, _get_json(URL_ENS, _params(lat, lon, oms, pasado, futuro) | {"models": modelo},
                                     timeout=90)["hourly"]
        except OpenMeteoError:
            return modelo, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        respuestas = [(m, h) for m, h in pool.map(uno, ENSAMBLES) if h]
    if not respuestas:
        raise OpenMeteoError("ensemble-api.open-meteo.com: ningún centro respondió")
    t = pd.to_datetime(respuestas[0][1]["time"])
    salida = {}
    for clave, om in zip(claves, oms):
        cols = {}
        for modelo, h in respuestas:
            for k, valores in h.items():
                if k == om or k.startswith(om + "_member"):
                    serie = _serie(valores)
                    if np.isfinite(serie).any():
                        cols[f"{modelo}:{k}"] = serie
        salida[clave] = pd.DataFrame(cols, index=t)
    return salida


def percentiles(miembros, qs=(10, 50, 90)):
    if miembros is None or miembros.empty:
        return None
    return pd.DataFrame({f"p{q}": np.nanpercentile(miembros.values, q, axis=1) for q in qs},
                        index=miembros.index)


def resumen_pronostico(det, ens):
    """Lo que la app usa de un sitio: deterministas, percentiles del ensamble
    por variable, los miembros de lluvia (para acumulados y bloques) y la
    ráfaga de cada bloque de 6 h (mediana entre miembros del máximo del bloque)."""
    raf = ens.get("rafaga")
    raf6h = None
    if raf is not None and not raf.empty:
        raf6h = raf.resample("6h", origin="start_day", closed="right", label="left").max().median(axis=1)
    return {"det": det, "pct": {k: percentiles(v) for k, v in ens.items()},
            "pp": ens.get("precipitacion"), "raf6h": raf6h}


def pronostico_vivo(lat, lon, pasado, futuro, exige_ensamble=True):
    """Resumen de un sitio en vivo. Con exige_ensamble=False, si el ensamble no responde se
    devuelven igual los 7 modelos (sin banda ni miembros de lluvia)."""
    det = deterministas(lat, lon, pasado, futuro)
    try:
        ens = ensamble(lat, lon, pasado, futuro)
    except OpenMeteoError:
        if exige_ensamble:
            raise
        ens = {}
    return resumen_pronostico(det, ens)


# --- copia publicada: 4 tablas parquet con columnas "sitio|variable|serie"
def guarda_pronosticos(por_sitio, carpeta, generado):
    import json
    from pathlib import Path

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    tablas = {"det": {}, "pct": {}, "pp": {}, "raf6h": {}}
    for sid, r in por_sitio.items():
        for var, df in r["det"].items():
            for c in df:
                tablas["det"][f"{sid}|{var}|{c}"] = df[c]
        for var, df in r["pct"].items():
            if df is not None:
                for c in df:
                    tablas["pct"][f"{sid}|{var}|{c}"] = df[c]
        if r["pp"] is not None:
            for c in r["pp"]:
                tablas["pp"][f"{sid}|precipitacion|{c}"] = r["pp"][c]
        if r["raf6h"] is not None:
            tablas["raf6h"][f"{sid}|rafaga|p50"] = r["raf6h"]
    for nombre, cols in tablas.items():
        pd.DataFrame(cols).astype("float32").to_parquet(carpeta / f"{nombre}.parquet", compression="zstd")
    (carpeta / "meta.json").write_text(json.dumps({"generado": generado, "sitios": sorted(por_sitio)}))


def _desarma(df):
    """{sitio: {variable: DataFrame(tiempo x serie)}} desde columnas 'sitio|variable|serie'."""
    salida = {}
    for col in df.columns:
        sid, var, serie = col.split("|", 2)
        salida.setdefault(sid, {}).setdefault(var, {})[serie] = df[col].astype(float)
    return {sid: {v: pd.DataFrame(c) for v, c in vs.items()} for sid, vs in salida.items()}


def lee_pronosticos(base=URL_PUBLICADOS):
    """(generado, {sitio: resumen}) desde la copia publicada (URL o carpeta)."""
    import io
    import json
    from pathlib import Path

    def lee(nombre):
        if str(base).startswith("http"):
            r = requests.get(f"{base}/{nombre}", headers=UA, timeout=30)
            r.raise_for_status()
            return r.content
        return (Path(base) / nombre).read_bytes()

    meta = json.loads(lee("meta.json"))
    t = {n: _desarma(pd.read_parquet(io.BytesIO(lee(f"{n}.parquet")))) for n in ("det", "pct", "pp", "raf6h")}
    por_sitio = {}
    for sid in meta["sitios"]:
        pp = t["pp"].get(sid, {}).get("precipitacion")
        raf = t["raf6h"].get(sid, {}).get("rafaga")
        por_sitio[sid] = {"det": t["det"].get(sid, {}), "pct": t["pct"].get(sid, {}), "pp": pp,
                          "raf6h": raf["p50"] if raf is not None else None}
    return pd.Timestamp(meta["generado"]), por_sitio


# ------------------------------------------------------------------ verificación
def diferencia(pron, obs, variable):
    """Diferencia pronóstico - observado; la dirección se toma en el círculo
    (-180, 180]."""
    d = pron - obs
    if variable == "direccion":
        d = (d + 180) % 360 - 180
    return d


def verificacion(modelos_df, obs, variable, hasta):
    """Métricas de cada modelo contra la observación en las horas ya
    ocurridas (<= hasta): n, sesgo, MAE, RMSE, correlación."""
    filas = []
    obs = obs[(obs.index <= hasta)].dropna()
    for m in modelos_df.columns:
        par = pd.concat([modelos_df[m], obs], axis=1, join="inner").dropna()
        if len(par) < 3:
            continue
        d = diferencia(par.iloc[:, 0], par.iloc[:, 1], variable)
        corr = par.iloc[:, 0].corr(par.iloc[:, 1]) if variable != "direccion" else np.nan
        filas.append(dict(modelo=m, n=len(par), sesgo=d.mean(), mae=d.abs().mean(),
                          rmse=float(np.sqrt((d ** 2).mean())), r=corr))
    return pd.DataFrame(filas).sort_values("mae") if filas else pd.DataFrame()


def cardinal(grados):
    if grados is None or np.isnan(grados):
        return "—"
    nombres = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
    return nombres[int((grados + 11.25) // 22.5) % 16]
