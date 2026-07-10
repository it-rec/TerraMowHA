# TerraMow para Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logotipo de TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · **Español** · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Esta es una integración de Home Assistant para los robots cortacésped TerraMow.

### Características

**Control**
- Entidad de cortacésped: iniciar, pausar y volver a la base
- Corte por zonas: entidad de selección de zona y servicio `terramow.start_select_region`
- **Schedule editing** — `terramow.add_schedule` / `terramow.delete_schedule` services write weekly mowing slots to the mower, confirmed against the device (acknowledgement + read-back); the calendar reflects changes immediately
- **Interactive map card** — pan/zoom vector lawn map for dashboards: live robot position (activity-tinted, with follow mode), on-card start / pause / dock controls, battery & job-progress chips, optional mowed-coverage shading, mowing path, base station, zones with tap-to-mow selection, forbidden areas and virtual walls; theme-aware, self-registering, with a UI editor (`custom:terramow-map-card`)
- Botón de corte de bordes
- Ajustes desde Home Assistant: altura de corte, velocidad, espaciado, velocidad de las cuchillas, distancia de corte de bordes, modo y ángulos de dirección principal, corte minucioso de esquinas, modo de corte de bordes con hierba alta
- Mantenimiento: botones de reinicio para los contadores del disco de cuchillas y de la estación base

**Supervisión**
- Cámara de mapa en vivo con la trayectoria de corte, la posición del robot y la estación base (además de una cámara limpia solo con el mapa para paneles, con resolución configurable mediante las opciones)
- Batería: nivel, estado de carga, estado de temperatura, cargador conectado, interruptor de alimentación
- Progreso del trabajo: área de la sesión actual, progreso (%), duración y tipo de trabajo; tiempo total de corte, número de trabajos y área cortada
- Estado: misión / submisión / estado de la misión, modo de funcionamiento, modo de energía, motivo del regreso a la estación, detección de lluvia, indicador de problemas, indicadores de guardado de datos y de conversión de datos
- Mapa: estado, área, indicadores de detectado / construible / copia de seguridad en curso
- Programación: próximo inicio programado
- Entidad de actualización de firmware, versión de firmware en la página del dispositivo y sensor de compatibilidad de versiones
- Todas las entidades se actualizan al instante con los envíos del dispositivo — sin retraso por sondeo

