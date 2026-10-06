# Cambios

Todos los cambios relevantes de MetGeo Concepción. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[versionado semántico](https://semver.org/lang/es/):

- **mayor** (2.0.0): cambios que rompen enlaces compartidos, quitan vistas o cambian de dónde salen los datos;
- **menor** (1.2.0): vistas, gráficos o funciones nuevas;
- **parche** (1.1.1): correcciones y ajustes que no agregan funciones.

Cómo publicar una versión: ver «Versiones» en el [README](README.md#versiones).

## [Sin publicar]

## [1.1.1] - 2026-10-05

### Corregido
- El mapa de la red en el Home cortaba las estaciones del extremo norte (Dichato) y sur (Santa Juana), y su
  leyenda (costa, ciudad, interior) tapaba las estaciones del borde inferior. Ahora el encuadre se calcula a
  partir de las coordenadas de las estaciones y la leyenda va debajo del mapa.
- Los mapas de Lluvia y de Mapa de estaciones usan el mismo encuadre calculado, así entran todas las
  estaciones con sus etiquetas, en vez de un centro y un zoom fijos.

### Cambiado
- Los mapas satelitales tienen esquinas redondeadas y un filete gris fino, igual en modo claro y oscuro; las
  descargas PNG/PDF de los mapas llevan ese mismo filete.
- La barra superior va sin el botón *Deploy* ni el menú ⋮: el modo claro u oscuro lo decide el navegador.

## [1.1.0] - 2026-10-05

### Agregado
- Descarga de cada gráfico en PNG (alta resolución) o PDF vectorial, con el logo de MetGeo.
- Modo oscuro: la app sigue el modo claro u oscuro del navegador, con logos claros para fondo oscuro y
  colores de gráficos y tarjetas ajustados a cada modo. Si el tema se cambia a mano (menú ⋮ → Settings), la
  página se vuelve a dibujar con los colores del modo elegido.
- Logos de MetGeo en SVG (vectoriales), en versión para fondo claro y para fondo oscuro.
- Número de versión al pie de la app, este registro de cambios y publicación automática de versiones en GitHub.

## [1.0.0] - 2026-09-25

Primera versión publicada.

### Agregado
- Vistas Home, Comparar modelos, Lluvia, Meteograma y Mapa de estaciones.
- Observaciones de 16 estaciones VIPNet (DGA/MOP) y del METAR de Carriel Sur.
- Pronósticos de 7 modelos globales y super-ensamble de 143 miembros (Open-Meteo), publicados cada hora por
  una GitHub Action.
- Verificación de modelos contra lo observado (sesgo, MAE, RMSE, correlación).
- Enlaces compartibles: sitio, días y variable quedan en la URL.

[Sin publicar]: https://github.com/Heszo/monitor-meteo-concepcion/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/Heszo/monitor-meteo-concepcion/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Heszo/monitor-meteo-concepcion/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Heszo/monitor-meteo-concepcion/releases/tag/v1.0.0
