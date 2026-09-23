"""
Baja de Open-Meteo los pronósticos de todos los sitios (7 modelos + super-ensamble,
DIAS_PUBLICADOS días hacia atrás y hacia adelante) y los guarda como parquet en la
carpeta indicada. Lo corre la GitHub Action .github/workflows/pronosticos.yml cada
hora y publica el resultado en la rama "datos", que es lo que lee la app.

    python actualiza_pronosticos.py salida/
"""
import sys
import time
from datetime import datetime, timezone

import fuentes as F


def main(carpeta):
    por_sitio, pendientes = {}, list(F.SITIOS)
    # 1ª pasada exige el ensamble; la 2ª, un par de minutos después, acepta quedarse solo con
    # los 7 modelos para los sitios cuyo ensamble siga sin responder
    for pasada, exige in ((1, True), (2, False)):
        if pasada == 2 and pendientes:
            time.sleep(90)
        fallas = []
        for s in pendientes:
            try:
                por_sitio[s["id"]] = F.pronostico_vivo(s["lat"], s["lon"], F.DIAS_PUBLICADOS,
                                                       F.DIAS_PUBLICADOS, exige_ensamble=exige)
                sin_ens = " (sin ensamble)" if por_sitio[s["id"]]["pp"] is None else ""
                print(f"ok    [{pasada}] {s['nombre']}{sin_ens}")
            except F.OpenMeteoError as ex:
                fallas.append(s)
                print(f"falla [{pasada}] {s['nombre']}: {ex}")
            time.sleep(1)  # sin apuro: se corre una vez por hora
        pendientes = fallas
    fallas = [s["nombre"] for s in pendientes]
    if not por_sitio:
        sys.exit("Ningún sitio respondió; se mantiene la copia publicada anterior.")
    F.guarda_pronosticos(por_sitio, carpeta, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(f"Guardado en {carpeta}: {len(por_sitio)} sitios" + (f" (fallaron: {', '.join(fallas)})" if fallas else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "salida")
