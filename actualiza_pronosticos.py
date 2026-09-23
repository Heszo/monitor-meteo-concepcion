"""
Baja de Open-Meteo los pronósticos de todos los sitios (7 modelos + super-ensamble,
DIAS_PUBLICADOS días hacia atrás y hacia adelante) y los guarda como parquet en la
carpeta indicada. Lo corre la GitHub Action .github/workflows/pronosticos.yml cada
hora y publica el resultado en la rama "datos", que es lo que lee la app.

    python actualiza_pronosticos.py salida/
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import fuentes as F

EN_PARALELO = 3          # sitios a la vez: Open-Meteo a veces tarda ~1 min por sitio
PRESUPUESTO_S = 15 * 60  # pasado este tiempo se publica lo que haya (el job corta a los 30 min)


def main(carpeta):
    inicio = time.monotonic()
    por_sitio, pendientes = {}, list(F.SITIOS)

    def uno(s, exige):
        if time.monotonic() - inicio > PRESUPUESTO_S:
            return s, None, "sin tiempo"
        try:
            return s, F.pronostico_vivo(s["lat"], s["lon"], F.DIAS_PUBLICADOS, F.DIAS_PUBLICADOS,
                                        exige_ensamble=exige), None
        except F.OpenMeteoError as ex:
            return s, None, str(ex)

    # 1ª pasada exige el ensamble; la 2ª acepta quedarse solo con los 7 modelos
    for pasada, exige in ((1, True), (2, False)):
        if not pendientes:
            break
        if pasada == 2:
            time.sleep(60)
        with ThreadPoolExecutor(max_workers=EN_PARALELO) as pool:
            resultados = list(pool.map(lambda s: uno(s, exige), pendientes))
        pendientes = []
        for s, r, err in resultados:
            if r is None:
                pendientes.append(s)
                print(f"falla [{pasada}] {s['nombre']}: {err}")
            else:
                por_sitio[s["id"]] = r
                print(f"ok    [{pasada}] {s['nombre']}{' (sin ensamble)' if r['pp'] is None else ''}")

    if not por_sitio:
        sys.exit("Ningún sitio respondió; se mantiene la copia publicada anterior.")
    F.guarda_pronosticos(por_sitio, carpeta, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    faltan = ", ".join(s["nombre"] for s in pendientes)
    print(f"Guardado en {carpeta}: {len(por_sitio)} sitios en {time.monotonic() - inicio:.0f} s"
          + (f" (fallaron: {faltan})" if faltan else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "salida")