**Comodidades de la integración**
- Detección automática mediante Zeroconf/mDNS
- Flujo de reconfiguración (cambiar el host/IP sin volver a añadir la integración) y flujo de reautenticación
- Descarga de diagnósticos para facilitar los informes de errores
- Traducida a 33 idiomas (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Comunicación local de tipo push basada en MQTT — no se necesita la nube

### Entidades compatibles

| Plataforma | Entidades |
| --- | --- |
| Cortacésped | Control de iniciar / pausar / volver a la base con actividad en vivo |
| Cámara | Mapa con trayectoria, robot y estación base; variante limpia solo con el mapa |
| Sensor | Nivel de batería, estado de la batería, estado de temperatura de la batería, estado del mapa, área del mapa, altura de corte, velocidad de corte, modo de funcionamiento, posición, tiempo total de corte / trabajos / área cortada, área / progreso / duración / tipo de trabajo de la sesión actual, tiempo restante de las cuchillas y de la estación base, próximo inicio programado, compatibilidad de versiones, estado de la dirección principal, modo de energía, motivo del regreso a la estación, misión, submisión, estado de la misión |
| Sensor binario | Cargando, navegación localizada, actualización de firmware en curso, interruptor de alimentación, problema, lluvia detectada, mapa detectado / construible / copia de seguridad en curso, guardando datos, conversión de datos en curso |
| Selección | Selección de zona, velocidad de corte, velocidad de las cuchillas, modo de dirección principal, modo de corte de bordes con hierba alta |
| Número | Altura de corte, distancia de corte de bordes, espaciado de corte, ángulo de dirección única, intervalo de ángulo de rotación automática, ángulo de la primera / segunda dirección |
| Interruptor | Corte minucioso de esquinas |
| Botón | Corte de bordes, reiniciar el temporizador de las cuchillas, reiniciar el temporizador de la estación base |
| Actualización | Versión de firmware |

### Instalación

#### Método 1: HACS (recomendado)
1. Asegúrese de que [HACS](https://hacs.xyz/) esté instalado
2. Use el botón de arriba para añadir la integración a HACS
3. Vaya a HACS → Integraciones → + → Busque "TerraMow"
4. Instale y reinicie Home Assistant

#### Método 2: Instalación manual
1. Copie la carpeta `custom_components/terramow` en la carpeta `/config/custom_components` de su Home Assistant
2. Reinicie Home Assistant
3. Vaya a Ajustes → Dispositivos y servicios → Añadir integración
4. Busque "TerraMow" y siga los pasos de configuración

### Configuración

Los dispositivos de la red local se detectan automáticamente mediante Zeroconf — acepte el dispositivo detectado e introduzca la contraseña de MQTT. Para la configuración manual se necesitan los siguientes parámetros:

- **Host**: dirección IP o nombre de host del dispositivo TerraMow
- **Contraseña**: contraseña de MQTT para la autenticación

**Cambiar los ajustes más adelante**
- *Reconfigurar* (Ajustes → Dispositivos y servicios → TerraMow → Reconfigurar): cambie el host/IP o la contraseña directamente, por ejemplo después de que el cortacésped haya recibido una nueva dirección DHCP — no es necesario eliminar y volver a añadir la integración.
- *Opciones* (Configurar): establezca la resolución de salida de la cámara del mapa. Los valores más altos ofrecen una imagen más nítida en el panel a costa de más ancho de banda y CPU por renderizado.
- Si la contraseña del dispositivo cambia, Home Assistant inicia automáticamente un flujo de *reautenticación*.

### Requisitos

- Home Assistant 2024.6.0 o posterior (probado con 2025.1.1)
- Firmware de TerraMow versión 6.6.0 o posterior
- APP de TerraMow versión 1.6.0 o posterior
- El mapa en vivo y la trayectoria de corte requieren la versión 3 del módulo HA del firmware; con la versión 2 (p. ej. S800) todo lo demás funciona y el sensor de compatibilidad de versiones lo indica

### Servicios

#### `terramow.start_select_region`

Inicia el corte para una lista de subregiones seleccionadas.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Interactive map card

The integration ships its own Lovelace card — auto-registered, no manual resource or HACS frontend install needed:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

It renders the lawn as vectors (crisp at any zoom, follows your HA theme): zones, forbidden areas, virtual walls, the mowing path, the base station and the robot's live position. Drag to pan, scroll or pinch to zoom, double-tap to re-fit. **Tap one or more zones** and press the button that appears to mow exactly those zones (`terramow.start_select_region` under the hood). Options and details: see the [dashboard guide](en/dashboard.md#interactive-map-card). Live map data requires firmware HA module version 3 (same as the map camera). The card is also available in the dashboard card picker as **TerraMow Map Card**, with a full UI editor — no YAML needed.

### Diagnósticos y solución de problemas

- **Descarga de diagnósticos**: Ajustes → Dispositivos y servicios → TerraMow → menú de tres puntos → *Descargar diagnósticos* genera una instantánea JSON con los datos sensibles ocultos (estado del dispositivo, compatibilidad del firmware, cachés de puntos de datos sin procesar) — por favor, adjúntela a los informes de errores.
- **Descubrir funciones no compatibles**: el cortacésped publica más puntos de datos de los que están documentados. La primera carga útil de cada punto de datos desconocido se registra una sola vez en el nivel INFO; active el registro de depuración para la integración `terramow` para grabarlos todos. Si encuentra un punto de datos de una función que falta (p. ej. alarma de elevación, interruptor de programación, códigos de error), compártalo en un issue.

### Idiomas

La integración está traducida a: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Notas de actualización

- **v0.5.0**: los valores de estado de las entidades cambiaron de mayúsculas a minúsculas (p. ej. `MISSION_IDLE` → `mission_idle`) para cumplir los requisitos de traducción de Home Assistant. Las automatizaciones o plantillas que comparan cadenas de estado sin procesar necesitan una actualización única; los nombres mostrados no cambian.

### Soporte

Abra un issue en [GitHub](https://github.com/it-rec/TerraMowHA/issues) para obtener soporte.

### Información para desarrolladores

Los desarrolladores interesados en comprender o ampliar esta integración pueden consultar la [Guía del desarrollador](en/developers.md).

Para ejecutar la suite de pruebas localmente:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licencia

Este proyecto está licenciado bajo la GNU General Public License v3.0 — consulte el archivo [LICENSE](../LICENSE) para más detalles.
