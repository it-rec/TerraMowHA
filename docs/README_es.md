# TerraMow para Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logotipo de TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · **Español** · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Esta es una integración de Home Assistant para los robots cortacésped TerraMow.

### Funciones

**Control**
- Entidad cortacésped: iniciar, pausar y volver a la base
- Siega por zonas: entidad de selección de zona y servicio `terramow.start_select_region`
- **Edición del programa** — los servicios `terramow.add_schedule` / `terramow.delete_schedule` escriben franjas de siega semanales en el robot y las verifican releyéndolas. *Nota:* el firmware comercial actual todavía no acepta escrituras del programa por MQTT local (la aplicación del fabricante usa Bluetooth/nube) — hasta que el firmware lo permita, usa el **blueprint de siega adaptada al tiempo** para programar desde HA
- **Tarjeta de mapa interactiva** — mapa vectorial del césped con desplazamiento y zoom para paneles: posición del robot en directo (teñida según la actividad, con modo de seguimiento), controles de inicio / pausa / base en la propia tarjeta, indicadores de batería / progreso / tiempo restante, sombreado de la superficie segada con progreso por zona, trayecto de siega, estación base, zonas con selección por toque para segar, zonas prohibidas y paredes virtuales, fallos activos marcados en su ubicación, y un **mapa de calor de Wi-Fi** del césped; un **botón de vista** alterna entre Ambos / Trayecto / Superficie / Wi-Fi. Compatible con temas, se registra sola y trae editor de interfaz (`custom:terramow-map-card`)
- Botón de siega de bordes
- Ajustes desde Home Assistant: altura de corte, velocidad, separación, velocidad de la cuchilla, distancia de corte de bordes, modo y ángulos de dirección principal, corte esmerado de esquinas, modo de siega de bordes para hierba alta
- Mantenimiento: botones de reinicio para los contadores del disco de cuchillas y de la estación base

**Supervisión**
- Cámara de mapa en directo con trayecto de siega, posición del robot y estación base (más una cámara de solo mapa, limpia, para paneles; resolución configurable en las opciones)
- Batería: nivel, estado de carga, estado de temperatura, cargador conectado, interruptor de alimentación
- Progreso: superficie de la sesión actual, progreso (%), duración y tipo de trabajo; tiempo de siega acumulado, número de trabajos y superficie segada
- Estado: misión / submisión / estado de misión, modo de funcionamiento, modo de energía, motivo del regreso a la base, detección de lluvia, indicador de problema, indicadores de guardado y conversión de datos
- **Sensor de fallo** — el fallo activo como texto legible (por ej. *Robot atascado*, *Robot levantado* u *OK*), para que una notificación o un asistente de voz pueda decir qué ocurre sin procesar un atributo con una plantilla
- Sensor de trabajo en curso (mantiene la misión activa a través de huecos en la señal de actividad) y un sensor de intensidad de señal Wi-Fi del robot
- Mapa: estado, superficie, indicadores de detectado / construible / copia de seguridad en curso
- Programa: sensor del próximo inicio programado y un **calendario del programa de siega** de solo lectura (la próxima siega aparece en la tarjeta de calendario)
- Entidad de actualización de firmware, versión del firmware en la página del dispositivo y sensor de compatibilidad de versión
- Todas las entidades se actualizan al instante con los envíos del dispositivo — sin retardo de sondeo

**Diagnósticos avanzados** (puntos de datos obtenidos por ingeniería inversa — en su mayoría en la categoría de entidad *Diagnóstico*, muchos desactivados por defecto; consulta las [notas sobre puntos de datos no oficiales](en/developers/data_point_unofficial.md))
- Errores y eventos: número de errores activos (con la lista de errores en bruto como atributo) y código del último evento. Los códigos de error conocidos se traducen a texto legible mediante un catálogo aportado por la comunidad (`error_codes.py`), que también decodifica el último código de error del robot (dp_115)
- Móvil / 4G: módem activado, intensidad de señal (RSRP / RSRQ), tipo de conexión y una lectura de *forzar red móvil*
- Entorno: amanecer / atardecer informados por el dispositivo, estado de luz diurna, calefacción antivaho, iluminación y aviso de meteorología extrema (con una URL informativa opcional)
- Seguridad y ajustes avanzados: estado de la detección de desniveles y de pendiente, umbral del sensor de lluvia, reanudación automática tras la lluvia y su retardo, y una lectura de *forzar una sola estación base*
- Modos de funcionamiento: cadenas de los modos movimiento / mapa / siega
- Cartografía y progreso: indicadores de guía para la cartografía manual (reposicionamiento / intervención necesarios, perímetro cerrado) y un porcentaje de progreso del guardado del mapa

**Eventos y automatización**
- **Entidad de evento del robot** — dispara un evento discreto en cada transición relevante (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), cada uno con los campos de misión en bruto, para que las automatizaciones reaccionen a *sucesos* sin sondear el estado de actividad
- Blueprints de automatización importables con un clic (ver más abajo)

**Comodidades de la integración**
- Detección automática mediante Zeroconf/mDNS
- Flujo de reconfiguración (cambiar host/IP sin volver a añadirla) y flujo de reautenticación
- **Avisos de reparación** — tarjetas de panel accionables para firmware incompatible y para el mantenimiento pendiente de la cuchilla / la estación base
- Descarga de diagnósticos para facilitar los informes de errores
- Traducida a 33 idiomas (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Órdenes confirmadas** — la siega por zonas espera la confirmación dp_119 del dispositivo e informa de los rechazos en lugar de «tener éxito» en silencio
- Comunicación local push basada en MQTT — sin necesidad de nube

### Entidades compatibles

| Plataforma | Entidades |
| --- | --- |
| Cortacésped | Control de inicio / pausa / base con actividad en directo |
| Cámara | Mapa con trayecto, robot y estación base; variante limpia de solo mapa |
| Sensor | Nivel de batería, estado de la batería, estado de temperatura de la batería, estado del mapa, superficie del mapa, altura de corte, velocidad de siega, modo de funcionamiento, posición, tiempo de siega / trabajos / superficie segada acumulados, superficie / progreso / duración / tipo de trabajo de la sesión actual, trabajo en curso, fallo, tiempo restante de la cuchilla y de la estación base, próximo inicio programado, compatibilidad de versión, estado de la dirección principal, modo de energía, motivo del regreso a la base, misión, submisión, estado de misión. *Diagnóstico:* errores activos, último evento, señal Wi-Fi, móvil RSRP / RSRQ / tipo, amanecer, atardecer, modos movimiento / mapa / siega, umbral del sensor de lluvia, retardo de reanudación tras la lluvia, progreso del guardado del mapa |
| Sensor binario | Cargando, navegación localizada, actualizando firmware, interruptor de alimentación, problema, lluvia detectada, mapa detectado / construible / copia de seguridad en curso, guardando datos, conversión de datos en curso. *Diagnóstico:* móvil activado, calefacción antivaho, iluminación, luz diurna, meteorología extrema, detección de desniveles / de pendiente, reanudación automática tras la lluvia, forzar una sola estación base, forzar red móvil, cartografía manual reposicionamiento / intervención / perímetro cerrado, indicador de estado 134 (sin decodificar) |
| Selección | Selección de zona, velocidad de siega, velocidad de la cuchilla, modo de dirección principal, modo de siega de bordes para hierba alta |
| Número | Altura de corte, distancia de corte de bordes, separación de siega, ángulo de dirección única, intervalo de rotación automática del ángulo, ángulo de la primera / segunda dirección |
| Interruptor | Corte esmerado de esquinas |
| Botón | Siega de bordes, reiniciar temporizador de la cuchilla, reiniciar temporizador de la estación base |
| Actualización | Versión del firmware |
| Evento | Evento del robot (siega iniciada / pausada / regresando / en la base / completada / error) |
| Calendario | Programa de siega (próxima siega programada) |

### Instalación

[![Abre tu instancia de Home Assistant y abre un repositorio en la Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Método 1: HACS (recomendado)
1. Asegúrate de que [HACS](https://hacs.xyz/) está instalado
2. Usa el botón de arriba para añadir la integración a HACS
3. Abre HACS, busca «TerraMow» y selecciona la integración
4. Instálala y reinicia Home Assistant

#### Método 2: Instalación manual
1. Copia la carpeta `custom_components/terramow` en la carpeta `/config/custom_components` de tu Home Assistant
2. Reinicia Home Assistant
3. Ve a Ajustes → Dispositivos y servicios → Añadir integración
4. Busca «TerraMow» y sigue los pasos de configuración

### Configuración

Los dispositivos de la red local se detectan automáticamente mediante Zeroconf — acepta el dispositivo detectado e introduce la contraseña MQTT. Para la configuración manual se requieren los siguientes parámetros:

- **Host**: dirección IP o nombre de host del dispositivo TerraMow
- **Contraseña**: contraseña MQTT para la autenticación

**Cambiar los ajustes más tarde**
- *Reconfigurar* (Ajustes → Dispositivos y servicios → TerraMow → Reconfigurar): cambia el host/IP o la contraseña en el sitio, por ej. después de que el robot reciba una nueva dirección DHCP — no hace falta eliminar y volver a añadir la integración.
- *Opciones* (Configurar):
  - **Resolución de salida del mapa** — mayor es más nítido, pero cuesta más ancho de banda y CPU en cada renderizado.
  - **Tema del mapa** — `light` o `dark`.
  - **Mostrar la superficie segada** — sombrea la zona ya segada bajo la línea del trayecto.
  - **Considerar todo trabajo finalizado como completado al 100 %** — algunos firmwares finalizan un trabajo sin emitir una señal de finalización, por lo que el progreso de la sesión nunca salta al 100 % aunque el césped esté acabado (se lee como «interrumpido»). Activa esta opción para tratar cualquier trabajo finalizado como completado, igual que la aplicación del fabricante; déjala desactivada para conservar el valor honesto del contador. *Por defecto: desactivado.*
- Si cambia la contraseña del dispositivo, Home Assistant inicia automáticamente un flujo de *reautenticación*.

### Requisitos

- Home Assistant 2024.6.0 o posterior (la CI valida contra la versión actual de HA Core)
- Firmware de TerraMow versión 6.6.0 o posterior
- Aplicación TerraMow versión 1.6.0 o posterior
- El mapa en directo y el trayecto de siega requieren la versión 3 del módulo HA del firmware; en la versión 2 (por ej. S800) todo lo demás funciona, y el sensor de compatibilidad de versión lo informa

### Dispositivos compatibles

Esta integración funciona con robots cortacésped TerraMow que exponen la interfaz MQTT/HTTP local — es decir, cualquier modelo con el firmware requerido. Se usa con la serie S de TerraMow, incluido el **S800** (que informa la versión 2 del módulo HA del firmware) y unidades más nuevas con la versión 3. Cualquier robot TerraMow con firmware 6.6.0+ y aplicación 1.6.0+ debería funcionar; el sensor de compatibilidad de versión y un aviso de reparación indican si el firmware de una unidad concreta es demasiado antiguo para una función determinada.

### Servicios

#### `terramow.start_select_region`

Inicia la siega de una lista de subregiones seleccionadas.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Crea o elimina una franja de siega semanal en el robot. Cada escritura se
confirma contra el dispositivo (confirmación dp_119 más una relectura del
programa).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` espera el `item_id` de la franja (se muestra como uid del
evento de calendario y se devuelve al añadir una franja).

> **Nota:** el firmware comercial actual todavía no acepta escrituras del
> programa por MQTT local (la aplicación del fabricante usa Bluetooth/nube).
> Hasta que el firmware lo permita, usa el **blueprint de siega adaptada al
> tiempo** para programar desde HA.

### Tarjeta de mapa interactiva

La integración incluye su propia tarjeta de Lovelace — registrada automáticamente, sin recursos manuales ni instalación aparte del frontend de HACS:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Dibuja el césped en vectores (nítido a cualquier zoom, sigue tu tema de HA): zonas, zonas prohibidas, paredes virtuales, el trayecto de siega, la estación base y la posición del robot en directo. Arrastra para desplazar, rueda o pinza para hacer zoom, doble toque para reajustar. **Toca una o varias zonas** y pulsa el botón que aparece para segar exactamente esas zonas (`terramow.start_select_region` por debajo).

Un **botón de vista** alterna lo que la tarjeta superpone al césped:

| Modo | Muestra |
| --- | --- |
| **Ambos** | la superficie segada *y* el trayecto de siega (predeterminado cuando la superficie está activada) |
| **Trayecto** | solo el trayecto del trabajo actual y del anterior |
| **Superficie** | solo el sombreado de la superficie segada, con progreso por zona |
| **Wi-Fi** | un **mapa de calor de Wi-Fi** del césped, medido por el propio robot mientras siega (verde = fuerte). Los huecos entre pasadas se interpolan a partir de las medidas vecinas; el terreno nunca recorrido queda vacío |

El modo elegido se recuerda por entidad en el navegador. Opciones y detalles: consulta la [guía de paneles](en/dashboard.md#interactive-map-card) (en inglés). Los datos de mapa en directo requieren la versión 3 del módulo HA del firmware (igual que la cámara de mapa). La tarjeta también está disponible en el selector de tarjetas del panel como **TerraMow Map Card**, con un editor de interfaz completo — sin necesidad de YAML.

### Ejemplo de panel

Una vista de Lovelace lista para usar (mapa en directo, controles, indicador de progreso, resumen de estado) junto con automatizaciones de notificación: consulta la [guía de paneles](en/dashboard.md) (en inglés).

### Blueprints de automatización

Blueprints importables con un clic para las notificaciones más habituales — cada uno solo pide la entidad TerraMow correspondiente y una acción de notificación:

- **Siega adaptada al tiempo** — inicia la siega según tu programa y la omite automáticamente si se detecta o se prevé lluvia
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Notificación de problema** — cuando el robot informa de un fallo
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Regreso por lluvia** — cuando el robot vuelve a la base por la lluvia
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Siega finalizada** — cuando se completa un trabajo de siega
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Usar la entidad de evento directamente** — la entidad de evento del robot es el desencadenante más flexible. Su atributo `event_type` es uno de `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, y lleva los campos en bruto `mission`, `sub_mission`, `state`, `back_to_station_reason` y `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow ha terminado de segar 🌱"
```

### Avisos de reparación

La integración genera avisos de reparación accionables en Home Assistant (Ajustes → Dispositivos y servicios → Reparaciones) en lugar de esconder los problemas en sensores:

- **Firmware incompatible / actualización necesaria** — el firmware es demasiado antiguo para la integración (o para una función concreta). Se deriva de la comprobación de compatibilidad de versión; desaparece cuando se anuncia un firmware compatible.
- **Mantenimiento de la cuchilla pendiente** — el disco de cuchillas ha alcanzado su intervalo de servicio recomendado de 240 horas. Limpia o sustituye las cuchillas y pulsa el botón *Reiniciar temporizador de la cuchilla* para borrarlo.
- **Mantenimiento de la estación base pendiente** — la estación base ha alcanzado su intervalo de servicio recomendado de 30 días. Límpiala y pulsa el botón *Reiniciar temporizador de la estación base* para borrarlo.

### Diagnósticos y solución de problemas

- **Descarga de diagnósticos**: Ajustes → Dispositivos y servicios → TerraMow → menú de tres puntos → *Descargar diagnósticos* genera una instantánea JSON depurada (estado del dispositivo, compatibilidad del firmware, cachés de puntos de datos en bruto) — adjúntala a los informes de errores.
- **Descubrir funciones no compatibles**: el robot publica más puntos de datos de los documentados. La primera carga útil de cada punto de datos desconocido se registra una vez en nivel INFO; activa el registro de depuración para la integración `terramow` para capturarlos todos. Si encuentras un punto de datos para una función que falta (por ej. alarma de elevación, interruptor de programa, códigos de error), compártelo en una issue.

### Cómo se actualizan los datos

TerraMow es una integración **local push**. El robot ejecuta un broker MQTT en el propio dispositivo; Home Assistant se conecta directamente a él por la red local (sin nube) y se suscribe a los temas de puntos de datos del dispositivo, de modo que los estados de las entidades se actualizan en el instante en que el robot informa de un cambio, y no en un intervalo de sondeo. Las cargas más grandes (el mapa, el trayecto en directo) se anuncian por MQTT y se descargan a demanda por HTTP local. Si el robot está en reposo o fuera de la red, la conexión se reintenta con retardo exponencial, y la entidad cortacésped expone la pérdida de conexión como su actividad `error`.

**Las órdenes fallan de forma visible, no en silencio.** Cuando envías una orden — `dock`, `start_mowing`, `pause`, siega de bordes, siega por zonas o cualquier cambio de ajuste — se publica con MQTT QoS 1 (así una reconexión breve la almacena en búfer en lugar de descartarla). Si el robot está desconectado o inaccesible, si el broker rechaza la publicación, o si una orden llega más rápido de lo que el dispositivo puede aceptarla, la llamada al servicio **falla con un error** en lugar de informar de un éxito silencioso. Así, una automatización que llama a `lawn_mower.dock` mientras el robot está inaccesible ve el fallo (y puede reintentar o notificar) en lugar de creer que el robot va de camino cuando nunca recibió la orden.

### Limitaciones conocidas

- **Sin acceso en la nube / remoto** — Home Assistant debe estar en la misma red local que el robot; no hay alternativa por la nube.
- **Funciones condicionadas por el firmware** — el mapa en directo y la vista del trayecto de siega requieren la versión 3 del módulo HA; en la versión 2 (por ej. el S800) todo lo demás funciona, y el sensor de compatibilidad / el aviso de reparación informa de la limitación.
- **Las actualizaciones de firmware** se realizan mediante la aplicación TerraMow, no desde Home Assistant; la entidad `update` del firmware es solo informativa.
- **El sensor de posición y la cámara de mapa limpia están desactivados por defecto** (el sensor de posición se actualiza a unos 2 Hz); actívalos en los ajustes de la entidad si los necesitas.
- **Muchas entidades de diagnóstico avanzado están desactivadas por defecto** y agrupadas en la categoría *Diagnóstico* (móvil, amanecer/atardecer, modos de funcionamiento, indicadores de cartografía manual, etc.); provienen de puntos de datos obtenidos por ingeniería inversa, así que activa solo los que necesites. Consulta las [notas sobre puntos de datos no oficiales](en/developers/data_point_unofficial.md).
- Algunos puntos de datos del dispositivo no están documentados; los desconocidos se registran una vez para ayudar a descubrir funciones que falten.

### Casos de uso

- **Notificaciones según la lluvia** — recibe un aviso cuando el robot vuelva a su base por la lluvia (ver los blueprints de arriba).
- **Alertas de fallo** — recibe un aviso en el momento en que el robot informa de un problema (atascado, levantado, bloqueado).
- **Siega por zonas desde automatizaciones** — llama a `terramow.start_select_region` para segar subregiones concretas según un programa o desde un botón del panel.
- **Recordatorios de mantenimiento** — los sensores de tiempo restante de la cuchilla / la estación base y los botones de reinicio permiten automatizar los recordatorios de mantenimiento.
- **Mapa en directo en un panel** — muestra la cámara de mapa con la posición del robot y el trayecto de siega (ver la guía de paneles).

### Idiomas

La integración está traducida a: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Notas de actualización

- **v0.5.0**: los valores de estado de las entidades pasaron de mayúsculas a minúsculas (por ej. `MISSION_IDLE` → `mission_idle`) para cumplir los requisitos de traducción de Home Assistant. Las automatizaciones o plantillas que comparen cadenas de estado en bruto necesitan una adaptación puntual; los nombres mostrados no cambian.

### Soporte

Abre una issue en [GitHub](https://github.com/it-rec/TerraMowHA/issues) para obtener ayuda.

### Información para desarrolladores

Para desarrolladores que quieran entender o ampliar esta integración (la documentación para desarrolladores está en inglés):

- [Guía de contribución](../CONTRIBUTING.md) — puesta en marcha, requisitos de calidad (100 % de cobertura, `mypy --strict`, traducciones), proceso de PR y de publicación
- [Arquitectura](ARCHITECTURE.md) — el funcionamiento interno: ciclo de vida del hub, modelo de ejecución, catálogo de puntos de datos, canalización de mapa/trayecto
- [Guía del desarrollador](en/developers.md) — el protocolo MQTT/HTTP del dispositivo tal como viaja por la red
- [Lo que este fork añade sobre el upstream](UPSTREAM_DELTA.md)

Para ejecutar la batería de pruebas en local:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licencia

Este proyecto está licenciado bajo la GNU General Public License v3.0 — consulta el archivo [LICENSE](../LICENSE) para más detalles.
