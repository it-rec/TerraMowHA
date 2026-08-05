/**
 * TerraMow interactive map card.
 *
 * Vector map card for the TerraMow integration. Auto-registered by the
 * integration (no manual Lovelace resource needed). Subscribes to the
 * `terramow/map/subscribe` WebSocket feed for the structured scene
 * (regions, zones, forbidden areas, paths, station), the live robot
 * pose and job/battery status; renders everything on a layered canvas
 * with pan/zoom, contextual mow controls, and starts a zone mow via
 * `terramow.start_select_region` when zones are tapped.
 *
 * Usage (YAML):
 *   type: custom:terramow-map-card
 *   entity: lawn_mower.terramow
 *
 * Options:
 *   show_controls: true        # contextual start / pause / dock buttons
 *   show_coverage: false       # shade the mowed swath at cutting width
 *   show_wifi: false           # Wi-Fi heatmap overlay (self-sampled, green=strong)
 *   show_history_path: true    # faded, previously mowed path
 *   show_current_path: true    # path of the running job, incl. the track
 *                              # from before a mid-session recharge dock
 *   zone_selection: true       # tap (or arrow-key) zones to start a selective mow
 *   show_hud: true             # status chips (state, battery, progress)
 *   show_maintenance: true     # wrench button: blade / base-station counters
 *   show_markers: true         # trapped / maintenance / passage markers
 *   show_replay: true          # session replay scrubber button
 *   show_hotspots: true        # recorded fault locations
 *   show_direction: true       # mowing stripe-direction arrow per region
 *   zone_info: true            # long-press a zone for its mow settings
 *   show_layer_counts: false   # debug: list received layer counts in the legend
 *   rotate_gesture: true       # two-finger rotate the map (compass button resets)
 *   rotation: 0                # default map rotation (degrees); compass resets here
 *   fit_height: 420            # card canvas height in px
 *   fit_padding: 0.95          # fraction of the card the lawn fills on fit-to-view
 *
 * NOTE: registered as a classic "js" Lovelace resource, not an ES "module".
 * A "module" served from the browser cache is not re-executed, so the custom
 * element could stay undefined and the card showed a permanent "Configuration
 * error" (issue #140); see CARD_RESOURCE_TYPE in map_card.py. Even so, the
 * file is kept module-safe: it ships unbundled from a bare URL, so keep it
 * free of import/export (any specifier would 404) and strict-safe throughout,
 * and both element definitions must run at top-level evaluation. CI evaluates
 * it under the strict module goal via tests/frontend/eval_card_module.mjs.
 */

"use strict";

const CARD_TAG = "terramow-map-card";

/* ------------------------------------------------------------- strings */
/* The card's own labels, separate from the integration's translations/*.json
   (those name entities and the config flow). English is the source of truth
   and every other language must carry exactly the same keys: localize() falls
   back to English silently, so a missing key is invisible in the browser and
   only tests/frontend/eval_card_module.mjs catches it (issue #337). When a
   feature adds a label, add it to every language -- and reuse the wording
   from translations/<lang>.json wherever the same thing is already named
   there, so the card and the entity names do not drift apart. */
const STRINGS = {
  en: { no_map: "No map available yet", not_connected: "Waiting for mower data…", start: "Mow", clear: "Clear", zone: "zone", zones: "zones", reset_view: "Fit map to view", reset_rotation: "Reset to default rotation", follow: "Follow the mower", replay: "Replay this session", replay_play: "Play the replay", start_mowing: "Start mowing", pause: "Pause", hud_progress: "Progress", hud_eta_left: "left", dock: "Return to dock", sent: "Zone mowing started", preflight_none: "Not enough comparable history", preflight_estimate: "Estimate", preflight_battery: "battery", preflight_recharges: "recharges", preflight_daylight: "may finish after sunset", missing_entity: "Set a TerraMow lawn mower entity in the card config", zi_cut_height: "Cut height", zi_speed: "Mow speed", zi_spacing: "Stripe spacing", zi_blade: "Blade speed", zi_edge: "Edge cutting", zi_direction: "Direction", zi_order: "Mow order", zi_custom: "Custom settings", zi_global: "Global settings", lvl_low: "Low", lvl_medium: "Medium", lvl_high: "High", kbd_selected: "selected", legend: "Legend", legend_show: "Show legend", legend_hide: "Hide legend", lg_zone: "Mowing zone", lg_zone_pending: "Selected to mow", lg_mower: "Mower position", lg_dock: "Charging base", lg_order: "Mow order", lg_custom: "Custom zone settings", lg_direction: "Mow direction", lg_stuck: "Got stuck here", lg_hotspot: "Fault happened here (repeat count)", lg_maint: "Maintenance point", lg_passage: "Passage point", lg_nogo: "No-go zone", lg_wall: "Virtual wall", lg_coverage: "Mowed area", lg_wifi: "Wi-Fi signal (green = strong)", view_mode: "View", vw_beides: "Both", vw_weg: "Path", vw_flaeche: "Area", vw_wlan: "Wi-Fi", vw_saison: "Season", lg_season: "Times mowed (pale = rarely)", map_refreshing: "Map refreshing…", dbg_title: "Layers received", dbg_zones: "Zones", dbg_nogo: "No-go zones", dbg_walls: "Walls", dbg_obstacles: "Obstacles", dbg_passthrough: "Pass-through", dbg_required: "Required", dbg_tunnels: "Tunnels", dbg_markers: "Markers", dbg_draw: "Draw regions", dbg_paths: "Path points", maint: "Maintenance", maint_show: "Show maintenance", maint_hide: "Hide maintenance", maint_base: "Base station", maint_blade: "Blades", maint_reset: "Reset counter", maint_due: "due now", maint_reset_done: "Counter reset" },
  bg: { no_map: "Все още няма карта", not_connected: "Изчакване на данни от косачката…", start: "Коси", clear: "Изчисти", zone: "зона", zones: "зони", reset_view: "Побери картата", reset_rotation: "Връщане към стандартното завъртане", follow: "Следвай косачката", replay: "Възпроизведи тази сесия", replay_play: "Пусни възпроизвеждането", start_mowing: "Започни косене", pause: "Пауза", hud_progress: "Напредък", hud_eta_left: "остават", dock: "Върни към станцията", sent: "Косенето на зони започна", preflight_none: "Няма достатъчно сравними данни", preflight_estimate: "Оценка", preflight_battery: "батерия", preflight_recharges: "презареждания", preflight_daylight: "може да завърши след залез", missing_entity: "Задайте обект на косачка TerraMow в конфигурацията", zi_cut_height: "Височина на косене", zi_speed: "Скорост на косене", zi_spacing: "Разстояние между редовете", zi_blade: "Скорост на ножовете", zi_edge: "Косене на ръбовете", zi_direction: "Посока", zi_order: "Ред на косене", zi_custom: "Персонални настройки", zi_global: "Глобални настройки", lvl_low: "Ниска", lvl_medium: "Средна", lvl_high: "Висока", kbd_selected: "избрана", legend: "Легенда", legend_show: "Покажи легендата", legend_hide: "Скрий легендата", lg_zone: "Зона за косене", lg_zone_pending: "Избрана за косене", lg_mower: "Позиция на косачката", lg_dock: "Зарядна станция", lg_order: "Ред на косене", lg_custom: "Персонални настройки на зоната", lg_direction: "Посока на косене", lg_stuck: "Заседна тук", lg_hotspot: "Тук възникна повреда (брой)", lg_maint: "Точка за поддръжка", lg_passage: "Точка на проход", lg_nogo: "Забранена зона", lg_wall: "Виртуална стена", lg_coverage: "Окосена площ", lg_wifi: "Wi-Fi сигнал (зелено = силен)", view_mode: "Изглед", vw_beides: "И двете", vw_weg: "Път", vw_flaeche: "Площ", vw_wlan: "Wi-Fi", vw_saison: "Сезон", lg_season: "Брой косения (бледо = рядко)", map_refreshing: "Картата се обновява…", dbg_title: "Получени слоеве", dbg_zones: "Зони", dbg_nogo: "Забранени зони", dbg_walls: "Стени", dbg_obstacles: "Препятствия", dbg_passthrough: "Проходими зони", dbg_required: "Задължителни", dbg_tunnels: "Тунели", dbg_markers: "Маркери", dbg_draw: "Начертани зони", dbg_paths: "Точки от пътя", maint: "Поддръжка", maint_show: "Покажи поддръжката", maint_hide: "Скрий поддръжката", maint_base: "Базова станция", maint_blade: "Ножове", maint_reset: "Нулиране на брояча", maint_due: "предстои сега", maint_reset_done: "Броячът е нулиран" },
  ca: { no_map: "Encara no hi ha mapa", not_connected: "Esperant dades del tallagespa…", start: "Sega", clear: "Neteja", zone: "zona", zones: "zones", reset_view: "Ajusta el mapa", reset_rotation: "Restableix la rotació predeterminada", follow: "Segueix el tallagespa", replay: "Reprodueix aquesta sessió", replay_play: "Inicia la reproducció", start_mowing: "Comença a segar", pause: "Pausa", hud_progress: "Progrés", hud_eta_left: "restants", dock: "Torna a la base", sent: "Sega per zones iniciada", preflight_none: "No hi ha prou historial comparable", preflight_estimate: "Estimació", preflight_battery: "de bateria", preflight_recharges: "recàrregues", preflight_daylight: "pot acabar després de la posta de sol", missing_entity: "Configureu una entitat de tallagespa TerraMow", zi_cut_height: "Alçada de tall", zi_speed: "Velocitat de tall", zi_spacing: "Espaiat de les franges", zi_blade: "Velocitat de les fulles", zi_edge: "Tall de vores", zi_direction: "Direcció", zi_order: "Ordre de tall", zi_custom: "Configuració personalitzada", zi_global: "Configuració global", lvl_low: "Baixa", lvl_medium: "Mitjana", lvl_high: "Alta", kbd_selected: "seleccionada", legend: "Llegenda", legend_show: "Mostra la llegenda", legend_hide: "Amaga la llegenda", lg_zone: "Zona de tall", lg_zone_pending: "Seleccionada per tallar", lg_mower: "Posició del tallagespa", lg_dock: "Base de càrrega", lg_order: "Ordre de tall", lg_custom: "Configuració pròpia de la zona", lg_direction: "Direcció de tall", lg_stuck: "Es va encallar aquí", lg_hotspot: "Aquí hi va haver una avaria (repeticions)", lg_maint: "Punt de manteniment", lg_passage: "Punt de pas", lg_nogo: "Zona prohibida", lg_wall: "Paret virtual", lg_coverage: "Àrea tallada", lg_wifi: "Senyal Wi-Fi (verd = fort)", view_mode: "Vista", vw_beides: "Ambdós", vw_weg: "Trajecte", vw_flaeche: "Àrea", vw_wlan: "Wi-Fi", vw_saison: "Temporada", lg_season: "Vegades tallada (pàl·lid = poques)", map_refreshing: "S'està actualitzant el mapa…", dbg_title: "Capes rebudes", dbg_zones: "Zones", dbg_nogo: "Zones prohibides", dbg_walls: "Parets", dbg_obstacles: "Obstacles", dbg_passthrough: "Zones de pas", dbg_required: "Obligatòries", dbg_tunnels: "Túnels", dbg_markers: "Marcadors", dbg_draw: "Zones dibuixades", dbg_paths: "Punts del trajecte", maint: "Manteniment", maint_show: "Mostra el manteniment", maint_hide: "Amaga el manteniment", maint_base: "Estació base", maint_blade: "Fulles", maint_reset: "Restableix el comptador", maint_due: "cal fer-ho ara", maint_reset_done: "Comptador restablert" },
  cs: { no_map: "Mapa zatím není k dispozici", not_connected: "Čekání na data sekačky…", start: "Sekat", clear: "Vymazat", zone: "zóna", zones: "zóny", reset_view: "Přizpůsobit mapu", reset_rotation: "Obnovit výchozí otočení", follow: "Sledovat sekačku", replay: "Přehrát tuto relaci", replay_play: "Spustit přehrávání", start_mowing: "Zahájit sekání", pause: "Pozastavit", hud_progress: "Průběh", hud_eta_left: "zbývá", dock: "Zpět na stanici", sent: "Sekání zón zahájeno", preflight_none: "Nedostatek srovnatelné historie", preflight_estimate: "Odhad", preflight_battery: "baterie", preflight_recharges: "dobíjení", preflight_daylight: "může skončit po západu slunce", missing_entity: "Nastavte entitu sekačky TerraMow v konfiguraci karty", zi_cut_height: "Výška sečení", zi_speed: "Rychlost sečení", zi_spacing: "Rozestup pruhů", zi_blade: "Rychlost nožů", zi_edge: "Sečení okrajů", zi_direction: "Směr", zi_order: "Pořadí sečení", zi_custom: "Vlastní nastavení", zi_global: "Globální nastavení", lvl_low: "Nízká", lvl_medium: "Střední", lvl_high: "Vysoká", kbd_selected: "vybráno", legend: "Legenda", legend_show: "Zobrazit legendu", legend_hide: "Skrýt legendu", lg_zone: "Zóna sečení", lg_zone_pending: "Vybráno k sečení", lg_mower: "Poloha sekačky", lg_dock: "Nabíjecí stanice", lg_order: "Pořadí sečení", lg_custom: "Vlastní nastavení zóny", lg_direction: "Směr sečení", lg_stuck: "Zde uvízla", lg_hotspot: "Zde došlo k poruše (počet)", lg_maint: "Bod údržby", lg_passage: "Bod průchodu", lg_nogo: "Zakázaná zóna", lg_wall: "Virtuální stěna", lg_coverage: "Posečená plocha", lg_wifi: "Signál Wi-Fi (zelená = silný)", view_mode: "Zobrazení", vw_beides: "Obojí", vw_weg: "Trasa", vw_flaeche: "Plocha", vw_wlan: "Wi-Fi", vw_saison: "Sezóna", lg_season: "Počet sečení (světlé = zřídka)", map_refreshing: "Mapa se aktualizuje…", dbg_title: "Přijaté vrstvy", dbg_zones: "Zóny", dbg_nogo: "Zakázané zóny", dbg_walls: "Stěny", dbg_obstacles: "Překážky", dbg_passthrough: "Průjezdné zóny", dbg_required: "Povinné", dbg_tunnels: "Tunely", dbg_markers: "Značky", dbg_draw: "Nakreslené oblasti", dbg_paths: "Body trasy", maint: "Údržba", maint_show: "Zobrazit údržbu", maint_hide: "Skrýt údržbu", maint_base: "Nabíjecí stanice", maint_blade: "Nože", maint_reset: "Vynulovat počítadlo", maint_due: "nutná nyní", maint_reset_done: "Počítadlo vynulováno" },
  da: { no_map: "Intet kort tilgængeligt endnu", not_connected: "Venter på data fra plæneklipperen…", start: "Klip", clear: "Ryd", zone: "zone", zones: "zoner", reset_view: "Tilpas kortet", reset_rotation: "Nulstil til standardrotation", follow: "Følg plæneklipperen", replay: "Afspil denne session", replay_play: "Start afspilningen", start_mowing: "Start klipning", pause: "Pause", hud_progress: "Fremskridt", hud_eta_left: "tilbage", dock: "Kør til base", sent: "Zoneklipning startet", preflight_none: "Ikke nok sammenlignelig historik", preflight_estimate: "Estimat", preflight_battery: "batteri", preflight_recharges: "opladninger", preflight_daylight: "bliver måske først færdig efter solnedgang", missing_entity: "Angiv en TerraMow-plæneklipperentitet i kortets konfiguration", zi_cut_height: "Klippehøjde", zi_speed: "Klippehastighed", zi_spacing: "Baneafstand", zi_blade: "Knivhastighed", zi_edge: "Kantklipning", zi_direction: "Retning", zi_order: "Klipperækkefølge", zi_custom: "Egne indstillinger", zi_global: "Globale indstillinger", lvl_low: "Lav", lvl_medium: "Middel", lvl_high: "Høj", kbd_selected: "valgt", legend: "Forklaring", legend_show: "Vis forklaring", legend_hide: "Skjul forklaring", lg_zone: "Klippezone", lg_zone_pending: "Valgt til klipning", lg_mower: "Plæneklipperens position", lg_dock: "Ladestation", lg_order: "Klipperækkefølge", lg_custom: "Egne zoneindstillinger", lg_direction: "Klipperetning", lg_stuck: "Sad fast her", lg_hotspot: "Fejl opstod her (antal)", lg_maint: "Vedligeholdelsespunkt", lg_passage: "Passagepunkt", lg_nogo: "Forbudt zone", lg_wall: "Virtuel væg", lg_coverage: "Klippet areal", lg_wifi: "Wi-Fi-signal (grøn = stærkt)", view_mode: "Visning", vw_beides: "Begge", vw_weg: "Rute", vw_flaeche: "Areal", vw_wlan: "Wi-Fi", vw_saison: "Sæson", lg_season: "Antal klipninger (bleg = sjældent)", map_refreshing: "Kortet opdateres…", dbg_title: "Modtagne lag", dbg_zones: "Zoner", dbg_nogo: "Forbudte zoner", dbg_walls: "Vægge", dbg_obstacles: "Forhindringer", dbg_passthrough: "Gennemkørsel", dbg_required: "Påkrævede", dbg_tunnels: "Tunneler", dbg_markers: "Markører", dbg_draw: "Tegnede områder", dbg_paths: "Rutepunkter", maint: "Vedligeholdelse", maint_show: "Vis vedligeholdelse", maint_hide: "Skjul vedligeholdelse", maint_base: "Basestation", maint_blade: "Knive", maint_reset: "Nulstil tæller", maint_due: "forfalden nu", maint_reset_done: "Tæller nulstillet" },
  de: { no_map: "Noch keine Karte verfügbar", not_connected: "Warte auf Mäherdaten…", start: "Mähen", clear: "Leeren", zone: "Zone", zones: "Zonen", reset_view: "Karte einpassen", reset_rotation: "Auf Standarddrehung zurücksetzen", follow: "Dem Mäher folgen", replay: "Diese Sitzung abspielen", replay_play: "Wiedergabe starten", start_mowing: "Mähen starten", pause: "Pausieren", hud_progress: "Fortschritt", hud_eta_left: "übrig", dock: "Zur Station", sent: "Zonenmähen gestartet", preflight_none: "Zu wenig vergleichbare Historie", preflight_estimate: "Schätzung", preflight_battery: "Akku", preflight_recharges: "Ladepausen", preflight_daylight: "endet evtl. nach Sonnenuntergang", missing_entity: "TerraMow-Mäher-Entität in der Kartenkonfiguration setzen", zi_cut_height: "Schnitthöhe", zi_speed: "Mähgeschwindigkeit", zi_spacing: "Bahnabstand", zi_blade: "Messerdrehzahl", zi_edge: "Kantenschnitt", zi_direction: "Richtung", zi_order: "Mähreihenfolge", zi_custom: "Eigene Einstellungen", zi_global: "Globale Einstellungen", lvl_low: "Niedrig", lvl_medium: "Mittel", lvl_high: "Hoch", kbd_selected: "ausgewählt", legend: "Legende", legend_show: "Legende anzeigen", legend_hide: "Legende ausblenden", lg_zone: "Rasenmähzone", lg_zone_pending: "Zum Mähen ausgewählt", lg_mower: "Mäherposition", lg_dock: "Ladestation", lg_order: "Mähreihenfolge", lg_custom: "Eigene Zoneneinstellungen", lg_direction: "Mährichtung", lg_stuck: "Hier steckengeblieben", lg_hotspot: "Hier trat eine Störung auf (Anzahl)", lg_maint: "Wartungspunkt", lg_passage: "Durchgangspunkt", lg_nogo: "Sperrzone", lg_wall: "Virtuelle Wand", lg_coverage: "Gemähte Fläche", lg_wifi: "WLAN-Signal (grün = stark)", view_mode: "Ansicht", vw_beides: "Beides", vw_weg: "Weg", vw_flaeche: "Fläche", vw_wlan: "WLAN", vw_saison: "Saison", lg_season: "Mähhäufigkeit (blass = selten)", map_refreshing: "Karte wird aktualisiert…", dbg_title: "Empfangene Ebenen", dbg_zones: "Zonen", dbg_nogo: "Sperrzonen", dbg_walls: "Wände", dbg_obstacles: "Hindernisse", dbg_passthrough: "Durchgänge", dbg_required: "Pflichtzonen", dbg_tunnels: "Tunnel", dbg_markers: "Markierungen", dbg_draw: "Zeichenregionen", dbg_paths: "Pfadpunkte", maint: "Wartung", maint_show: "Wartung anzeigen", maint_hide: "Wartung ausblenden", maint_base: "Basisstation", maint_blade: "Klingen", maint_reset: "Zähler zurücksetzen", maint_due: "jetzt fällig", maint_reset_done: "Zähler zurückgesetzt" },
  el: { no_map: "Δεν υπάρχει ακόμη χάρτης", not_connected: "Αναμονή δεδομένων χλοοκοπτικού…", start: "Κούρεμα", clear: "Καθαρισμός", zone: "ζώνη", zones: "ζώνες", reset_view: "Προσαρμογή χάρτη", reset_rotation: "Επαναφορά προεπιλεγμένης περιστροφής", follow: "Ακολούθησε το χλοοκοπτικό", replay: "Αναπαραγωγή αυτής της συνεδρίας", replay_play: "Έναρξη αναπαραγωγής", start_mowing: "Έναρξη κουρέματος", pause: "Παύση", hud_progress: "Πρόοδος", hud_eta_left: "απομένουν", dock: "Επιστροφή στη βάση", sent: "Το κούρεμα ζωνών ξεκίνησε", preflight_none: "Δεν υπάρχει αρκετό συγκρίσιμο ιστορικό", preflight_estimate: "Εκτίμηση", preflight_battery: "μπαταρία", preflight_recharges: "επαναφορτίσεις", preflight_daylight: "μπορεί να τελειώσει μετά τη δύση", missing_entity: "Ορίστε οντότητα χλοοκοπτικού TerraMow στη διαμόρφωση", zi_cut_height: "Ύψος κοπής", zi_speed: "Ταχύτητα κοπής", zi_spacing: "Απόσταση λωρίδων", zi_blade: "Ταχύτητα λεπίδων", zi_edge: "Κοπή άκρων", zi_direction: "Κατεύθυνση", zi_order: "Σειρά κοπής", zi_custom: "Προσαρμοσμένες ρυθμίσεις", zi_global: "Γενικές ρυθμίσεις", lvl_low: "Χαμηλή", lvl_medium: "Μεσαία", lvl_high: "Υψηλή", kbd_selected: "επιλεγμένη", legend: "Υπόμνημα", legend_show: "Εμφάνιση υπομνήματος", legend_hide: "Απόκρυψη υπομνήματος", lg_zone: "Ζώνη κοπής", lg_zone_pending: "Επιλεγμένη για κοπή", lg_mower: "Θέση χλοοκοπτικού", lg_dock: "Βάση φόρτισης", lg_order: "Σειρά κοπής", lg_custom: "Προσαρμοσμένες ρυθμίσεις ζώνης", lg_direction: "Κατεύθυνση κοπής", lg_stuck: "Κόλλησε εδώ", lg_hotspot: "Εδώ συνέβη σφάλμα (πλήθος)", lg_maint: "Σημείο συντήρησης", lg_passage: "Σημείο διέλευσης", lg_nogo: "Απαγορευμένη ζώνη", lg_wall: "Εικονικός τοίχος", lg_coverage: "Κομμένη επιφάνεια", lg_wifi: "Σήμα Wi-Fi (πράσινο = ισχυρό)", view_mode: "Προβολή", vw_beides: "Και τα δύο", vw_weg: "Διαδρομή", vw_flaeche: "Επιφάνεια", vw_wlan: "Wi-Fi", vw_saison: "Σεζόν", lg_season: "Φορές κοπής (ανοιχτό = σπάνια)", map_refreshing: "Ο χάρτης ανανεώνεται…", dbg_title: "Ληφθέντα επίπεδα", dbg_zones: "Ζώνες", dbg_nogo: "Απαγορευμένες ζώνες", dbg_walls: "Τοίχοι", dbg_obstacles: "Εμπόδια", dbg_passthrough: "Ζώνες διέλευσης", dbg_required: "Υποχρεωτικές", dbg_tunnels: "Σήραγγες", dbg_markers: "Δείκτες", dbg_draw: "Σχεδιασμένες περιοχές", dbg_paths: "Σημεία διαδρομής", maint: "Συντήρηση", maint_show: "Εμφάνιση συντήρησης", maint_hide: "Απόκρυψη συντήρησης", maint_base: "Σταθμός βάσης", maint_blade: "Λεπίδες", maint_reset: "Μηδενισμός μετρητή", maint_due: "απαιτείται τώρα", maint_reset_done: "Ο μετρητής μηδενίστηκε" },
  es: { no_map: "Aún no hay mapa disponible", not_connected: "Esperando datos del cortacésped…", start: "Cortar", clear: "Borrar", zone: "zona", zones: "zonas", reset_view: "Ajustar mapa", reset_rotation: "Restablecer la rotación predeterminada", follow: "Seguir al cortacésped", replay: "Reproducir esta sesión", replay_play: "Iniciar la reproducción", start_mowing: "Iniciar corte", pause: "Pausar", hud_progress: "Progreso", hud_eta_left: "restantes", dock: "Volver a la base", sent: "Corte por zonas iniciado", preflight_none: "No hay suficiente historial comparable", preflight_estimate: "Estimación", preflight_battery: "de batería", preflight_recharges: "recargas", preflight_daylight: "puede terminar después del atardecer", missing_entity: "Configura la entidad del cortacésped TerraMow", zi_cut_height: "Altura de corte", zi_speed: "Velocidad de corte", zi_spacing: "Espaciado de franjas", zi_blade: "Velocidad de cuchillas", zi_edge: "Corte de bordes", zi_direction: "Dirección", zi_order: "Orden de corte", zi_custom: "Ajustes personalizados", zi_global: "Ajustes globales", lvl_low: "Baja", lvl_medium: "Media", lvl_high: "Alta", kbd_selected: "seleccionada", legend: "Leyenda", legend_show: "Mostrar leyenda", legend_hide: "Ocultar leyenda", lg_zone: "Zona de corte", lg_zone_pending: "Seleccionada para cortar", lg_mower: "Posición del cortacésped", lg_dock: "Base de carga", lg_order: "Orden de corte", lg_custom: "Ajustes propios de la zona", lg_direction: "Dirección de corte", lg_stuck: "Se atascó aquí", lg_hotspot: "Aquí ocurrió un fallo (repeticiones)", lg_maint: "Punto de mantenimiento", lg_passage: "Punto de paso", lg_nogo: "Zona prohibida", lg_wall: "Pared virtual", lg_coverage: "Área cortada", lg_wifi: "Señal Wi-Fi (verde = fuerte)", view_mode: "Vista", vw_beides: "Ambos", vw_weg: "Ruta", vw_flaeche: "Área", vw_wlan: "Wi-Fi", vw_saison: "Temporada", lg_season: "Veces cortada (pálido = pocas)", map_refreshing: "Actualizando el mapa…", dbg_title: "Capas recibidas", dbg_zones: "Zonas", dbg_nogo: "Zonas prohibidas", dbg_walls: "Paredes", dbg_obstacles: "Obstáculos", dbg_passthrough: "Zonas de paso", dbg_required: "Obligatorias", dbg_tunnels: "Túneles", dbg_markers: "Marcadores", dbg_draw: "Zonas dibujadas", dbg_paths: "Puntos de ruta", maint: "Mantenimiento", maint_show: "Mostrar mantenimiento", maint_hide: "Ocultar mantenimiento", maint_base: "Estación base", maint_blade: "Cuchillas", maint_reset: "Restablecer contador", maint_due: "pendiente ahora", maint_reset_done: "Contador restablecido" },
  et: { no_map: "Kaarti pole veel saadaval", not_connected: "Ootan niiduki andmeid…", start: "Niida", clear: "Tühjenda", zone: "tsoon", zones: "tsooni", reset_view: "Mahuta kaart", reset_rotation: "Taasta vaikimisi pööre", follow: "Jälgi niidukit", replay: "Esita see seanss uuesti", replay_play: "Käivita taasesitus", start_mowing: "Alusta niitmist", pause: "Paus", hud_progress: "Edenemine", hud_eta_left: "jäänud", dock: "Tagasi baasi", sent: "Tsooniniitmine alustatud", preflight_none: "Võrreldavat ajalugu on liiga vähe", preflight_estimate: "Hinnang", preflight_battery: "akut", preflight_recharges: "laadimispausi", preflight_daylight: "võib lõppeda pärast päikeseloojangut", missing_entity: "Määra kaardi seadetes TerraMow niiduki olem", zi_cut_height: "Niitmiskõrgus", zi_speed: "Niitmiskiirus", zi_spacing: "Ribade vahe", zi_blade: "Terade kiirus", zi_edge: "Servade niitmine", zi_direction: "Suund", zi_order: "Niitmisjärjekord", zi_custom: "Kohandatud seaded", zi_global: "Üldised seaded", lvl_low: "Väike", lvl_medium: "Keskmine", lvl_high: "Suur", kbd_selected: "valitud", legend: "Legend", legend_show: "Näita legendi", legend_hide: "Peida legend", lg_zone: "Niitmistsoon", lg_zone_pending: "Valitud niitmiseks", lg_mower: "Niiduki asukoht", lg_dock: "Laadimisjaam", lg_order: "Niitmisjärjekord", lg_custom: "Tsooni kohandatud seaded", lg_direction: "Niitmissuund", lg_stuck: "Jäi siia kinni", lg_hotspot: "Siin tekkis tõrge (korduste arv)", lg_maint: "Hoolduspunkt", lg_passage: "Läbipääsupunkt", lg_nogo: "Keelutsoon", lg_wall: "Virtuaalne sein", lg_coverage: "Niidetud ala", lg_wifi: "Wi-Fi signaal (roheline = tugev)", view_mode: "Vaade", vw_beides: "Mõlemad", vw_weg: "Rada", vw_flaeche: "Pindala", vw_wlan: "Wi-Fi", vw_saison: "Hooaeg", lg_season: "Niitmiskordi (hele = harva)", map_refreshing: "Kaarti värskendatakse…", dbg_title: "Saadud kihid", dbg_zones: "Tsoonid", dbg_nogo: "Keelutsoonid", dbg_walls: "Seinad", dbg_obstacles: "Takistused", dbg_passthrough: "Läbipääsualad", dbg_required: "Kohustuslikud", dbg_tunnels: "Tunnelid", dbg_markers: "Märgised", dbg_draw: "Joonistatud alad", dbg_paths: "Rajapunktid", maint: "Hooldus", maint_show: "Näita hooldust", maint_hide: "Peida hooldus", maint_base: "Baasjaam", maint_blade: "Terad", maint_reset: "Lähtesta loendur", maint_due: "kohe vajalik", maint_reset_done: "Loendur lähtestatud" },
  fi: { no_map: "Karttaa ei vielä saatavilla", not_connected: "Odotetaan leikkurin tietoja…", start: "Leikkaa", clear: "Tyhjennä", zone: "vyöhyke", zones: "vyöhykettä", reset_view: "Sovita kartta", reset_rotation: "Palauta oletuskierto", follow: "Seuraa leikkuria", replay: "Toista tämä istunto", replay_play: "Käynnistä toisto", start_mowing: "Aloita leikkuu", pause: "Tauko", hud_progress: "Edistyminen", hud_eta_left: "jäljellä", dock: "Palaa asemalle", sent: "Vyöhykeleikkuu aloitettu", preflight_none: "Vertailukelpoista historiaa ei ole tarpeeksi", preflight_estimate: "Arvio", preflight_battery: "akkua", preflight_recharges: "latauskertaa", preflight_daylight: "voi päättyä auringonlaskun jälkeen", missing_entity: "Aseta TerraMow-leikkurientiteetti kortin asetuksissa", zi_cut_height: "Leikkuukorkeus", zi_speed: "Leikkuunopeus", zi_spacing: "Kaistojen väli", zi_blade: "Terien nopeus", zi_edge: "Reunaleikkuu", zi_direction: "Suunta", zi_order: "Leikkuujärjestys", zi_custom: "Omat asetukset", zi_global: "Yleiset asetukset", lvl_low: "Hidas", lvl_medium: "Keskitaso", lvl_high: "Nopea", kbd_selected: "valittu", legend: "Selite", legend_show: "Näytä selite", legend_hide: "Piilota selite", lg_zone: "Leikkuuvyöhyke", lg_zone_pending: "Valittu leikattavaksi", lg_mower: "Leikkurin sijainti", lg_dock: "Latausasema", lg_order: "Leikkuujärjestys", lg_custom: "Vyöhykkeen omat asetukset", lg_direction: "Leikkuusuunta", lg_stuck: "Juuttui tähän", lg_hotspot: "Täällä tapahtui vika (toistot)", lg_maint: "Huoltopiste", lg_passage: "Kulkupiste", lg_nogo: "Kielletty alue", lg_wall: "Virtuaaliseinä", lg_coverage: "Leikattu alue", lg_wifi: "Wi-Fi-signaali (vihreä = vahva)", view_mode: "Näkymä", vw_beides: "Molemmat", vw_weg: "Reitti", vw_flaeche: "Pinta-ala", vw_wlan: "Wi-Fi", vw_saison: "Kausi", lg_season: "Leikkuukertoja (vaalea = harvoin)", map_refreshing: "Karttaa päivitetään…", dbg_title: "Vastaanotetut tasot", dbg_zones: "Vyöhykkeet", dbg_nogo: "Kielletyt alueet", dbg_walls: "Seinät", dbg_obstacles: "Esteet", dbg_passthrough: "Kulkualueet", dbg_required: "Pakolliset", dbg_tunnels: "Tunnelit", dbg_markers: "Merkinnät", dbg_draw: "Piirretyt alueet", dbg_paths: "Reittipisteet", maint: "Huolto", maint_show: "Näytä huolto", maint_hide: "Piilota huolto", maint_base: "Latausasema", maint_blade: "Terät", maint_reset: "Nollaa laskuri", maint_due: "nyt ajankohtainen", maint_reset_done: "Laskuri nollattu" },
  fr: { no_map: "Aucune carte disponible", not_connected: "En attente des données de la tondeuse…", start: "Tondre", clear: "Effacer", zone: "zone", zones: "zones", reset_view: "Ajuster la carte", reset_rotation: "Rétablir la rotation par défaut", follow: "Suivre la tondeuse", replay: "Rejouer cette session", replay_play: "Lancer la lecture", start_mowing: "Démarrer la tonte", pause: "Pause", hud_progress: "Progression", hud_eta_left: "restantes", dock: "Retour à la base", sent: "Tonte de zone démarrée", preflight_none: "Pas assez d'historique comparable", preflight_estimate: "Estimation", preflight_battery: "de batterie", preflight_recharges: "recharges", preflight_daylight: "peut se terminer après le coucher du soleil", missing_entity: "Définissez l'entité tondeuse TerraMow dans la configuration", zi_cut_height: "Hauteur de coupe", zi_speed: "Vitesse de tonte", zi_spacing: "Espacement des bandes", zi_blade: "Vitesse des lames", zi_edge: "Coupe des bordures", zi_direction: "Direction", zi_order: "Ordre de tonte", zi_custom: "Réglages personnalisés", zi_global: "Réglages globaux", lvl_low: "Lente", lvl_medium: "Moyenne", lvl_high: "Rapide", kbd_selected: "sélectionnée", legend: "Légende", legend_show: "Afficher la légende", legend_hide: "Masquer la légende", lg_zone: "Zone de tonte", lg_zone_pending: "Sélectionnée pour la tonte", lg_mower: "Position de la tondeuse", lg_dock: "Base de charge", lg_order: "Ordre de tonte", lg_custom: "Réglages propres à la zone", lg_direction: "Direction de tonte", lg_stuck: "Bloquée ici", lg_hotspot: "Une panne s'est produite ici (occurrences)", lg_maint: "Point d'entretien", lg_passage: "Point de passage", lg_nogo: "Zone interdite", lg_wall: "Mur virtuel", lg_coverage: "Surface tondue", lg_wifi: "Signal Wi-Fi (vert = fort)", view_mode: "Affichage", vw_beides: "Les deux", vw_weg: "Trajet", vw_flaeche: "Surface", vw_wlan: "Wi-Fi", vw_saison: "Saison", lg_season: "Nombre de tontes (pâle = rare)", map_refreshing: "Actualisation de la carte…", dbg_title: "Couches reçues", dbg_zones: "Zones", dbg_nogo: "Zones interdites", dbg_walls: "Murs", dbg_obstacles: "Obstacles", dbg_passthrough: "Zones de passage", dbg_required: "Obligatoires", dbg_tunnels: "Tunnels", dbg_markers: "Marqueurs", dbg_draw: "Zones dessinées", dbg_paths: "Points de trajet", maint: "Entretien", maint_show: "Afficher l'entretien", maint_hide: "Masquer l'entretien", maint_base: "Station de base", maint_blade: "Lames", maint_reset: "Réinitialiser le compteur", maint_due: "à faire maintenant", maint_reset_done: "Compteur réinitialisé" },
  hr: { no_map: "Karta još nije dostupna", not_connected: "Čekanje podataka kosilice…", start: "Kosi", clear: "Očisti", zone: "zona", zones: "zone", reset_view: "Prilagodi kartu", reset_rotation: "Vrati zadanu rotaciju", follow: "Prati kosilicu", replay: "Reproduciraj ovu sesiju", replay_play: "Pokreni reprodukciju", start_mowing: "Pokreni košnju", pause: "Pauza", hud_progress: "Napredak", hud_eta_left: "preostalo", dock: "Povratak na stanicu", sent: "Košnja zona pokrenuta", preflight_none: "Nema dovoljno usporedive povijesti", preflight_estimate: "Procjena", preflight_battery: "baterije", preflight_recharges: "punjenja", preflight_daylight: "može završiti nakon zalaska sunca", missing_entity: "Postavite entitet TerraMow kosilice u konfiguraciji kartice", zi_cut_height: "Visina košnje", zi_speed: "Brzina košnje", zi_spacing: "Razmak traka", zi_blade: "Brzina noževa", zi_edge: "Košnja rubova", zi_direction: "Smjer", zi_order: "Redoslijed košnje", zi_custom: "Prilagođene postavke", zi_global: "Globalne postavke", lvl_low: "Niska", lvl_medium: "Srednja", lvl_high: "Visoka", kbd_selected: "odabrano", legend: "Legenda", legend_show: "Prikaži legendu", legend_hide: "Sakrij legendu", lg_zone: "Zona košnje", lg_zone_pending: "Odabrano za košnju", lg_mower: "Položaj kosilice", lg_dock: "Stanica za punjenje", lg_order: "Redoslijed košnje", lg_custom: "Prilagođene postavke zone", lg_direction: "Smjer košnje", lg_stuck: "Ovdje se zaglavila", lg_hotspot: "Ovdje je došlo do kvara (broj)", lg_maint: "Točka održavanja", lg_passage: "Točka prolaza", lg_nogo: "Zabranjena zona", lg_wall: "Virtualni zid", lg_coverage: "Pokošena površina", lg_wifi: "Wi-Fi signal (zeleno = jak)", view_mode: "Prikaz", vw_beides: "Oboje", vw_weg: "Putanja", vw_flaeche: "Površina", vw_wlan: "Wi-Fi", vw_saison: "Sezona", lg_season: "Broj košnji (blijedo = rijetko)", map_refreshing: "Karta se osvježava…", dbg_title: "Primljeni slojevi", dbg_zones: "Zone", dbg_nogo: "Zabranjene zone", dbg_walls: "Zidovi", dbg_obstacles: "Prepreke", dbg_passthrough: "Prolazne zone", dbg_required: "Obavezne", dbg_tunnels: "Tuneli", dbg_markers: "Oznake", dbg_draw: "Nacrtane zone", dbg_paths: "Točke putanje", maint: "Održavanje", maint_show: "Prikaži održavanje", maint_hide: "Sakrij održavanje", maint_base: "Bazna stanica", maint_blade: "Noževi", maint_reset: "Poništi brojač", maint_due: "potrebno sada", maint_reset_done: "Brojač poništen" },
  hu: { no_map: "Még nincs elérhető térkép", not_connected: "Várakozás a fűnyíró adataira…", start: "Nyírás", clear: "Törlés", zone: "zóna", zones: "zóna", reset_view: "Térkép igazítása", reset_rotation: "Alapértelmezett forgatás visszaállítása", follow: "Fűnyíró követése", replay: "Munkamenet visszajátszása", replay_play: "Visszajátszás indítása", start_mowing: "Nyírás indítása", pause: "Szünet", hud_progress: "Előrehaladás", hud_eta_left: "van hátra", dock: "Vissza a dokkolóba", sent: "Zónanyírás elindítva", preflight_none: "Nincs elég összehasonlítható előzmény", preflight_estimate: "Becslés", preflight_battery: "akkumulátor", preflight_recharges: "töltés", preflight_daylight: "napnyugta után érhet véget", missing_entity: "Állítson be TerraMow fűnyíró entitást a kártya beállításaiban", zi_cut_height: "Nyírási magasság", zi_speed: "Nyírási sebesség", zi_spacing: "Sávtávolság", zi_blade: "Késsebesség", zi_edge: "Szegélyvágás", zi_direction: "Irány", zi_order: "Nyírási sorrend", zi_custom: "Egyéni beállítások", zi_global: "Globális beállítások", lvl_low: "Alacsony", lvl_medium: "Közepes", lvl_high: "Magas", kbd_selected: "kiválasztva", legend: "Jelmagyarázat", legend_show: "Jelmagyarázat megjelenítése", legend_hide: "Jelmagyarázat elrejtése", lg_zone: "Nyírási zóna", lg_zone_pending: "Nyírásra kiválasztva", lg_mower: "A fűnyíró helyzete", lg_dock: "Töltőállomás", lg_order: "Nyírási sorrend", lg_custom: "Egyéni zónabeállítások", lg_direction: "Nyírási irány", lg_stuck: "Itt akadt el", lg_hotspot: "Itt hiba történt (előfordulások)", lg_maint: "Karbantartási pont", lg_passage: "Átjárási pont", lg_nogo: "Tiltott zóna", lg_wall: "Virtuális fal", lg_coverage: "Lenyírt terület", lg_wifi: "Wi-Fi jel (zöld = erős)", view_mode: "Nézet", vw_beides: "Mindkettő", vw_weg: "Útvonal", vw_flaeche: "Terület", vw_wlan: "Wi-Fi", vw_saison: "Szezon", lg_season: "Nyírások száma (halvány = ritkán)", map_refreshing: "Térkép frissítése…", dbg_title: "Fogadott rétegek", dbg_zones: "Zónák", dbg_nogo: "Tiltott zónák", dbg_walls: "Falak", dbg_obstacles: "Akadályok", dbg_passthrough: "Átjárható zónák", dbg_required: "Kötelezők", dbg_tunnels: "Alagutak", dbg_markers: "Jelölők", dbg_draw: "Rajzolt területek", dbg_paths: "Útvonalpontok", maint: "Karbantartás", maint_show: "Karbantartás megjelenítése", maint_hide: "Karbantartás elrejtése", maint_base: "Bázisállomás", maint_blade: "Kések", maint_reset: "Számláló nullázása", maint_due: "most esedékes", maint_reset_done: "Számláló nullázva" },
  it: { no_map: "Nessuna mappa disponibile", not_connected: "In attesa dei dati del robot…", start: "Taglia", clear: "Svuota", zone: "zona", zones: "zone", reset_view: "Adatta mappa", reset_rotation: "Ripristina la rotazione predefinita", follow: "Segui il rasaerba", replay: "Riproduci questa sessione", replay_play: "Avvia la riproduzione", start_mowing: "Avvia taglio", pause: "Pausa", hud_progress: "Avanzamento", hud_eta_left: "rimanenti", dock: "Torna alla base", sent: "Taglio a zone avviato", preflight_none: "Storico confrontabile insufficiente", preflight_estimate: "Stima", preflight_battery: "di batteria", preflight_recharges: "ricariche", preflight_daylight: "potrebbe finire dopo il tramonto", missing_entity: "Imposta l'entità del rasaerba TerraMow nella configurazione", zi_cut_height: "Altezza di taglio", zi_speed: "Velocità di taglio", zi_spacing: "Distanza tra le strisce", zi_blade: "Velocità lame", zi_edge: "Taglio bordi", zi_direction: "Direzione", zi_order: "Ordine di taglio", zi_custom: "Impostazioni personalizzate", zi_global: "Impostazioni globali", lvl_low: "Bassa", lvl_medium: "Media", lvl_high: "Alta", kbd_selected: "selezionata", legend: "Legenda", legend_show: "Mostra la legenda", legend_hide: "Nascondi la legenda", lg_zone: "Zona di taglio", lg_zone_pending: "Selezionata per il taglio", lg_mower: "Posizione del rasaerba", lg_dock: "Base di ricarica", lg_order: "Ordine di taglio", lg_custom: "Impostazioni proprie della zona", lg_direction: "Direzione di taglio", lg_stuck: "Si è bloccato qui", lg_hotspot: "Qui si è verificato un guasto (occorrenze)", lg_maint: "Punto di manutenzione", lg_passage: "Punto di passaggio", lg_nogo: "Zona vietata", lg_wall: "Muro virtuale", lg_coverage: "Area tagliata", lg_wifi: "Segnale Wi-Fi (verde = forte)", view_mode: "Vista", vw_beides: "Entrambi", vw_weg: "Percorso", vw_flaeche: "Area", vw_wlan: "Wi-Fi", vw_saison: "Stagione", lg_season: "Numero di tagli (chiaro = raro)", map_refreshing: "Aggiornamento mappa…", dbg_title: "Livelli ricevuti", dbg_zones: "Zone", dbg_nogo: "Zone vietate", dbg_walls: "Muri", dbg_obstacles: "Ostacoli", dbg_passthrough: "Zone di passaggio", dbg_required: "Obbligatorie", dbg_tunnels: "Tunnel", dbg_markers: "Marcatori", dbg_draw: "Zone disegnate", dbg_paths: "Punti del percorso", maint: "Manutenzione", maint_show: "Mostra la manutenzione", maint_hide: "Nascondi la manutenzione", maint_base: "Stazione base", maint_blade: "Lame", maint_reset: "Azzera contatore", maint_due: "da fare ora", maint_reset_done: "Contatore azzerato" },
  ja: { no_map: "マップはまだありません", not_connected: "芝刈り機のデータを待機中…", start: "刈る", clear: "クリア", zone: "ゾーン", zones: "ゾーン", reset_view: "マップを全体表示", reset_rotation: "既定の回転に戻す", follow: "芝刈り機を追跡", replay: "このセッションを再生", replay_play: "再生を開始", start_mowing: "芝刈り開始", pause: "一時停止", hud_progress: "進捗", hud_eta_left: "残り", dock: "ドックに戻る", sent: "ゾーン芝刈りを開始しました", preflight_none: "比較できる履歴が足りません", preflight_estimate: "予測", preflight_battery: "バッテリー", preflight_recharges: "回の充電", preflight_daylight: "日没後に終わる可能性があります", missing_entity: "カード設定でTerraMow芝刈り機エンティティを設定してください", zi_cut_height: "刈り高さ", zi_speed: "刈り取り速度", zi_spacing: "刈り取り間隔", zi_blade: "ブレード回転速度", zi_edge: "エッジ刈り", zi_direction: "方向", zi_order: "刈り取り順序", zi_custom: "個別設定", zi_global: "全体設定", lvl_low: "低", lvl_medium: "中", lvl_high: "高", kbd_selected: "選択中", legend: "凡例", legend_show: "凡例を表示", legend_hide: "凡例を隠す", lg_zone: "芝刈りゾーン", lg_zone_pending: "刈り取り対象に選択", lg_mower: "芝刈り機の位置", lg_dock: "充電ステーション", lg_order: "刈り取り順序", lg_custom: "ゾーンの個別設定", lg_direction: "刈り取り方向", lg_stuck: "ここで動けなくなりました", lg_hotspot: "ここで異常が発生（回数）", lg_maint: "メンテナンス地点", lg_passage: "通路地点", lg_nogo: "進入禁止エリア", lg_wall: "バーチャルウォール", lg_coverage: "刈り取り済みエリア", lg_wifi: "Wi-Fi 信号（緑＝強い）", view_mode: "表示", vw_beides: "両方", vw_weg: "経路", vw_flaeche: "面積", vw_wlan: "Wi-Fi", vw_saison: "シーズン", lg_season: "刈り取り回数（淡色＝少ない）", map_refreshing: "マップを更新中…", dbg_title: "受信したレイヤー", dbg_zones: "ゾーン", dbg_nogo: "進入禁止エリア", dbg_walls: "壁", dbg_obstacles: "障害物", dbg_passthrough: "通行可能エリア", dbg_required: "必須エリア", dbg_tunnels: "トンネル", dbg_markers: "マーカー", dbg_draw: "描画エリア", dbg_paths: "経路ポイント", maint: "メンテナンス", maint_show: "メンテナンスを表示", maint_hide: "メンテナンスを隠す", maint_base: "ベースステーション", maint_blade: "ブレード", maint_reset: "カウンターをリセット", maint_due: "今すぐ必要", maint_reset_done: "カウンターをリセットしました" },
  ko: { no_map: "아직 지도가 없습니다", not_connected: "잔디깎이 데이터 대기 중…", start: "깎기", clear: "지우기", zone: "구역", zones: "구역", reset_view: "지도 맞추기", reset_rotation: "기본 회전으로 되돌리기", follow: "잔디깎이 따라가기", replay: "이 세션 다시 보기", replay_play: "재생 시작", start_mowing: "잔디깎기 시작", pause: "일시정지", hud_progress: "진행률", hud_eta_left: "남음", dock: "도크로 복귀", sent: "구역 잔디깎기 시작됨", preflight_none: "비교할 기록이 충분하지 않습니다", preflight_estimate: "예상", preflight_battery: "배터리", preflight_recharges: "회 충전", preflight_daylight: "일몰 후에 끝날 수 있습니다", missing_entity: "카드 설정에서 TerraMow 잔디깎이 엔티티를 설정하세요", zi_cut_height: "깎기 높이", zi_speed: "깎기 속도", zi_spacing: "깎기 간격", zi_blade: "블레이드 속도", zi_edge: "가장자리 깎기", zi_direction: "방향", zi_order: "깎기 순서", zi_custom: "사용자 설정", zi_global: "전체 설정", lvl_low: "낮음", lvl_medium: "중간", lvl_high: "높음", kbd_selected: "선택됨", legend: "범례", legend_show: "범례 표시", legend_hide: "범례 숨기기", lg_zone: "잔디깎기 구역", lg_zone_pending: "깎기로 선택됨", lg_mower: "잔디깎이 위치", lg_dock: "충전 스테이션", lg_order: "깎기 순서", lg_custom: "구역 사용자 설정", lg_direction: "깎기 방향", lg_stuck: "여기에서 갇혔습니다", lg_hotspot: "여기에서 오류 발생 (횟수)", lg_maint: "유지보수 지점", lg_passage: "통로 지점", lg_nogo: "금지 구역", lg_wall: "가상 벽", lg_coverage: "깎은 면적", lg_wifi: "Wi-Fi 신호 (녹색 = 강함)", view_mode: "보기", vw_beides: "둘 다", vw_weg: "경로", vw_flaeche: "면적", vw_wlan: "Wi-Fi", vw_saison: "시즌", lg_season: "깎은 횟수 (연한 색 = 드묾)", map_refreshing: "지도를 새로 고치는 중…", dbg_title: "수신된 레이어", dbg_zones: "구역", dbg_nogo: "금지 구역", dbg_walls: "벽", dbg_obstacles: "장애물", dbg_passthrough: "통과 구역", dbg_required: "필수 구역", dbg_tunnels: "터널", dbg_markers: "마커", dbg_draw: "그린 영역", dbg_paths: "경로 지점", maint: "유지보수", maint_show: "유지보수 표시", maint_hide: "유지보수 숨기기", maint_base: "베이스 스테이션", maint_blade: "블레이드", maint_reset: "카운터 초기화", maint_due: "지금 필요", maint_reset_done: "카운터가 초기화되었습니다" },
  lt: { no_map: "Žemėlapio dar nėra", not_connected: "Laukiama vejapjovės duomenų…", start: "Pjauti", clear: "Išvalyti", zone: "zona", zones: "zonos", reset_view: "Sutalpinti žemėlapį", reset_rotation: "Atkurti numatytąjį pasukimą", follow: "Sekti vejapjovę", replay: "Peržiūrėti šią sesiją", replay_play: "Paleisti peržiūrą", start_mowing: "Pradėti pjovimą", pause: "Pristabdyti", hud_progress: "Eiga", hud_eta_left: "liko", dock: "Grįžti į stotelę", sent: "Zonų pjovimas pradėtas", preflight_none: "Nepakanka palyginamos istorijos", preflight_estimate: "Įvertis", preflight_battery: "baterijos", preflight_recharges: "įkrovimai", preflight_daylight: "gali baigtis po saulėlydžio", missing_entity: "Kortelės nustatymuose nurodykite TerraMow vejapjovės objektą", zi_cut_height: "Pjovimo aukštis", zi_speed: "Pjovimo greitis", zi_spacing: "Juostų tarpas", zi_blade: "Peilių greitis", zi_edge: "Kraštų pjovimas", zi_direction: "Kryptis", zi_order: "Pjovimo eiliškumas", zi_custom: "Pasirinktiniai nustatymai", zi_global: "Bendrieji nustatymai", lvl_low: "Mažas", lvl_medium: "Vidutinis", lvl_high: "Didelis", kbd_selected: "pasirinkta", legend: "Legenda", legend_show: "Rodyti legendą", legend_hide: "Slėpti legendą", lg_zone: "Pjovimo zona", lg_zone_pending: "Pasirinkta pjauti", lg_mower: "Vejapjovės padėtis", lg_dock: "Įkrovimo stotelė", lg_order: "Pjovimo eiliškumas", lg_custom: "Pasirinktiniai zonos nustatymai", lg_direction: "Pjovimo kryptis", lg_stuck: "Čia įstrigo", lg_hotspot: "Čia įvyko gedimas (kartų)", lg_maint: "Priežiūros taškas", lg_passage: "Pravažiavimo taškas", lg_nogo: "Draudžiama zona", lg_wall: "Virtuali siena", lg_coverage: "Nupjautas plotas", lg_wifi: "Wi-Fi signalas (žalia = stiprus)", view_mode: "Rodinys", vw_beides: "Abu", vw_weg: "Maršrutas", vw_flaeche: "Plotas", vw_wlan: "Wi-Fi", vw_saison: "Sezonas", lg_season: "Pjovimų skaičius (blyšku = retai)", map_refreshing: "Žemėlapis atnaujinamas…", dbg_title: "Gauti sluoksniai", dbg_zones: "Zonos", dbg_nogo: "Draudžiamos zonos", dbg_walls: "Sienos", dbg_obstacles: "Kliūtys", dbg_passthrough: "Pravažiuojamos zonos", dbg_required: "Privalomos", dbg_tunnels: "Tuneliai", dbg_markers: "Žymos", dbg_draw: "Nubrėžtos sritys", dbg_paths: "Maršruto taškai", maint: "Priežiūra", maint_show: "Rodyti priežiūrą", maint_hide: "Slėpti priežiūrą", maint_base: "Bazinė stotis", maint_blade: "Peiliai", maint_reset: "Atstatyti skaitiklį", maint_due: "reikia dabar", maint_reset_done: "Skaitiklis atstatytas" },
  lv: { no_map: "Karte vēl nav pieejama", not_connected: "Gaida pļāvēja datus…", start: "Pļaut", clear: "Notīrīt", zone: "zona", zones: "zonas", reset_view: "Ietilpināt karti", reset_rotation: "Atjaunot noklusējuma pagriezienu", follow: "Sekot pļāvējam", replay: "Atskaņot šo sesiju", replay_play: "Sākt atskaņošanu", start_mowing: "Sākt pļaušanu", pause: "Pauze", hud_progress: "Progress", hud_eta_left: "atlicis", dock: "Atgriezties stacijā", sent: "Zonu pļaušana sākta", preflight_none: "Nepietiek salīdzināmas vēstures", preflight_estimate: "Aplēse", preflight_battery: "akumulatora", preflight_recharges: "uzlādes", preflight_daylight: "var beigties pēc saulrieta", missing_entity: "Kartītes konfigurācijā iestatiet TerraMow pļāvēja entītiju", zi_cut_height: "Pļaušanas augstums", zi_speed: "Pļaušanas ātrums", zi_spacing: "Joslu atstatums", zi_blade: "Asmeņu ātrums", zi_edge: "Malu pļaušana", zi_direction: "Virziens", zi_order: "Pļaušanas secība", zi_custom: "Pielāgoti iestatījumi", zi_global: "Globālie iestatījumi", lvl_low: "Zems", lvl_medium: "Vidējs", lvl_high: "Augsts", kbd_selected: "atlasīta", legend: "Apzīmējumi", legend_show: "Rādīt apzīmējumus", legend_hide: "Slēpt apzīmējumus", lg_zone: "Pļaušanas zona", lg_zone_pending: "Atlasīta pļaušanai", lg_mower: "Pļāvēja atrašanās vieta", lg_dock: "Uzlādes stacija", lg_order: "Pļaušanas secība", lg_custom: "Zonas pielāgotie iestatījumi", lg_direction: "Pļaušanas virziens", lg_stuck: "Šeit iestrēga", lg_hotspot: "Šeit notika kļūme (reizes)", lg_maint: "Apkopes punkts", lg_passage: "Ejas punkts", lg_nogo: "Aizliegtā zona", lg_wall: "Virtuāla siena", lg_coverage: "Nopļautā platība", lg_wifi: "Wi-Fi signāls (zaļš = spēcīgs)", view_mode: "Skats", vw_beides: "Abi", vw_weg: "Maršruts", vw_flaeche: "Platība", vw_wlan: "Wi-Fi", vw_saison: "Sezona", lg_season: "Pļaušanas reizes (bāls = reti)", map_refreshing: "Karte tiek atsvaidzināta…", dbg_title: "Saņemtie slāņi", dbg_zones: "Zonas", dbg_nogo: "Aizliegtās zonas", dbg_walls: "Sienas", dbg_obstacles: "Šķēršļi", dbg_passthrough: "Caurbraucamās zonas", dbg_required: "Obligātās", dbg_tunnels: "Tuneļi", dbg_markers: "Atzīmes", dbg_draw: "Zīmētie apgabali", dbg_paths: "Maršruta punkti", maint: "Apkope", maint_show: "Rādīt apkopi", maint_hide: "Slēpt apkopi", maint_base: "Bāzes stacija", maint_blade: "Asmeņi", maint_reset: "Atiestatīt skaitītāju", maint_due: "jāveic tagad", maint_reset_done: "Skaitītājs atiestatīts" },
  nb: { no_map: "Ingen kart tilgjengelig ennå", not_connected: "Venter på data fra gressklipperen…", start: "Klipp", clear: "Tøm", zone: "sone", zones: "soner", reset_view: "Tilpass kartet", reset_rotation: "Tilbakestill til standardrotasjon", follow: "Følg gressklipperen", replay: "Spill av denne økten", replay_play: "Start avspillingen", start_mowing: "Start klipping", pause: "Pause", hud_progress: "Fremdrift", hud_eta_left: "igjen", dock: "Tilbake til basen", sent: "Soneklipping startet", preflight_none: "Ikke nok sammenlignbar historikk", preflight_estimate: "Estimat", preflight_battery: "batteri", preflight_recharges: "ladinger", preflight_daylight: "kan bli ferdig etter solnedgang", missing_entity: "Angi en TerraMow-gressklipperentitet i kortkonfigurasjonen", zi_cut_height: "Klippehøyde", zi_speed: "Klippehastighet", zi_spacing: "Baneavstand", zi_blade: "Knivhastighet", zi_edge: "Kantklipping", zi_direction: "Retning", zi_order: "Klipperekkefølge", zi_custom: "Egne innstillinger", zi_global: "Globale innstillinger", lvl_low: "Lav", lvl_medium: "Middels", lvl_high: "Høy", kbd_selected: "valgt", legend: "Tegnforklaring", legend_show: "Vis tegnforklaring", legend_hide: "Skjul tegnforklaring", lg_zone: "Klippesone", lg_zone_pending: "Valgt for klipping", lg_mower: "Gressklipperens posisjon", lg_dock: "Ladestasjon", lg_order: "Klipperekkefølge", lg_custom: "Egne soneinnstillinger", lg_direction: "Klipperetning", lg_stuck: "Satt fast her", lg_hotspot: "Feil oppsto her (antall)", lg_maint: "Vedlikeholdspunkt", lg_passage: "Passasjepunkt", lg_nogo: "Forbudt sone", lg_wall: "Virtuell vegg", lg_coverage: "Klippet areal", lg_wifi: "Wi-Fi-signal (grønn = sterkt)", view_mode: "Visning", vw_beides: "Begge", vw_weg: "Rute", vw_flaeche: "Areal", vw_wlan: "Wi-Fi", vw_saison: "Sesong", lg_season: "Antall klippinger (blek = sjelden)", map_refreshing: "Kartet oppdateres…", dbg_title: "Mottatte lag", dbg_zones: "Soner", dbg_nogo: "Forbudte soner", dbg_walls: "Vegger", dbg_obstacles: "Hindringer", dbg_passthrough: "Gjennomkjøring", dbg_required: "Påkrevde", dbg_tunnels: "Tunneler", dbg_markers: "Markører", dbg_draw: "Tegnede områder", dbg_paths: "Rutepunkter", maint: "Vedlikehold", maint_show: "Vis vedlikehold", maint_hide: "Skjul vedlikehold", maint_base: "Basestasjon", maint_blade: "Kniver", maint_reset: "Nullstill teller", maint_due: "må gjøres nå", maint_reset_done: "Teller nullstilt" },
  nl: { no_map: "Nog geen kaart beschikbaar", not_connected: "Wachten op maaierdata…", start: "Maaien", clear: "Wissen", zone: "zone", zones: "zones", reset_view: "Kaart passend maken", reset_rotation: "Standaardrotatie herstellen", follow: "Volg de maaier", replay: "Deze sessie afspelen", replay_play: "Afspelen starten", start_mowing: "Maaien starten", pause: "Pauzeren", hud_progress: "Voortgang", hud_eta_left: "resterend", dock: "Terug naar dock", sent: "Zonemaaien gestart", preflight_none: "Te weinig vergelijkbare geschiedenis", preflight_estimate: "Schatting", preflight_battery: "accu", preflight_recharges: "laadpauzes", preflight_daylight: "eindigt mogelijk na zonsondergang", missing_entity: "Stel een TerraMow-maaierentiteit in bij de kaartconfiguratie", zi_cut_height: "Maaihoogte", zi_speed: "Maaisnelheid", zi_spacing: "Baanafstand", zi_blade: "Messnelheid", zi_edge: "Randmaaien", zi_direction: "Richting", zi_order: "Maaivolgorde", zi_custom: "Eigen instellingen", zi_global: "Globale instellingen", lvl_low: "Laag", lvl_medium: "Gemiddeld", lvl_high: "Hoog", kbd_selected: "geselecteerd", legend: "Legenda", legend_show: "Legenda tonen", legend_hide: "Legenda verbergen", lg_zone: "Maaizone", lg_zone_pending: "Geselecteerd om te maaien", lg_mower: "Positie van de maaier", lg_dock: "Laadstation", lg_order: "Maaivolgorde", lg_custom: "Eigen zone-instellingen", lg_direction: "Maairichting", lg_stuck: "Hier vastgelopen", lg_hotspot: "Hier trad een storing op (aantal)", lg_maint: "Onderhoudspunt", lg_passage: "Doorgangspunt", lg_nogo: "Verboden zone", lg_wall: "Virtuele muur", lg_coverage: "Gemaaid oppervlak", lg_wifi: "Wi-Fi-signaal (groen = sterk)", view_mode: "Weergave", vw_beides: "Beide", vw_weg: "Pad", vw_flaeche: "Oppervlak", vw_wlan: "Wi-Fi", vw_saison: "Seizoen", lg_season: "Aantal maaibeurten (bleek = zelden)", map_refreshing: "Kaart wordt vernieuwd…", dbg_title: "Ontvangen lagen", dbg_zones: "Zones", dbg_nogo: "Verboden zones", dbg_walls: "Muren", dbg_obstacles: "Obstakels", dbg_passthrough: "Doorgangszones", dbg_required: "Verplichte", dbg_tunnels: "Tunnels", dbg_markers: "Markeringen", dbg_draw: "Getekende gebieden", dbg_paths: "Padpunten", maint: "Onderhoud", maint_show: "Onderhoud tonen", maint_hide: "Onderhoud verbergen", maint_base: "Basisstation", maint_blade: "Messen", maint_reset: "Teller resetten", maint_due: "nu nodig", maint_reset_done: "Teller gereset" },
  pl: { no_map: "Mapa nie jest jeszcze dostępna", not_connected: "Oczekiwanie na dane kosiarki…", start: "Koś", clear: "Wyczyść", zone: "strefa", zones: "strefy", reset_view: "Dopasuj mapę", reset_rotation: "Przywróć domyślny obrót", follow: "Śledź kosiarkę", replay: "Odtwórz tę sesję", replay_play: "Uruchom odtwarzanie", start_mowing: "Rozpocznij koszenie", pause: "Wstrzymaj", hud_progress: "Postęp", hud_eta_left: "pozostało", dock: "Wróć do stacji", sent: "Rozpoczęto koszenie stref", preflight_none: "Za mało porównywalnej historii", preflight_estimate: "Szacunek", preflight_battery: "baterii", preflight_recharges: "doładowania", preflight_daylight: "może zakończyć się po zachodzie słońca", missing_entity: "Ustaw encję kosiarki TerraMow w konfiguracji karty", zi_cut_height: "Wysokość koszenia", zi_speed: "Prędkość koszenia", zi_spacing: "Odstęp pasów", zi_blade: "Prędkość ostrzy", zi_edge: "Koszenie krawędzi", zi_direction: "Kierunek", zi_order: "Kolejność koszenia", zi_custom: "Ustawienia własne", zi_global: "Ustawienia globalne", lvl_low: "Niska", lvl_medium: "Średnia", lvl_high: "Wysoka", kbd_selected: "wybrana", legend: "Legenda", legend_show: "Pokaż legendę", legend_hide: "Ukryj legendę", lg_zone: "Strefa koszenia", lg_zone_pending: "Wybrana do koszenia", lg_mower: "Pozycja kosiarki", lg_dock: "Stacja ładowania", lg_order: "Kolejność koszenia", lg_custom: "Własne ustawienia strefy", lg_direction: "Kierunek koszenia", lg_stuck: "Tu utknęła", lg_hotspot: "Tu wystąpiła usterka (liczba)", lg_maint: "Punkt konserwacji", lg_passage: "Punkt przejścia", lg_nogo: "Strefa zakazana", lg_wall: "Wirtualna ściana", lg_coverage: "Skoszona powierzchnia", lg_wifi: "Sygnał Wi-Fi (zielony = silny)", view_mode: "Widok", vw_beides: "Oba", vw_weg: "Trasa", vw_flaeche: "Powierzchnia", vw_wlan: "Wi-Fi", vw_saison: "Sezon", lg_season: "Liczba koszeń (jasny = rzadko)", map_refreshing: "Odświeżanie mapy…", dbg_title: "Odebrane warstwy", dbg_zones: "Strefy", dbg_nogo: "Strefy zakazane", dbg_walls: "Ściany", dbg_obstacles: "Przeszkody", dbg_passthrough: "Strefy przejazdu", dbg_required: "Obowiązkowe", dbg_tunnels: "Tunele", dbg_markers: "Znaczniki", dbg_draw: "Narysowane obszary", dbg_paths: "Punkty trasy", maint: "Konserwacja", maint_show: "Pokaż konserwację", maint_hide: "Ukryj konserwację", maint_base: "Stacja bazowa", maint_blade: "Ostrza", maint_reset: "Zresetuj licznik", maint_due: "wymagane teraz", maint_reset_done: "Licznik zresetowany" },
  pt: { no_map: "Ainda não há mapa disponível", not_connected: "A aguardar dados do corta-relva…", start: "Cortar", clear: "Limpar", zone: "zona", zones: "zonas", reset_view: "Ajustar mapa", reset_rotation: "Repor a rotação predefinida", follow: "Seguir o corta-relva", replay: "Reproduzir esta sessão", replay_play: "Iniciar a reprodução", start_mowing: "Iniciar corte", pause: "Pausar", hud_progress: "Progresso", hud_eta_left: "restantes", dock: "Voltar à base", sent: "Corte por zonas iniciado", preflight_none: "Histórico comparável insuficiente", preflight_estimate: "Estimativa", preflight_battery: "de bateria", preflight_recharges: "recargas", preflight_daylight: "pode terminar depois do pôr do sol", missing_entity: "Defina a entidade do corta-relva TerraMow na configuração", zi_cut_height: "Altura de corte", zi_speed: "Velocidade de corte", zi_spacing: "Espaçamento das faixas", zi_blade: "Velocidade das lâminas", zi_edge: "Corte de bordas", zi_direction: "Direção", zi_order: "Ordem de corte", zi_custom: "Definições personalizadas", zi_global: "Definições globais", lvl_low: "Baixa", lvl_medium: "Média", lvl_high: "Alta", kbd_selected: "selecionada", legend: "Legenda", legend_show: "Mostrar legenda", legend_hide: "Ocultar legenda", lg_zone: "Zona de corte", lg_zone_pending: "Selecionada para cortar", lg_mower: "Posição do corta-relva", lg_dock: "Base de carregamento", lg_order: "Ordem de corte", lg_custom: "Definições próprias da zona", lg_direction: "Direção de corte", lg_stuck: "Ficou preso aqui", lg_hotspot: "Ocorreu uma falha aqui (repetições)", lg_maint: "Ponto de manutenção", lg_passage: "Ponto de passagem", lg_nogo: "Zona proibida", lg_wall: "Parede virtual", lg_coverage: "Área cortada", lg_wifi: "Sinal Wi-Fi (verde = forte)", view_mode: "Vista", vw_beides: "Ambos", vw_weg: "Trajeto", vw_flaeche: "Área", vw_wlan: "Wi-Fi", vw_saison: "Época", lg_season: "Número de cortes (claro = raro)", map_refreshing: "A atualizar o mapa…", dbg_title: "Camadas recebidas", dbg_zones: "Zonas", dbg_nogo: "Zonas proibidas", dbg_walls: "Paredes", dbg_obstacles: "Obstáculos", dbg_passthrough: "Zonas de passagem", dbg_required: "Obrigatórias", dbg_tunnels: "Túneis", dbg_markers: "Marcadores", dbg_draw: "Zonas desenhadas", dbg_paths: "Pontos do trajeto", maint: "Manutenção", maint_show: "Mostrar manutenção", maint_hide: "Ocultar manutenção", maint_base: "Estação base", maint_blade: "Lâminas", maint_reset: "Repor contador", maint_due: "necessário agora", maint_reset_done: "Contador reposto" },
  "pt-BR": { no_map: "Nenhum mapa disponível ainda", not_connected: "Aguardando dados do cortador…", start: "Cortar", clear: "Limpar", zone: "zona", zones: "zonas", reset_view: "Ajustar mapa", reset_rotation: "Restaurar a rotação padrão", follow: "Seguir o cortador", replay: "Reproduzir esta sessão", replay_play: "Iniciar a reprodução", start_mowing: "Iniciar corte", pause: "Pausar", hud_progress: "Progresso", hud_eta_left: "restantes", dock: "Voltar à base", sent: "Corte por zonas iniciado", preflight_none: "Histórico comparável insuficiente", preflight_estimate: "Estimativa", preflight_battery: "de bateria", preflight_recharges: "recargas", preflight_daylight: "pode terminar depois do pôr do sol", missing_entity: "Defina a entidade do cortador TerraMow na configuração do cartão", zi_cut_height: "Altura de corte", zi_speed: "Velocidade de corte", zi_spacing: "Espaçamento das faixas", zi_blade: "Velocidade das lâminas", zi_edge: "Corte de bordas", zi_direction: "Direção", zi_order: "Ordem de corte", zi_custom: "Configurações personalizadas", zi_global: "Configurações globais", lvl_low: "Baixa", lvl_medium: "Média", lvl_high: "Alta", kbd_selected: "selecionada", legend: "Legenda", legend_show: "Mostrar legenda", legend_hide: "Ocultar legenda", lg_zone: "Zona de corte", lg_zone_pending: "Selecionada para cortar", lg_mower: "Posição do cortador", lg_dock: "Base de carregamento", lg_order: "Ordem de corte", lg_custom: "Configurações próprias da zona", lg_direction: "Direção de corte", lg_stuck: "Ficou preso aqui", lg_hotspot: "Ocorreu uma falha aqui (repetições)", lg_maint: "Ponto de manutenção", lg_passage: "Ponto de passagem", lg_nogo: "Zona proibida", lg_wall: "Parede virtual", lg_coverage: "Área cortada", lg_wifi: "Sinal Wi-Fi (verde = forte)", view_mode: "Visualização", vw_beides: "Ambos", vw_weg: "Trajeto", vw_flaeche: "Área", vw_wlan: "Wi-Fi", vw_saison: "Temporada", lg_season: "Número de cortes (claro = raro)", map_refreshing: "Atualizando o mapa…", dbg_title: "Camadas recebidas", dbg_zones: "Zonas", dbg_nogo: "Zonas proibidas", dbg_walls: "Paredes", dbg_obstacles: "Obstáculos", dbg_passthrough: "Zonas de passagem", dbg_required: "Obrigatórias", dbg_tunnels: "Túneis", dbg_markers: "Marcadores", dbg_draw: "Zonas desenhadas", dbg_paths: "Pontos do trajeto", maint: "Manutenção", maint_show: "Mostrar manutenção", maint_hide: "Ocultar manutenção", maint_base: "Estação base", maint_blade: "Lâminas", maint_reset: "Redefinir contador", maint_due: "necessário agora", maint_reset_done: "Contador redefinido" },
  ro: { no_map: "Încă nu există hartă", not_connected: "Se așteaptă datele mașinii de tuns…", start: "Tunde", clear: "Golește", zone: "zonă", zones: "zone", reset_view: "Potrivește harta", reset_rotation: "Restabilește rotația implicită", follow: "Urmărește mașina", replay: "Redă această sesiune", replay_play: "Pornește redarea", start_mowing: "Pornește tunderea", pause: "Pauză", hud_progress: "Progres", hud_eta_left: "rămase", dock: "Înapoi la stație", sent: "Tunderea pe zone a început", preflight_none: "Nu există suficient istoric comparabil", preflight_estimate: "Estimare", preflight_battery: "baterie", preflight_recharges: "reîncărcări", preflight_daylight: "se poate încheia după apus", missing_entity: "Setați entitatea mașinii de tuns TerraMow în configurația cardului", zi_cut_height: "Înălțime de tundere", zi_speed: "Viteză de tundere", zi_spacing: "Distanța dintre benzi", zi_blade: "Viteza lamelor", zi_edge: "Tundere margini", zi_direction: "Direcție", zi_order: "Ordinea de tundere", zi_custom: "Setări personalizate", zi_global: "Setări globale", lvl_low: "Mică", lvl_medium: "Medie", lvl_high: "Mare", kbd_selected: "selectată", legend: "Legendă", legend_show: "Afișează legenda", legend_hide: "Ascunde legenda", lg_zone: "Zonă de tundere", lg_zone_pending: "Selectată pentru tundere", lg_mower: "Poziția mașinii", lg_dock: "Stație de încărcare", lg_order: "Ordinea de tundere", lg_custom: "Setări proprii ale zonei", lg_direction: "Direcția de tundere", lg_stuck: "S-a blocat aici", lg_hotspot: "Aici a apărut o defecțiune (repetări)", lg_maint: "Punct de întreținere", lg_passage: "Punct de trecere", lg_nogo: "Zonă interzisă", lg_wall: "Perete virtual", lg_coverage: "Suprafață tunsă", lg_wifi: "Semnal Wi-Fi (verde = puternic)", view_mode: "Vizualizare", vw_beides: "Ambele", vw_weg: "Traseu", vw_flaeche: "Suprafață", vw_wlan: "Wi-Fi", vw_saison: "Sezon", lg_season: "Număr de tunderi (palid = rar)", map_refreshing: "Harta se actualizează…", dbg_title: "Straturi primite", dbg_zones: "Zone", dbg_nogo: "Zone interzise", dbg_walls: "Pereți", dbg_obstacles: "Obstacole", dbg_passthrough: "Zone de trecere", dbg_required: "Obligatorii", dbg_tunnels: "Tuneluri", dbg_markers: "Marcaje", dbg_draw: "Zone desenate", dbg_paths: "Puncte de traseu", maint: "Întreținere", maint_show: "Afișează întreținerea", maint_hide: "Ascunde întreținerea", maint_base: "Stație de bază", maint_blade: "Lame", maint_reset: "Resetează contorul", maint_due: "necesar acum", maint_reset_done: "Contor resetat" },
  ru: { no_map: "Карта пока недоступна", not_connected: "Ожидание данных газонокосилки…", start: "Косить", clear: "Очистить", zone: "зона", zones: "зоны", reset_view: "Вписать карту", reset_rotation: "Сбросить поворот по умолчанию", follow: "Следовать за косилкой", replay: "Воспроизвести этот сеанс", replay_play: "Запустить воспроизведение", start_mowing: "Начать стрижку", pause: "Пауза", hud_progress: "Прогресс", hud_eta_left: "осталось", dock: "Вернуться на базу", sent: "Стрижка зон начата", preflight_none: "Недостаточно сопоставимой истории", preflight_estimate: "Оценка", preflight_battery: "заряда", preflight_recharges: "подзарядок", preflight_daylight: "может завершиться после заката", missing_entity: "Укажите сущность газонокосилки TerraMow в настройках карточки", zi_cut_height: "Высота скашивания", zi_speed: "Скорость скашивания", zi_spacing: "Интервал полос", zi_blade: "Скорость ножей", zi_edge: "Скашивание кромок", zi_direction: "Направление", zi_order: "Порядок скашивания", zi_custom: "Свои настройки", zi_global: "Общие настройки", lvl_low: "Низкая", lvl_medium: "Средняя", lvl_high: "Высокая", kbd_selected: "выбрана", legend: "Легенда", legend_show: "Показать легенду", legend_hide: "Скрыть легенду", lg_zone: "Зона скашивания", lg_zone_pending: "Выбрана для скашивания", lg_mower: "Положение косилки", lg_dock: "Зарядная станция", lg_order: "Порядок скашивания", lg_custom: "Свои настройки зоны", lg_direction: "Направление скашивания", lg_stuck: "Здесь застряла", lg_hotspot: "Здесь произошёл сбой (число)", lg_maint: "Точка обслуживания", lg_passage: "Точка прохода", lg_nogo: "Запретная зона", lg_wall: "Виртуальная стена", lg_coverage: "Скошенная площадь", lg_wifi: "Сигнал Wi-Fi (зелёный = сильный)", view_mode: "Вид", vw_beides: "Оба", vw_weg: "Путь", vw_flaeche: "Площадь", vw_wlan: "Wi-Fi", vw_saison: "Сезон", lg_season: "Число скашиваний (бледный = редко)", map_refreshing: "Карта обновляется…", dbg_title: "Полученные слои", dbg_zones: "Зоны", dbg_nogo: "Запретные зоны", dbg_walls: "Стены", dbg_obstacles: "Препятствия", dbg_passthrough: "Зоны проезда", dbg_required: "Обязательные", dbg_tunnels: "Туннели", dbg_markers: "Метки", dbg_draw: "Нарисованные области", dbg_paths: "Точки пути", maint: "Обслуживание", maint_show: "Показать обслуживание", maint_hide: "Скрыть обслуживание", maint_base: "Базовая станция", maint_blade: "Ножи", maint_reset: "Сбросить счётчик", maint_due: "требуется сейчас", maint_reset_done: "Счётчик сброшен" },
  sk: { no_map: "Mapa zatiaľ nie je k dispozícii", not_connected: "Čaká sa na údaje kosačky…", start: "Kosiť", clear: "Vymazať", zone: "zóna", zones: "zóny", reset_view: "Prispôsobiť mapu", reset_rotation: "Obnoviť predvolené otočenie", follow: "Sledovať kosačku", replay: "Prehrať túto reláciu", replay_play: "Spustiť prehrávanie", start_mowing: "Spustiť kosenie", pause: "Pozastaviť", hud_progress: "Priebeh", hud_eta_left: "zostáva", dock: "Späť na stanicu", sent: "Kosenie zón spustené", preflight_none: "Nedostatok porovnateľnej histórie", preflight_estimate: "Odhad", preflight_battery: "batérie", preflight_recharges: "dobíjaní", preflight_daylight: "môže skončiť po západe slnka", missing_entity: "Nastavte entitu kosačky TerraMow v konfigurácii karty", zi_cut_height: "Výška kosenia", zi_speed: "Rýchlosť kosenia", zi_spacing: "Rozstup pruhov", zi_blade: "Rýchlosť nožov", zi_edge: "Kosenie okrajov", zi_direction: "Smer", zi_order: "Poradie kosenia", zi_custom: "Vlastné nastavenia", zi_global: "Globálne nastavenia", lvl_low: "Nízka", lvl_medium: "Stredná", lvl_high: "Vysoká", kbd_selected: "vybraté", legend: "Legenda", legend_show: "Zobraziť legendu", legend_hide: "Skryť legendu", lg_zone: "Zóna kosenia", lg_zone_pending: "Vybraté na kosenie", lg_mower: "Poloha kosačky", lg_dock: "Nabíjacia stanica", lg_order: "Poradie kosenia", lg_custom: "Vlastné nastavenia zóny", lg_direction: "Smer kosenia", lg_stuck: "Tu uviazla", lg_hotspot: "Tu došlo k poruche (počet)", lg_maint: "Bod údržby", lg_passage: "Bod priechodu", lg_nogo: "Zakázaná zóna", lg_wall: "Virtuálna stena", lg_coverage: "Pokosená plocha", lg_wifi: "Signál Wi-Fi (zelená = silný)", view_mode: "Zobrazenie", vw_beides: "Oboje", vw_weg: "Trasa", vw_flaeche: "Plocha", vw_wlan: "Wi-Fi", vw_saison: "Sezóna", lg_season: "Počet kosení (svetlé = zriedka)", map_refreshing: "Mapa sa aktualizuje…", dbg_title: "Prijaté vrstvy", dbg_zones: "Zóny", dbg_nogo: "Zakázané zóny", dbg_walls: "Steny", dbg_obstacles: "Prekážky", dbg_passthrough: "Prejazdné zóny", dbg_required: "Povinné", dbg_tunnels: "Tunely", dbg_markers: "Značky", dbg_draw: "Nakreslené oblasti", dbg_paths: "Body trasy", maint: "Údržba", maint_show: "Zobraziť údržbu", maint_hide: "Skryť údržbu", maint_base: "Základňová stanica", maint_blade: "Nože", maint_reset: "Vynulovať počítadlo", maint_due: "potrebné teraz", maint_reset_done: "Počítadlo vynulované" },
  sl: { no_map: "Zemljevid še ni na voljo", not_connected: "Čakanje na podatke kosilnice…", start: "Kosi", clear: "Počisti", zone: "cona", zones: "cone", reset_view: "Prilagodi zemljevid", reset_rotation: "Ponastavi na privzeti zasuk", follow: "Sledi kosilnici", replay: "Predvajaj to sejo", replay_play: "Zaženi predvajanje", start_mowing: "Začni košnjo", pause: "Premor", hud_progress: "Napredek", hud_eta_left: "preostalo", dock: "Nazaj na postajo", sent: "Košnja con se je začela", preflight_none: "Premalo primerljive zgodovine", preflight_estimate: "Ocena", preflight_battery: "baterije", preflight_recharges: "polnjenj", preflight_daylight: "se lahko konča po sončnem zahodu", missing_entity: "Nastavite entiteto kosilnice TerraMow v konfiguraciji kartice", zi_cut_height: "Višina košnje", zi_speed: "Hitrost košnje", zi_spacing: "Razmik pasov", zi_blade: "Hitrost rezil", zi_edge: "Košnja robov", zi_direction: "Smer", zi_order: "Vrstni red košnje", zi_custom: "Nastavitve po meri", zi_global: "Globalne nastavitve", lvl_low: "Nizka", lvl_medium: "Srednja", lvl_high: "Visoka", kbd_selected: "izbrano", legend: "Legenda", legend_show: "Prikaži legendo", legend_hide: "Skrij legendo", lg_zone: "Območje košnje", lg_zone_pending: "Izbrano za košnjo", lg_mower: "Položaj kosilnice", lg_dock: "Polnilna postaja", lg_order: "Vrstni red košnje", lg_custom: "Lastne nastavitve območja", lg_direction: "Smer košnje", lg_stuck: "Tu se je zataknila", lg_hotspot: "Tu je prišlo do napake (število)", lg_maint: "Vzdrževalna točka", lg_passage: "Prehodna točka", lg_nogo: "Prepovedano območje", lg_wall: "Navidezna stena", lg_coverage: "Pokošena površina", lg_wifi: "Signal Wi-Fi (zeleno = močan)", view_mode: "Pogled", vw_beides: "Oboje", vw_weg: "Pot", vw_flaeche: "Površina", vw_wlan: "Wi-Fi", vw_saison: "Sezona", lg_season: "Število košenj (bledo = redko)", map_refreshing: "Zemljevid se osvežuje…", dbg_title: "Prejete plasti", dbg_zones: "Območja", dbg_nogo: "Prepovedana območja", dbg_walls: "Stene", dbg_obstacles: "Ovire", dbg_passthrough: "Prehodna območja", dbg_required: "Obvezna", dbg_tunnels: "Predori", dbg_markers: "Oznake", dbg_draw: "Narisana območja", dbg_paths: "Točke poti", maint: "Vzdrževanje", maint_show: "Prikaži vzdrževanje", maint_hide: "Skrij vzdrževanje", maint_base: "Bazna postaja", maint_blade: "Rezila", maint_reset: "Ponastavi števec", maint_due: "potrebno zdaj", maint_reset_done: "Števec ponastavljen" },
  sr: { no_map: "Мапа још није доступна", not_connected: "Чекање података косачице…", start: "Коси", clear: "Очисти", zone: "зона", zones: "зоне", reset_view: "Уклопи мапу", reset_rotation: "Врати подразумевану ротацију", follow: "Прати косачицу", replay: "Репродукуј ову сесију", replay_play: "Покрени репродукцију", start_mowing: "Покрени кошење", pause: "Пауза", hud_progress: "Напредак", hud_eta_left: "преостало", dock: "Назад на станицу", sent: "Кошење зона покренуто", preflight_none: "Нема довољно упоредиве историје", preflight_estimate: "Процена", preflight_battery: "батерије", preflight_recharges: "пуњења", preflight_daylight: "може да се заврши после заласка сунца", missing_entity: "Подесите ентитет TerraMow косачице у конфигурацији картице", zi_cut_height: "Висина кошења", zi_speed: "Брзина кошења", zi_spacing: "Размак трака", zi_blade: "Брзина ножева", zi_edge: "Кошење ивица", zi_direction: "Смер", zi_order: "Редослед кошења", zi_custom: "Прилагођена подешавања", zi_global: "Глобална подешавања", lvl_low: "Ниска", lvl_medium: "Средња", lvl_high: "Висока", kbd_selected: "изабрано", legend: "Легенда", legend_show: "Прикажи легенду", legend_hide: "Сакриј легенду", lg_zone: "Зона кошења", lg_zone_pending: "Изабрано за кошење", lg_mower: "Положај косачице", lg_dock: "Станица за пуњење", lg_order: "Редослед кошења", lg_custom: "Прилагођена подешавања зоне", lg_direction: "Смер кошења", lg_stuck: "Овде се заглавила", lg_hotspot: "Овде је дошло до квара (број)", lg_maint: "Тачка одржавања", lg_passage: "Тачка пролаза", lg_nogo: "Забрањена зона", lg_wall: "Виртуелни зид", lg_coverage: "Покошена површина", lg_wifi: "Wi-Fi сигнал (зелено = јак)", view_mode: "Приказ", vw_beides: "Обоје", vw_weg: "Путања", vw_flaeche: "Површина", vw_wlan: "Wi-Fi", vw_saison: "Сезона", lg_season: "Број кошења (бледо = ретко)", map_refreshing: "Мапа се освежава…", dbg_title: "Примљени слојеви", dbg_zones: "Зоне", dbg_nogo: "Забрањене зоне", dbg_walls: "Зидови", dbg_obstacles: "Препреке", dbg_passthrough: "Пролазне зоне", dbg_required: "Обавезне", dbg_tunnels: "Тунели", dbg_markers: "Ознаке", dbg_draw: "Нацртане зоне", dbg_paths: "Тачке путање", maint: "Одржавање", maint_show: "Прикажи одржавање", maint_hide: "Сакриј одржавање", maint_base: "Базна станица", maint_blade: "Ножеви", maint_reset: "Ресетуј бројач", maint_due: "потребно сада", maint_reset_done: "Бројач ресетован" },
  sv: { no_map: "Ingen karta tillgänglig ännu", not_connected: "Väntar på data från gräsklipparen…", start: "Klipp", clear: "Rensa", zone: "zon", zones: "zoner", reset_view: "Anpassa kartan", reset_rotation: "Återställ till standardrotation", follow: "Följ gräsklipparen", replay: "Spela upp denna session", replay_play: "Starta uppspelningen", start_mowing: "Starta klippning", pause: "Pausa", hud_progress: "Förlopp", hud_eta_left: "kvar", dock: "Åter till basen", sent: "Zonklippning startad", preflight_none: "Inte tillräckligt med jämförbar historik", preflight_estimate: "Uppskattning", preflight_battery: "batteri", preflight_recharges: "laddningar", preflight_daylight: "kan bli klar efter solnedgången", missing_entity: "Ange en TerraMow-gräsklipparentitet i kortets konfiguration", zi_cut_height: "Klipphöjd", zi_speed: "Klipphastighet", zi_spacing: "Banavstånd", zi_blade: "Knivhastighet", zi_edge: "Kantklippning", zi_direction: "Riktning", zi_order: "Klippordning", zi_custom: "Egna inställningar", zi_global: "Globala inställningar", lvl_low: "Låg", lvl_medium: "Medel", lvl_high: "Hög", kbd_selected: "vald", legend: "Teckenförklaring", legend_show: "Visa teckenförklaring", legend_hide: "Dölj teckenförklaring", lg_zone: "Klippzon", lg_zone_pending: "Vald för klippning", lg_mower: "Gräsklipparens position", lg_dock: "Laddstation", lg_order: "Klippordning", lg_custom: "Egna zoninställningar", lg_direction: "Klippriktning", lg_stuck: "Fastnade här", lg_hotspot: "Fel inträffade här (antal)", lg_maint: "Underhållspunkt", lg_passage: "Passagepunkt", lg_nogo: "Förbjuden zon", lg_wall: "Virtuell vägg", lg_coverage: "Klippt yta", lg_wifi: "Wi-Fi-signal (grön = stark)", view_mode: "Vy", vw_beides: "Båda", vw_weg: "Rutt", vw_flaeche: "Yta", vw_wlan: "Wi-Fi", vw_saison: "Säsong", lg_season: "Antal klippningar (blek = sällan)", map_refreshing: "Kartan uppdateras…", dbg_title: "Mottagna lager", dbg_zones: "Zoner", dbg_nogo: "Förbjudna zoner", dbg_walls: "Väggar", dbg_obstacles: "Hinder", dbg_passthrough: "Genomfart", dbg_required: "Obligatoriska", dbg_tunnels: "Tunnlar", dbg_markers: "Markörer", dbg_draw: "Ritade områden", dbg_paths: "Ruttpunkter", maint: "Underhåll", maint_show: "Visa underhåll", maint_hide: "Dölj underhåll", maint_base: "Basstation", maint_blade: "Knivar", maint_reset: "Nollställ räknare", maint_due: "behövs nu", maint_reset_done: "Räknaren nollställd" },
  tr: { no_map: "Henüz harita yok", not_connected: "Çim biçme makinesi verileri bekleniyor…", start: "Biç", clear: "Temizle", zone: "bölge", zones: "bölge", reset_view: "Haritayı sığdır", reset_rotation: "Varsayılan dönüşe sıfırla", follow: "Makineyi takip et", replay: "Bu oturumu yeniden oynat", replay_play: "Oynatmayı başlat", start_mowing: "Biçmeyi başlat", pause: "Duraklat", hud_progress: "İlerleme", hud_eta_left: "kaldı", dock: "İstasyona dön", sent: "Bölge biçme başlatıldı", preflight_none: "Karşılaştırılabilir yeterli geçmiş yok", preflight_estimate: "Tahmin", preflight_battery: "pil", preflight_recharges: "şarj molası", preflight_daylight: "gün batımından sonra bitebilir", missing_entity: "Kart yapılandırmasında bir TerraMow çim biçme varlığı ayarlayın", zi_cut_height: "Biçme yüksekliği", zi_speed: "Biçme hızı", zi_spacing: "Şerit aralığı", zi_blade: "Bıçak hızı", zi_edge: "Kenar kesimi", zi_direction: "Yön", zi_order: "Biçme sırası", zi_custom: "Özel ayarlar", zi_global: "Genel ayarlar", lvl_low: "Düşük", lvl_medium: "Orta", lvl_high: "Yüksek", kbd_selected: "seçildi", legend: "Lejant", legend_show: "Lejantı göster", legend_hide: "Lejantı gizle", lg_zone: "Biçme bölgesi", lg_zone_pending: "Biçmek için seçildi", lg_mower: "Makinenin konumu", lg_dock: "Şarj istasyonu", lg_order: "Biçme sırası", lg_custom: "Bölgeye özel ayarlar", lg_direction: "Biçme yönü", lg_stuck: "Burada sıkıştı", lg_hotspot: "Burada arıza oluştu (tekrar sayısı)", lg_maint: "Bakım noktası", lg_passage: "Geçiş noktası", lg_nogo: "Yasak bölge", lg_wall: "Sanal duvar", lg_coverage: "Biçilen alan", lg_wifi: "Wi-Fi sinyali (yeşil = güçlü)", view_mode: "Görünüm", vw_beides: "İkisi de", vw_weg: "Rota", vw_flaeche: "Alan", vw_wlan: "Wi-Fi", vw_saison: "Sezon", lg_season: "Biçme sayısı (soluk = seyrek)", map_refreshing: "Harita yenileniyor…", dbg_title: "Alınan katmanlar", dbg_zones: "Bölgeler", dbg_nogo: "Yasak bölgeler", dbg_walls: "Duvarlar", dbg_obstacles: "Engeller", dbg_passthrough: "Geçiş bölgeleri", dbg_required: "Zorunlu", dbg_tunnels: "Tüneller", dbg_markers: "İşaretler", dbg_draw: "Çizilen alanlar", dbg_paths: "Rota noktaları", maint: "Bakım", maint_show: "Bakımı göster", maint_hide: "Bakımı gizle", maint_base: "Baz istasyonu", maint_blade: "Bıçaklar", maint_reset: "Sayacı sıfırla", maint_due: "şimdi gerekli", maint_reset_done: "Sayaç sıfırlandı" },
  uk: { no_map: "Мапа поки недоступна", not_connected: "Очікування даних газонокосарки…", start: "Косити", clear: "Очистити", zone: "зона", zones: "зони", reset_view: "Вписати мапу", reset_rotation: "Скинути до типового повороту", follow: "Слідкувати за косаркою", replay: "Відтворити цей сеанс", replay_play: "Запустити відтворення", start_mowing: "Почати косіння", pause: "Пауза", hud_progress: "Прогрес", hud_eta_left: "залишилось", dock: "Повернутися на базу", sent: "Косіння зон розпочато", preflight_none: "Недостатньо порівнюваної історії", preflight_estimate: "Оцінка", preflight_battery: "заряду", preflight_recharges: "підзарядок", preflight_daylight: "може завершитися після заходу сонця", missing_entity: "Вкажіть сутність газонокосарки TerraMow у налаштуваннях картки", zi_cut_height: "Висота скошування", zi_speed: "Швидкість скошування", zi_spacing: "Інтервал смуг", zi_blade: "Швидкість ножів", zi_edge: "Скошування країв", zi_direction: "Напрямок", zi_order: "Порядок скошування", zi_custom: "Власні налаштування", zi_global: "Загальні налаштування", lvl_low: "Низька", lvl_medium: "Середня", lvl_high: "Висока", kbd_selected: "вибрана", legend: "Легенда", legend_show: "Показати легенду", legend_hide: "Сховати легенду", lg_zone: "Зона скошування", lg_zone_pending: "Вибрана для скошування", lg_mower: "Положення косарки", lg_dock: "Зарядна станція", lg_order: "Порядок скошування", lg_custom: "Власні налаштування зони", lg_direction: "Напрямок скошування", lg_stuck: "Тут застрягла", lg_hotspot: "Тут стався збій (кількість)", lg_maint: "Точка обслуговування", lg_passage: "Точка проходу", lg_nogo: "Заборонена зона", lg_wall: "Віртуальна стіна", lg_coverage: "Скошена площа", lg_wifi: "Сигнал Wi-Fi (зелений = сильний)", view_mode: "Вигляд", vw_beides: "Обидва", vw_weg: "Шлях", vw_flaeche: "Площа", vw_wlan: "Wi-Fi", vw_saison: "Сезон", lg_season: "Кількість скошувань (блідий = рідко)", map_refreshing: "Мапа оновлюється…", dbg_title: "Отримані шари", dbg_zones: "Зони", dbg_nogo: "Заборонені зони", dbg_walls: "Стіни", dbg_obstacles: "Перешкоди", dbg_passthrough: "Зони проїзду", dbg_required: "Обов'язкові", dbg_tunnels: "Тунелі", dbg_markers: "Позначки", dbg_draw: "Намальовані області", dbg_paths: "Точки шляху", maint: "Обслуговування", maint_show: "Показати обслуговування", maint_hide: "Сховати обслуговування", maint_base: "Базова станція", maint_blade: "Ножі", maint_reset: "Скинути лічильник", maint_due: "потрібно зараз", maint_reset_done: "Лічильник скинуто" },
  "zh-Hans": { no_map: "暂无地图", not_connected: "等待割草机数据…", start: "开始割草", clear: "清除", zone: "个区域", zones: "个区域", reset_view: "适配地图视图", reset_rotation: "恢复默认旋转", follow: "跟随割草机", replay: "回放本次作业", replay_play: "开始回放", start_mowing: "开始割草", pause: "暂停", hud_progress: "进度", hud_eta_left: "剩余", dock: "返回充电站", sent: "已开始选区割草", preflight_none: "可比较的历史数据不足", preflight_estimate: "预计", preflight_battery: "电量", preflight_recharges: "次回充", preflight_daylight: "可能在日落后结束", missing_entity: "请在卡片配置中设置 TerraMow 割草机实体", zi_cut_height: "割草高度", zi_speed: "割草速度", zi_spacing: "割草间距", zi_blade: "刀盘转速", zi_edge: "沿边修剪", zi_direction: "方向", zi_order: "割草顺序", zi_custom: "自定义设置", zi_global: "全局设置", lvl_low: "低", lvl_medium: "中", lvl_high: "高", kbd_selected: "已选择", legend: "图例", legend_show: "显示图例", legend_hide: "隐藏图例", lg_zone: "割草分区", lg_zone_pending: "已选择割草", lg_mower: "割草机位置", lg_dock: "充电站", lg_order: "割草顺序", lg_custom: "分区自定义设置", lg_direction: "割草方向", lg_stuck: "在此被困", lg_hotspot: "此处发生故障（次数）", lg_maint: "维护点", lg_passage: "通道点", lg_nogo: "禁区", lg_wall: "虚拟墙", lg_coverage: "已割区域", lg_wifi: "Wi-Fi 信号（绿色＝强）", view_mode: "视图", vw_beides: "两者", vw_weg: "路径", vw_flaeche: "面积", vw_wlan: "Wi-Fi", vw_saison: "季节", lg_season: "割草次数（浅色＝较少）", map_refreshing: "地图刷新中…", dbg_title: "已接收图层", dbg_zones: "分区", dbg_nogo: "禁区", dbg_walls: "墙", dbg_obstacles: "障碍", dbg_passthrough: "可穿行区", dbg_required: "必割区", dbg_tunnels: "通道", dbg_markers: "标记", dbg_draw: "画区", dbg_paths: "路径点", maint: "维护", maint_show: "显示维护", maint_hide: "隐藏维护", maint_base: "基站", maint_blade: "刀盘", maint_reset: "重置计数", maint_due: "现在需要", maint_reset_done: "计数已重置" },
  "zh-Hant": { no_map: "尚無地圖", not_connected: "等待割草機資料…", start: "開始割草", clear: "清除", zone: "個區域", zones: "個區域", reset_view: "縮放至全圖", reset_rotation: "恢復預設旋轉", follow: "跟隨割草機", replay: "回放本次作業", replay_play: "開始回放", start_mowing: "開始割草", pause: "暫停", hud_progress: "進度", hud_eta_left: "剩餘", dock: "返回充電站", sent: "已開始選區割草", preflight_none: "可比較的歷史資料不足", preflight_estimate: "預計", preflight_battery: "電量", preflight_recharges: "次回充", preflight_daylight: "可能在日落後結束", missing_entity: "請在卡片設定中設定 TerraMow 割草機實體", zi_cut_height: "割草高度", zi_speed: "割草速度", zi_spacing: "割草間距", zi_blade: "刀盤轉速", zi_edge: "沿邊修剪", zi_direction: "方向", zi_order: "割草順序", zi_custom: "自訂設定", zi_global: "全域設定", lvl_low: "低", lvl_medium: "中", lvl_high: "高", kbd_selected: "已選擇", legend: "圖例", legend_show: "顯示圖例", legend_hide: "隱藏圖例", lg_zone: "割草分區", lg_zone_pending: "已選擇割草", lg_mower: "割草機位置", lg_dock: "充電站", lg_order: "割草順序", lg_custom: "分區自訂設定", lg_direction: "割草方向", lg_stuck: "在此受困", lg_hotspot: "此處發生故障（次數）", lg_maint: "維護點", lg_passage: "通道點", lg_nogo: "禁區", lg_wall: "虛擬牆", lg_coverage: "已割區域", lg_wifi: "Wi-Fi 訊號（綠色＝強）", view_mode: "檢視", vw_beides: "兩者", vw_weg: "路徑", vw_flaeche: "面積", vw_wlan: "Wi-Fi", vw_saison: "季節", lg_season: "割草次數（淺色＝較少）", map_refreshing: "地圖更新中…", dbg_title: "已接收圖層", dbg_zones: "分區", dbg_nogo: "禁區", dbg_walls: "牆", dbg_obstacles: "障礙", dbg_passthrough: "可穿行區", dbg_required: "必割區", dbg_tunnels: "通道", dbg_markers: "標記", dbg_draw: "畫區", dbg_paths: "路徑點", maint: "維護", maint_show: "顯示維護", maint_hide: "隱藏維護", maint_base: "基地台", maint_blade: "刀盤", maint_reset: "重設計數", maint_due: "現在需要", maint_reset_done: "計數已重設" },
};

function localize(hass, key) {
  const lang = (hass && hass.language) || "en";
  const table = STRINGS[lang] || STRINGS[lang.split("-")[0]] || STRINGS.en;
  return table[key] || STRINGS.en[key] || key;
}

/** "134 min" -> "2 h 14 min"; floors at 1 min (issue #198 ETA chip). */
function formatEtaMinutes(seconds) {
  const mins = Math.max(1, Math.round(seconds / 60));
  if (mins >= 60) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  return `${mins} min`;
}

/**
 * Remaining maintenance minutes as a short, readable span (issue #304). The
 * counters run to 14400 min (blade disc) and 43200 min (base station), and
 * "43200 min" tells nobody anything; the unit letters match the ETA chip's.
 */
function formatMaintenanceMinutes(minutes) {
  const mins = Math.max(0, Math.round(minutes));
  if (mins <= 0) {
    return "0 min";
  }
  if (mins >= 1440) {
    const d = Math.floor(mins / 1440);
    const h = Math.round((mins % 1440) / 60);
    return h ? `${d} d ${h} h` : `${d} d`;
  }
  return formatEtaMinutes(mins * 60);
}

/**
 * Localized noun for a count, choosing between the singular and plural
 * strings by the language's CLDR plural category rather than `n === 1`.
 * The table carries only two forms per language, so every non-"one"
 * category folds onto the plural — but this still fixes cases the naive
 * check gets wrong (e.g. Russian "21 зона" is the "one" form, Slavic and
 * Baltic zero is plural). Falls back to `n === 1` where Intl.PluralRules
 * is unavailable.
 */
function pluralWord(hass, count, oneKey, otherKey) {
  const lang = (hass && hass.language) || "en";
  let category = count === 1 ? "one" : "other";
  if (typeof Intl !== "undefined" && Intl.PluralRules) {
    try {
      category = new Intl.PluralRules(lang).select(count);
    } catch (_err) {
      /* keep the n === 1 fallback */
    }
  }
  return localize(hass, category === "one" ? oneKey : otherKey);
}

/* ---------------------------------------------------------------- icons */

// How long a full replay takes to watch, regardless of the track's length.
const REPLAY_SECONDS = 12;

const ICONS = {
  layers:
    "M12,16L19.36,10.27L21,9L12,2L3,9L4.63,10.27L12,16M12,18.54L4.62,12.81L3,14.07L12,21.07L21,14.07L19.37,12.81L12,18.54Z",
  play: "M8,5.14V19.14L19,12.14L8,5.14Z",
  replay:
    "M12,5V1L7,6L12,11V7A6,6 0 0,1 18,13A6,6 0 0,1 12,19A6,6 0 0,1 6,13H4A8,8 0 0,0 12,21A8,8 0 0,0 20,13A8,8 0 0,0 12,5Z",
  pause: "M14,19H18V5H14M6,19H10V5H6V19Z",
  dock: "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z",
  fit: "M9.5,13.09L10.92,14.5L6.41,19H10V21H3V14H5V17.59L9.5,13.09M10.91,9.5L9.5,10.91L5,6.41V10H3V3H10V5H6.41L10.91,9.5M14.5,13.09L19,17.59V14H21V21H14V19H17.59L13.08,14.5L14.5,13.09M13.09,9.5L17.59,5H14V3H21V10H19V6.41L14.5,10.91L13.09,9.5Z",
  follow: "M12,8A4,4 0 0,1 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12A4,4 0 0,1 12,8M3.05,13H1V11H3.05C3.5,6.83 6.83,3.5 11,3.05V1H13V3.05C17.17,3.5 20.5,6.83 20.95,11H23V13H20.95C20.5,17.17 17.17,20.5 13,20.95V23H11V20.95C6.83,20.5 3.5,17.17 3.05,13M12,5A7,7 0 0,0 5,12A7,7 0 0,0 12,19A7,7 0 0,0 19,12A7,7 0 0,0 12,5Z",
  battery: "M16,18H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  batteryCharging: "M16,20H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.66C6,21.4 6.6,22 7.33,22H16.66C17.4,22 18,21.4 18,20.66V5.33C18,4.6 17.4,4 16.67,4M11,20V14.5H9L13,7V12.5H15L11,20Z",
  legend: "M7,5H21V7H7V5M7,13V11H21V13H7M4,4.5A1.5,1.5 0 0,1 5.5,6A1.5,1.5 0 0,1 4,7.5A1.5,1.5 0 0,1 2.5,6A1.5,1.5 0 0,1 4,4.5M4,10.5A1.5,1.5 0 0,1 5.5,12A1.5,1.5 0 0,1 4,13.5A1.5,1.5 0 0,1 2.5,12A1.5,1.5 0 0,1 4,10.5M7,19V17H21V19H7M4,16.5A1.5,1.5 0 0,1 5.5,18A1.5,1.5 0 0,1 4,19.5A1.5,1.5 0 0,1 2.5,18A1.5,1.5 0 0,1 4,16.5Z",
  close: "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  wrench:
    "M22.7,19L13.6,9.9C14.5,7.6 14,4.9 12.1,3C10.1,1 7.1,0.6 4.7,1.7L9,6L6,9L1.6,4.7C0.4,7.1 0.9,10.1 2.9,12.1C4.8,14 7.5,14.5 9.8,13.6L18.9,22.7C19.3,23.1 19.9,23.1 20.3,22.7L22.6,20.4C23.1,20 23.1,19.3 22.7,19Z",
  restore:
    "M13,3A9,9 0 0,0 4,12H1L4.89,15.89L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3M12,8V13L16.28,15.54L17,14.33L13.5,12.25V8H12Z",
  refreshing: "M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12H4A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4Z",
  compass: "M14.19,14.19L6,18L9.81,9.81L18,6M12,10.9A1.1,1.1 0 0,0 10.9,12A1.1,1.1 0 0,0 12,13.1A1.1,1.1 0 0,0 13.1,12A1.1,1.1 0 0,0 12,10.9M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4Z",
};

function svgIcon(path) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${path}"/></svg>`;
}

/** Prefix -> the sensor translation_key whose entity-state translations carry
 *  the localized labels for that status enum (strings.json / translations/*).
 *  MISSION_STATE_ and SUB_MISSION_ must precede MISSION_ so the longer, more
 *  specific prefixes win. */
const STATUS_TRANSLATION_KEYS = [
  ["MISSION_STATE_", "mission_state"],
  ["SUB_MISSION_", "sub_mission"],
  ["BACK_TO_STATION_REASON_", "back_to_station_reason"],
  ["MISSION_", "mission"],
];

/** Turn a raw mission enum (e.g. "MISSION_GLOBAL_CLEAN") into readable text.
 *  Prefers the integration's own entity-state translation so the label follows
 *  the Home Assistant UI language (issue #248) — these are the same strings the
 *  mission/sub_mission/mission_state sensors already show. Falls back to
 *  stripping the known prefix and title-casing ("Global clean") when hass has
 *  no matching translation loaded (or none is passed). */
function prettyStatus(v, hass) {
  if (typeof v !== "string" || !v) {
    return "";
  }
  if (hass && typeof hass.localize === "function") {
    for (const [prefix, tkey] of STATUS_TRANSLATION_KEYS) {
      if (v.startsWith(prefix)) {
        const translated = hass.localize(
          `component.terramow.entity.sensor.${tkey}.state.${v.toLowerCase()}`
        );
        if (translated) {
          return translated;
        }
        break;
      }
    }
  }
  return v
    .replace(/^(MISSION_STATE_|SUB_MISSION_|MISSION_|BACK_TO_STATION_REASON_)/, "")
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());
}

/**
 * A 20×20 swatch mirroring an on-map glyph, for the legend. Colours come
 * from the resolved palette so the swatch matches the current theme exactly.
 * Shapes distinguish glyphs that share a colour (e.g. the orange custom-param
 * dot vs. the orange "got stuck" triangle).
 */
/** localStorage flag so the legend auto-opens only on a browser's first visit. */
const LEGEND_SEEN_KEY = "terramow-map-card:legend-seen";

/** The two maintenance counters the wrench panel shows, in display order:
 *  [role of the counter sensor, its label, role of its reset button]. The
 *  roles are the keys the backend fills with this install's entity ids
 *  (MAINTENANCE_ENTITY_SUFFIXES in map_card.py). */
const MAINT_ROWS = [
  ["base_station_time", "maint_base", "base_station_reset"],
  ["blade_time", "maint_blade", "blade_reset"],
];

/** A counter this far into its last stretch reads as "soon" (orange); at zero
 *  it is due (red). 10 % of the recommended cycle is about the last three days
 *  of base-station cleaning and the last 24 mowing hours of a blade disc —
 *  enough warning to order blades, not so much that it nags all season. */
const MAINT_SOON_FRACTION = 0.1;

/** Two-finger twist must exceed this (radians, ~7°) before rotation engages,
 *  so an ordinary pinch-zoom doesn't rotate the map by accident. */
const ROTATE_DEADZONE = 0.12;

/** localStorage key prefix (per entity) where the card mirrors its live
 *  rotation in whole degrees, so the config editor's "use current rotation"
 *  button can capture it — the editor and the preview card are isolated. */
const LIVE_ROT_KEY = "terramow-map-card:rot:";

/** localStorage key prefix (per entity) for the last picked overlay view mode,
 *  so the tap-to-cycle button remembers your choice across reloads. */
const VIEW_MODE_KEY = "terramow-map-card:view:";

/** Overlay view modes the on-map button cycles through. Each maps to a set of
 *  effective layer flags in _layers(); the button replaces needing separate
 *  dashboard views (or the show_* config flags) to switch what's drawn. */
const VIEW_MODES = ["beides", "weg", "flaeche", "wlan", "saison"];

/** Gap-fill the sparse Wi-Fi heatmap so a single (or interrupted) mow still
 *  reads as a continuous map: an empty grid cell surrounded by at least 3 of
 *  its 8 neighbours takes their average. Cells far from any sample stay empty
 *  — we fill holes between mow passes, never invent unmeasured ground. Returns
 *  `[gx, gy, pct, isFilled]` tuples. */
function interpolateWifiCells(cells) {
  const have = new Map();
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const [gx, gy, pct] of cells) {
    have.set(`${gx},${gy}`, pct);
    minX = Math.min(minX, gx);
    maxX = Math.max(maxX, gx);
    minY = Math.min(minY, gy);
    maxY = Math.max(maxY, gy);
  }
  const out = cells.map((c) => [c[0], c[1], c[2], false]);
  for (let gx = minX; gx <= maxX; gx++) {
    for (let gy = minY; gy <= maxY; gy++) {
      if (have.has(`${gx},${gy}`)) {
        continue;
      }
      let n = 0;
      let sum = 0;
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          if (dx === 0 && dy === 0) {
            continue;
          }
          const v = have.get(`${gx + dx},${gy + dy}`);
          if (v !== undefined) {
            n += 1;
            sum += v;
          }
        }
      }
      if (n >= 3) {
        out.push([gx, gy, sum / n, true]);
      }
    }
  }
  return out;
}

function legendSwatch(kind, c) {
  const out = c.markerOutline;
  const svg = (inner) =>
    `<svg viewBox="0 0 20 20" aria-hidden="true">${inner}</svg>`;
  switch (kind) {
    case "mower":
      // Match the on-map marker: a filled disc with a nose-up heading wedge.
      return svg(
        `<circle cx="10" cy="10" r="7" fill="${c.robot}" stroke="${c.bg}" stroke-width="1.2"/>` +
          `<path d="M10,3.6 L12.5,8.6 L7.5,8.6 Z" fill="${c.bg}"/>`
      );
    case "zone":
      return svg(
        `<rect x="3" y="4" width="14" height="12" rx="2" fill="${c.zoneFill}" stroke="${c.zoneEdge}" stroke-width="1.6"/>`
      );
    case "zone_selected":
      return svg(
        `<rect x="3" y="4" width="14" height="12" rx="2" fill="${c.zoneSelected}" stroke="${c.accent}" stroke-width="1.6"/>`
      );
    case "zone_pending":
      return svg(
        `<rect x="3" y="4" width="14" height="12" rx="2" fill="${c.zonePending}" stroke="${c.robot}" stroke-width="1.6"/>`
      );
    case "dock":
      // House = "home / charging base"; matches the on-map station glyph.
      return svg(
        `<path d="M10,3 L17,9.5 L3,9.5 Z" fill="${c.station}"/>` +
          `<rect x="5" y="9" width="10" height="7.5" fill="${c.station}"/>`
      );
    case "order":
      return svg(
        `<circle cx="10" cy="10" r="8" fill="${c.badgeOrder}" stroke="${out}" stroke-width="1.2"/>` +
          `<text x="10" y="10" font-size="11" font-weight="700" text-anchor="middle" dominant-baseline="central" fill="#fff">1</text>`
      );
    case "custom":
      return svg(
        `<circle cx="10" cy="10" r="5" fill="${c.markerTrapped}" stroke="${out}" stroke-width="1.2"/>`
      );
    case "direction":
      return svg(
        `<g stroke="${c.text}" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round">` +
          `<line x1="4" y1="10" x2="16" y2="10"/>` +
          `<polyline points="6.5,7 4,10 6.5,13"/>` +
          `<polyline points="13.5,7 16,10 13.5,13"/></g>`
      );
    case "stuck":
      return svg(
        `<path d="M10,3 L17,16 H3 Z" fill="${c.markerTrapped}" stroke="${out}" stroke-width="1.2" stroke-linejoin="round"/>`
      );
    case "hotspot":
      return svg(
        `<circle cx="10" cy="10" r="6.5" fill="none" stroke="${c.markerTrapped}" stroke-width="2"/>` +
          `<circle cx="10" cy="10" r="2" fill="${c.markerTrapped}"/>`
      );
    case "season":
      return svg(
        `<rect x="2" y="6" width="5" height="8" fill="hsla(140,70%,40%,.18)"/>` +
          `<rect x="7.5" y="6" width="5" height="8" fill="hsla(140,70%,40%,.4)"/>` +
          `<rect x="13" y="6" width="5" height="8" fill="hsla(140,70%,40%,.62)"/>`
      );
    case "maint":
      return svg(
        `<path d="M10,3 L16,6.5 V13.5 L10,17 L4,13.5 V6.5 Z" fill="${c.markerMaintenance}" stroke="${out}" stroke-width="1.2" stroke-linejoin="round"/>`
      );
    case "passage":
      return svg(
        `<path d="M10,3 L17,10 L10,17 L3,10 Z" fill="${c.accent}" stroke="${out}" stroke-width="1.2" stroke-linejoin="round"/>`
      );
    case "nogo":
      return svg(
        `<rect x="3" y="3" width="14" height="14" rx="2" fill="${c.forbidden}" stroke="${c.forbiddenEdge}" stroke-width="1.6"/>`
      );
    case "wall":
      return svg(
        `<line x1="3" y1="10" x2="17" y2="10" stroke="${c.wall}" stroke-width="2.4" stroke-dasharray="4 3" stroke-linecap="round"/>`
      );
    case "coverage":
      return svg(`<rect x="3" y="3" width="14" height="14" rx="2" fill="${c.coverage}"/>`);
    case "wifi":
      // Green-to-red gradient chip mirroring the heatmap cell colours.
      return svg(
        `<rect x="3" y="3" width="4" height="14" fill="hsla(120,75%,45%,0.8)"/>` +
          `<rect x="8" y="3" width="4" height="14" fill="hsla(60,75%,45%,0.8)"/>` +
          `<rect x="13" y="3" width="4" height="14" fill="hsla(0,75%,45%,0.8)"/>`
      );
    default:
      return svg("");
  }
}

/* ------------------------------------------------------------- geometry */

/** Ray-casting point-in-polygon. */
function pointInPolygon(x, y, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i][0];
    const yi = polygon[i][1];
    const xj = polygon[j][0];
    const yj = polygon[j][1];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** Shoelace area in the polygon's own units². */
function polygonArea(points) {
  let sum = 0;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    sum += points[j][0] * points[i][1] - points[i][0] * points[j][1];
  }
  return Math.abs(sum) / 2;
}

/** Zone area in m² (boundary minus holes; coordinates are mm). */
function zoneAreaM2(sub) {
  let area = polygonArea(sub.boundary || []);
  for (const hole of sub.inner_boundaries || []) {
    area -= polygonArea(hole);
  }
  return Math.max(0, area) / 1e6;
}

/** Nice scale-bar lengths in mm (0.1 m … 50 m). */
const SCALE_BAR_STEPS = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000];

/**
 * Upper bound on the points held for a single mow path. A long job streams
 * point deltas indefinitely; without a cap the arrays grow without limit and
 * every append re-strokes the whole polyline into the cached path layer.
 */
const MAX_PATH_POINTS = 6000;

/**
 * Halve a polyline's vertex density in place until it fits `cap`, keeping
 * every other point. At whole-lawn scale the coarser line is visually
 * indistinguishable, but memory and per-append redraw cost stay bounded.
 *
 * Empty `[]` run-break sentinels are always kept (dropping one would rejoin
 * two mowing runs into a phantom diagonal), as is the first real point after
 * a break so a run never loses its start vertex.
 */
function decimatePath(points, cap) {
  while (points.length > cap) {
    let write = 0;
    let keep = true;
    for (let read = 0; read < points.length; read++) {
      const p = points[read];
      if (!p || p.length !== 2) {
        points[write++] = p; // never drop a run break
        keep = true; // keep the first point of the next run
        continue;
      }
      if (keep) {
        points[write++] = p;
      }
      keep = !keep;
    }
    if (write >= points.length) {
      break; // nothing removed (all sentinels) — avoid an infinite loop
    }
    points.length = write;
  }
}

/** Activities and their marker/chip colors (light, dark). */
const ACTIVITY_COLORS = {
  mowing: ["#2e7d32", "#81c784"],
  paused: ["#ef6c00", "#ffb74d"],
  returning: ["#0277bd", "#4fc3f7"],
  docked: ["#616161", "#b0bec5"],
  error: ["#c62828", "#e57373"],
};

/* ------------------------------------------------------------ the card */

// Scene memo keyed by entity id. It survives the card element being destroyed
// and recreated within the same document (the JS module stays loaded), so
// swiping back to the map view on mobile repaints the last scene instantly
// instead of blanking to "Waiting for mower data…" while the WebSocket
// re-subscribes and the server rebuilds the scene from scratch.
const SCENE_MEMO = new Map();

/** Last fully-rendered frame per entity, as a data URL. The browser does NOT
 *  keep canvas pixels when the card element is destroyed and recreated (which
 *  Home Assistant does on every dashboard switch), so a freshly mounted card
 *  shows a blank canvas for a frame or two before its first draw completes —
 *  the flicker. Painting this cached frame as an overlay the instant the card
 *  mounts, then fading it out once the live canvas has drawn, hides that gap.
 *  Module-level, so it survives the element being recreated. */
const FRAME_MEMO = new Map();

class TerramowMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scene = null;
    this._sceneRev = 0;
    this._pathRev = 0;
    this._robot = null;
    this._battery = null;
    this._work = null;
    this._status = null;
    this._errors = null;
    // {role: entity_id} of this mower's maintenance counters and reset
    // buttons, sent by the backend; null until the first robot event.
    this._maintenance = null;
    this._maintSig = null; // last seen counter states, to gate re-renders
    this._robotPrev = null;
    this._robotAnimStart = 0;
    this._view = null; // {scale, tx, ty}
    // Whether _view is still the automatic fit rather than one the user chose.
    // Only an automatic view may be recomputed when the card is resized: the
    // first fit can land on a provisional size and stick (issue #327), but a
    // view someone panned or zoomed to is theirs to keep.
    this._viewIsAuto = true;
    // The box the automatic view was framed against, so a later scene that
    // reframes the lawn can be told from one that merely moved the mower.
    this._fitBox = null;
    this._follow = false;
    this._pending = new Set(); // sub-region ids tapped by the user
    this._pointers = new Map();
    this._dragged = false;
    this._pinchStart = null;
    this._baseRot = 0; // configured rotation (radians); compass resets here
    this._focusedZoneId = null; // keyboard-focused sub-region id
    this._lastPersistedRot = null; // last live rotation mirrored to storage
    this._unsub = null;
    this._subscribedEntity = null;
    this._resizeObserver = null;
    this._rafHandle = 0;
    this._lastFrameTs = 0;
    this._lastEntityState = null;
    this._staticCache = null; // {canvas, sig, view}
    // Session replay: index is a point count into the session track, so the
    // path layer can be clipped to "as far as the mower had got".
    this._replay = { active: false, playing: false, index: 0, timer: null };
    this._pathCache = null; // {canvas, sig, view}
    this._layerView = null; // view the offscreen layers were rasterized at
    this._viewMode = null; // overlay mode (VIEW_MODES); set from storage/config
    this._frameStamp = 0; // last time the rendered frame was cached (throttle)
    this._colorCache = null; // resolved theme colors; invalidated on theme change
    this._themeSig = null;
    this._onVisibility = () => {
      if (document.visibilityState === "hidden") {
        this._teardownSubscription();
      } else {
        this._resubscribe();
        this._requestDraw();
      }
    };
  }

  /* ---------------------------------------------------------- card API */

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("terramow-map-card: 'entity' is required");
    }
    this._config = {
      show_history_path: true,
      show_current_path: true,
      show_coverage: false,
      show_wifi: false,
      zone_selection: true,
      show_hud: true,
      show_maintenance: true,
      show_controls: true,
      show_markers: true,
      show_replay: true,
      show_hotspots: true,
      show_direction: true,
      zone_info: true,
      show_layer_counts: false,
      rotate_gesture: true,
      rotation: 0,
      fit_height: 420,
      fit_padding: 0.95,
      ...config,
    };
    this._rot = ((Number(this._config.rotation) || 0) * Math.PI) / 180;
    this._baseRot = this._rot;
    this._buildDom();
    this._staticCache = null;
    this._pathCache = null;
    this._resubscribe();
    this._requestDraw();
  }

  set hass(hass) {
    const firstHass = !this._hass;
    this._hass = hass;
    if (!this._unsub) {
      this._resubscribe();
    }
    if (firstHass) {
      this._updateModeBtn(); // localize the mode label once hass is available
    }
    const themeSig = this._themeSignature(hass);
    if (themeSig !== this._themeSig) {
      this._themeSig = themeSig;
      this._colorCache = null; // re-resolve theme colors on the next draw
      this._updateHud();
      this._requestDraw();
    }
    const state = hass && hass.states[this._config?.entity];
    const stateStr = state ? `${state.state}` : null;
    if (stateStr !== this._lastEntityState) {
      this._lastEntityState = stateStr;
      this._updateHud();
      this._updateControls();
      this._requestDraw(); // marker tint follows the activity
    }
    // The maintenance counters live in hass.states, not in the map feed, and
    // every state change in the whole system lands here — so re-render only
    // when one of the two counters actually moved.
    const maintSig = this._maintSignature();
    if (maintSig !== this._maintSig) {
      this._maintSig = maintSig;
      this._updateMaintBtn();
    }
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find((id) =>
      id.startsWith("lawn_mower.")
    );
    return { entity: entity || "" };
  }

  static getConfigElement() {
    return document.createElement(`${CARD_TAG}-editor`);
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisibility);
    this._colorCache = null; // CSS custom props only resolve while connected
    this._showFrameCache(); // paint the last frame at once → no mount flicker
    this._restoreMemoScene();
    this._resubscribe();
  }

  /** Show the last rendered frame (if any) over the still-blank canvas the
   *  instant the card mounts; the first live _draw fades it out. */
  _showFrameCache() {
    if (!this._frameImg || !this._config) {
      return;
    }
    const url = FRAME_MEMO.get(this._config.entity);
    if (url) {
      this._frameImg.src = url;
      this._frameImg.classList.add("show");
    }
  }

  /**
   * Repaint the last known scene for this entity instantly when a freshly
   * created element (e.g. after a mobile view swipe) has no scene yet. Avoids
   * the "Waiting for mower data…" blank while the subscription re-establishes;
   * the live feed replaces this with a fresh scene moments later.
   */
  _restoreMemoScene() {
    if (this._scene || !this._config || !this._config.entity) {
      return;
    }
    const memo = SCENE_MEMO.get(this._config.entity);
    if (!memo) {
      return;
    }
    this._scene = memo;
    this._sceneRev += 1;
    this._pathRev += 1;
    if (this._hasGeometry()) {
      this._fitView();
    }
    this._updateHud();
    this._requestDraw();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    // A replay left running would keep ticking on a card nobody is looking at.
    this._setReplayPlaying(false);
    this._teardownSubscription();
  }

  _activity() {
    const state = this._hass && this._hass.states[this._config?.entity];
    return state ? state.state : null;
  }

  /* ------------------------------------------------------ subscription */

  async _resubscribe() {
    if (!this._hass || !this._config || !this.isConnected) {
      return;
    }
    if (document.visibilityState === "hidden") {
      return; // resubscribed by _onVisibility when shown again
    }
    if (this._subscribedEntity === this._config.entity && this._unsub) {
      return;
    }
    this._teardownSubscription();
    this._subscribedEntity = this._config.entity;
    try {
      this._unsub = await this._hass.connection.subscribeMessage(
        (msg) => this._onFeedMessage(msg),
        { type: "terramow/map/subscribe", entity_id: this._config.entity }
      );
    } catch (err) {
      this._subscribedEntity = null;
      this._showMessage(
        (err && err.message) || localize(this._hass, "not_connected")
      );
    }
  }

  _teardownSubscription() {
    if (this._unsub) {
      const unsub = this._unsub;
      this._unsub = null;
      this._subscribedEntity = null;
      Promise.resolve()
        .then(() => unsub())
        .catch(() => {});
    }
  }

  _onFeedMessage(msg) {
    if (msg.type === "scene") {
      const hadScene = this._hasGeometry();
      this._scene = msg.scene;
      if (Array.isArray(this._scene.current_path)) {
        decimatePath(this._scene.current_path, MAX_PATH_POINTS);
      }
      if (Array.isArray(this._scene.history_path)) {
        decimatePath(this._scene.history_path, MAX_PATH_POINTS);
      }
      if (Array.isArray(this._scene.session_paths)) {
        for (const segment of this._scene.session_paths) {
          decimatePath(segment, MAX_PATH_POINTS);
        }
      }
      if (this._config && this._config.entity) {
        SCENE_MEMO.set(this._config.entity, this._scene);
      }
      this._sceneRev += 1;
      this._pathRev += 1;
      this._pruneStaleSelection();
      // Re-frame whenever the geometry the automatic view was fitted to has
      // changed, not just on the first scene: the first one can carry nothing
      // but the scanned extent, and that fit must not stand (issue #327).
      if (this._hasGeometry() && (!hadScene || this._fitBasisChanged())) {
        this._fitView();
      }
      this._updateHud();
      if (this._legend && this._legend.classList.contains("visible")) {
        this._buildLegend();
      }
      this._maybeAutoOpenLegend();
      this._requestDraw();
    } else if (msg.type === "paths_append") {
      if (!this._scene) {
        return;
      }
      if (Array.isArray(msg.current_path_append)) {
        this._scene.current_path.push(...msg.current_path_append);
        decimatePath(this._scene.current_path, MAX_PATH_POINTS);
      }
      if (Array.isArray(msg.history_path_append)) {
        this._scene.history_path.push(...msg.history_path_append);
        decimatePath(this._scene.history_path, MAX_PATH_POINTS);
      }
      if (msg.wifi_heatmap !== undefined) {
        // The heatmap rides the append channel whole (it is small); it is
        // drawn in the path layer, so the path revision covers it.
        this._scene.wifi_heatmap = msg.wifi_heatmap;
      }
      this._pathRev += 1;
      this._requestDraw();
    } else if (msg.type === "robot") {
      if (
        this._robot &&
        msg.robot &&
        (this._robot.x !== msg.robot.x || this._robot.y !== msg.robot.y)
      ) {
        this._robotPrev = this._robot;
        this._robotAnimStart = performance.now();
      }
      this._robot = msg.robot;
      this._battery = msg.battery || null;
      this._work = msg.work || null;
      this._status = msg.status || null;
      this._errors = msg.errors || null;
      this._preflight = msg.preflight || {};
      this._maintenance = msg.maintenance || null;
      if (this._follow && this._robot) {
        this._centerOnRobot();
      }
      this._updateMaintBtn();
      this._updateHud();
      this._updateButtons();
      this._updateActionBar();
      this._requestDraw();
    }
  }

  _hasGeometry() {
    const scene = this._scene;
    return Boolean(
      scene &&
        scene.bounds &&
        (scene.regions.length || scene.map_extent.length)
    );
  }

  _pruneStaleSelection() {
    if (!this._pending.size) {
      return;
    }
    const known = new Set();
    for (const region of this._scene?.regions || []) {
      for (const sub of region.sub_regions) {
        if (sub.id !== null) {
          known.add(sub.id);
        }
      }
    }
    for (const id of [...this._pending]) {
      if (!known.has(id)) {
        this._pending.delete(id);
      }
    }
    this._updateActionBar();
    this._updateReplayBtn();
  }

  /* --------------------------------------------------------------- DOM */

  /**
   * The card height: the configured fit_height, clamped to the viewport so
   * a large value (e.g. the docs' 900px panel view) can never push the
   * bottom selection bar below the fold on small screens.
   */
  _applyCardHeight(el) {
    // Clamp to the *visible* viewport so a large fit_height (e.g. the docs'
    // 900px panel view) can never push the bottom mow controls below the
    // fold. `dvh` (dynamic viewport height) excludes the mobile browser's
    // URL bar / bottom nav; `vh` counts the area behind them and would cut
    // the controls off. Assign `vh` first as a fallback, then `dvh` — the
    // second assignment is silently rejected on browsers without `dvh`,
    // leaving the `vh` value in place.
    const px = Number(this._config.fit_height) || 420;
    el.style.height = `min(${px}px, calc(100vh - 96px))`;
    el.style.height = `min(${px}px, calc(100dvh - 96px))`;
  }

  _buildDom() {
    if (this._root) {
      this._applyCardHeight(this._root);
      this._updateHud();
      this._updateControls();
      return;
    }
    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; }
      ha-card { overflow: hidden; position: relative; }
      .wrap { position: relative; width: 100%; touch-action: none; }
      canvas.main { display: block; width: 100%; height: 100%; cursor: grab; }
      canvas.main.dragging { cursor: grabbing; }
      .framecache {
        position: absolute; inset: 0; width: 100%; height: 100%;
        object-fit: contain; pointer-events: none;
        opacity: 0; transition: opacity .12s ease-out;
      }
      .framecache.show { opacity: 1; }
      canvas.main:focus { outline: none; }
      canvas.main:focus-visible {
        outline: 2px solid var(--primary-color, #03a9f4); outline-offset: -3px;
      }
      .sr-only {
        position: absolute; width: 1px; height: 1px; overflow: hidden;
        clip: rect(0 0 0 0); white-space: nowrap; border: 0; padding: 0; margin: -1px;
      }
      .hud {
        position: absolute; top: 8px; left: 8px; display: flex; gap: 6px;
        flex-wrap: wrap; pointer-events: none; max-width: calc(100% - 56px);
      }
      .chip {
        display: inline-flex; align-items: center; gap: 5px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        border-radius: 14px; padding: 3px 10px; font-size: 12px;
        opacity: .92; white-space: nowrap; line-height: 1.4;
      }
      .chip svg { width: 13px; height: 13px; }
      .chip.error {
        background: #c62828; color: #fff; border-color: #c62828;
        font-weight: 600; opacity: 1;
      }
      .chip .dot {
        width: 8px; height: 8px; border-radius: 50%; flex: none;
        background: var(--secondary-text-color, #727272);
      }
      .chip.state { text-transform: capitalize; }
      .chip.warn {
        border-color: var(--warning-color, #ffa726);
        color: var(--warning-color, #ffa726);
      }
      .chip.warn svg { width: 13px; height: 13px; }
      .chip.map .m-name + .m-area::before { content: " · "; }
      /* Narrow (phone) cards: drop the map name, keep just the area to save
         space; hide the chip entirely only if there's no area to show. */
      .wrap.narrow .chip.map .m-name { display: none; }
      .wrap.narrow .chip.map .m-name + .m-area::before { content: ""; }
      .wrap.narrow .chip.map:not(:has(.m-area)) { display: none; }
      .side {
        position: absolute; top: 8px; right: 8px; display: flex;
        flex-direction: column; gap: 6px;
      }
      .rbtn {
        width: 34px; height: 34px; border-radius: 50%;
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        cursor: pointer; opacity: .92; padding: 0;
        display: inline-flex; align-items: center; justify-content: center;
      }
      .rbtn svg { width: 18px; height: 18px; }
      .rbtn.mode {
        width: auto; border-radius: 17px; padding: 0 11px 0 8px;
        gap: 5px; font-size: 12px; font-weight: 600; white-space: nowrap;
      }
      .rbtn:hover { opacity: 1; }
      .rbtn:focus-visible, .actions button:focus-visible {
        outline: 2px solid var(--primary-color, #03a9f4);
        outline-offset: 2px;
      }
      .rbtn.active {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .controls {
        position: absolute; right: 8px; bottom: 10px; display: flex;
        gap: 8px;
      }
      .wrap.selecting .controls { display: none; }
      .controls .rbtn { width: 40px; height: 40px; opacity: .95; }
      .controls .rbtn.primary {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .actions {
        position: absolute; left: 50%; bottom: 10px; transform: translateX(-50%);
        display: none; align-items: center; gap: 8px; max-width: calc(100% - 20px);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        border-radius: 22px; padding: 6px 8px 6px 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,.18);
      }
      .actions.visible { display: flex; }
      .actions .names {
        font-size: 12px; color: var(--primary-text-color, #212121);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        max-width: 42vw;
      }
      .actions .preflight {
        font-size: 11px; color: var(--secondary-text-color, #727272);
        white-space: nowrap;
      }
      .actions button {
        border: none; border-radius: 16px; padding: 6px 14px; font-size: 13px;
        cursor: pointer; white-space: nowrap;
      }
      .actions .go {
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff); font-weight: 600;
      }
      .actions .clear {
        background: transparent; color: var(--secondary-text-color, #727272);
      }
      .msg {
        position: absolute; inset: 0; display: flex; align-items: center;
        justify-content: center; font-size: 14px; text-align: center;
        color: var(--secondary-text-color, #727272); pointer-events: none;
        padding: 0 16px;
      }
      .zoneinfo {
        position: absolute; top: 10px; left: 10px; display: none;
        min-width: 190px; max-width: min(65vw, 280px);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        border-radius: 12px; padding: 10px 14px;
        box-shadow: 0 2px 10px rgba(0,0,0,.22);
        font-size: 12px; color: var(--primary-text-color, #212121);
        z-index: 3;
      }
      .zoneinfo.visible { display: block; }
      .zoneinfo .zi-title {
        font-size: 13px; font-weight: 600; margin-bottom: 6px;
        display: flex; justify-content: space-between; gap: 10px;
      }
      .zoneinfo .zi-title .zi-area {
        font-weight: 400; color: var(--secondary-text-color, #727272);
      }
      .zoneinfo .zi-row {
        display: flex; justify-content: space-between; gap: 14px;
        padding: 1.5px 0;
      }
      .zoneinfo .zi-row .zi-label {
        color: var(--secondary-text-color, #727272);
      }
      .zoneinfo .zi-scope {
        margin-top: 6px; font-size: 11px;
        color: var(--secondary-text-color, #727272);
      }
      .replay {
        position: absolute; left: 50%; bottom: 8px; transform: translateX(-50%);
        display: flex; align-items: center; gap: 8px; z-index: 3;
        padding: 4px 10px 4px 4px; border-radius: 20px;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        box-shadow: 0 2px 10px rgba(0,0,0,.22);
        max-width: min(90%, 320px);
      }
      .replay .rp-play {
        display: flex; align-items: center; justify-content: center;
        width: 30px; height: 30px; flex: none; padding: 0;
        border: none; border-radius: 50%; cursor: pointer;
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .replay .rp-play svg { width: 18px; height: 18px; }
      .replay input[type="range"] { flex: 1; min-width: 90px; accent-color: var(--primary-color, #03a9f4); }
      .replay .rp-label {
        font-size: 12px; min-width: 34px; text-align: right;
        color: var(--secondary-text-color, #727272); font-variant-numeric: tabular-nums;
      }
      .legend-btn {
        position: absolute; left: 8px; bottom: 32px; z-index: 3;
      }
      .legend {
        position: absolute; left: 8px; bottom: 72px; display: none;
        min-width: 168px; max-width: min(70vw, 250px);
        max-height: calc(100% - 100px); overflow: auto;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        border-radius: 12px; padding: 8px 12px 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,.22);
        font-size: 12px; color: var(--primary-text-color, #212121);
        z-index: 3;
      }
      .legend.visible { display: block; }
      .legend .lg-head {
        display: flex; align-items: center; justify-content: space-between;
        gap: 10px; font-weight: 600; font-size: 13px; margin-bottom: 6px;
      }
      .legend .lg-head button {
        border: none; background: transparent; cursor: pointer; padding: 2px;
        color: var(--secondary-text-color, #727272); line-height: 0;
      }
      .legend .lg-head button svg { width: 16px; height: 16px; }
      .legend .lg-row {
        display: flex; align-items: center; gap: 9px; padding: 2.5px 0;
      }
      .legend .lg-sw {
        width: 20px; height: 20px; flex: none;
        display: inline-flex; align-items: center; justify-content: center;
      }
      .legend .lg-sw svg { width: 20px; height: 20px; display: block; }
      .legend .lg-sec {
        margin: 8px 0 3px; padding-top: 7px; font-weight: 600; font-size: 11px;
        border-top: 1px solid var(--divider-color, rgba(0,0,0,.12));
        color: var(--secondary-text-color, #727272);
      }
      .legend .lg-cnt {
        display: flex; justify-content: space-between; gap: 14px; padding: 1.5px 0;
      }
      .legend .lg-cnt.zero { color: var(--secondary-text-color, #727272); opacity: .6; }
      .legend .lg-cnt .lg-n { font-variant-numeric: tabular-nums; }
      /* Maintenance: the wrench sits beside the legend button and shares the
         panel spot above it (only one of the two is ever open). */
      .maint-btn { position: absolute; left: 50px; bottom: 32px; z-index: 3; }
      .maint-btn.soon {
        border-color: var(--warning-color, #ffa726);
        color: var(--warning-color, #ffa726);
      }
      .maint-btn.due {
        border-color: var(--error-color, #db4437);
        color: var(--error-color, #db4437);
        animation: tm-maint-pulse 2s ease-in-out infinite;
      }
      .maint-btn.due.active { animation: none; }
      @keyframes tm-maint-pulse {
        0%, 100% { opacity: .92; }
        50% { opacity: .45; }
      }
      @media (prefers-reduced-motion: reduce) {
        .maint-btn.due { animation: none; }
      }
      .maint .mt-row {
        display: flex; align-items: center; gap: 8px; padding: 3px 0;
      }
      .maint .mt-cell {
        flex: 1; min-width: 0; display: flex; flex-direction: column;
        background: transparent; border: none; padding: 0; cursor: pointer;
        color: inherit; font: inherit; text-align: left;
      }
      .maint .mt-label { color: var(--secondary-text-color, #727272); }
      .maint .mt-value { font-variant-numeric: tabular-nums; }
      .maint .mt-row.soon .mt-value { color: var(--warning-color, #ffa726); }
      .maint .mt-row.due .mt-value {
        color: var(--error-color, #db4437); font-weight: 600;
      }
      .maint .mt-reset {
        flex: none; width: 28px; height: 28px; border-radius: 50%;
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        cursor: pointer; padding: 0; line-height: 0;
        display: inline-flex; align-items: center; justify-content: center;
      }
      .maint .mt-reset svg { width: 16px; height: 16px; }
      .maint .mt-reset:hover { border-color: var(--primary-color, #03a9f4); }
    `;

    const card = document.createElement("ha-card");
    const wrap = document.createElement("div");
    wrap.className = "wrap";
    this._applyCardHeight(wrap);
    this._root = wrap;

    this._canvas = document.createElement("canvas");
    this._canvas.className = "main";
    // The canvas is a status surface for assistive tech; the actionable
    // controls live in the labelled button rows beside it. When zone
    // selection is on it is also a keyboard widget (arrow keys cycle zones,
    // Enter toggles) so it takes focus.
    this._canvas.setAttribute("role", "img");
    if (this._config.zone_selection) {
      this._canvas.tabIndex = 0;
    }
    wrap.appendChild(this._canvas);

    // Overlay that shows the last rendered frame the instant the card mounts,
    // hiding the blank-canvas flicker on a dashboard switch (see FRAME_MEMO).
    this._frameImg = document.createElement("img");
    this._frameImg.className = "framecache";
    this._frameImg.alt = "";
    wrap.appendChild(this._frameImg);

    // Off-screen live region announcing the keyboard-focused zone.
    this._srLive = document.createElement("div");
    this._srLive.className = "sr-only";
    this._srLive.setAttribute("aria-live", "polite");
    wrap.appendChild(this._srLive);

    this._hud = document.createElement("div");
    this._hud.className = "hud";
    wrap.appendChild(this._hud);

    // top-right: fit + follow
    const side = document.createElement("div");
    side.className = "side";
    this._fitBtn = this._roundButton(ICONS.fit, () => {
      this._setFollow(false);
      this._fitView();
      this._requestDraw();
    });
    this._followBtn = this._roundButton(ICONS.follow, () => {
      this._setFollow(!this._follow);
    });
    this._followBtn.style.display = "none";
    this._compassBtn = this._roundButton(ICONS.compass, () => {
      this._setFollow(false);
      this._resetRotation();
    });
    this._compassBtn.style.display = "none";
    const resetRotLabel = localize(this._hass, "reset_rotation");
    this._compassBtn.title = resetRotLabel;
    this._compassBtn.setAttribute("aria-label", resetRotLabel);
    this._compassBtn.querySelector("svg").style.transition = "transform .15s";
    // Overlay view toggle (path / area / both / Wi-Fi) — one tap cycles what's
    // drawn, so a single card replaces separate dashboard views.
    // Session replay: scrub through the track the mower actually drove this
    // session. Purely a view of data the card already has — no extra traffic.
    this._replayBtn = this._roundButton(ICONS.replay, () => this._toggleReplay());
    this._replayBtn.style.display = "none";
    this._modeBtn = this._roundButton(ICONS.layers, () => this._cycleViewMode());
    this._modeBtn.classList.add("mode");
    this._initViewMode();
    this._updateModeBtn();
    side.append(
      this._modeBtn,
      this._replayBtn,
      this._fitBtn,
      this._followBtn,
      this._compassBtn
    );
    wrap.appendChild(side);

    // bottom-right: contextual mow controls
    this._controls = document.createElement("div");
    this._controls.className = "controls";
    wrap.appendChild(this._controls);

    this._actionBar = document.createElement("div");
    this._actionBar.className = "actions";
    this._actionNames = document.createElement("span");
    this._actionNames.className = "names";
    this._preflightText = document.createElement("span");
    this._preflightText.className = "preflight";
    this._goBtn = document.createElement("button");
    this._goBtn.className = "go";
    this._goBtn.addEventListener("click", () => this._startSelectedZones());
    this._clearBtn = document.createElement("button");
    this._clearBtn.className = "clear";
    this._clearBtn.addEventListener("click", () => {
      this._pending.clear();
      this._updateActionBar();
      this._requestDraw();
    });
    this._actionBar.append(
      this._actionNames,
      this._preflightText,
      this._goBtn,
      this._clearBtn
    );
    wrap.appendChild(this._actionBar);

    this._infoPanel = document.createElement("div");
    this._infoPanel.className = "zoneinfo";
    wrap.appendChild(this._infoPanel);

    // bottom-left (above the scale bar): collapsible legend
    this._legend = document.createElement("div");
    this._legend.className = "legend";
    wrap.appendChild(this._legend);
    this._legendBtn = this._roundButton(ICONS.legend, () => this._toggleLegend());
    this._legendBtn.classList.add("legend-btn");
    this._legendBtn.setAttribute("aria-expanded", "false");
    const legendLabel = localize(this._hass, "legend_show");
    this._legendBtn.title = legendLabel;
    this._legendBtn.setAttribute("aria-label", legendLabel);
    wrap.appendChild(this._legendBtn);

    // Beside it: the maintenance panel (issue #304). It borrows the legend's
    // box styling — same place, same collapse behaviour — and is shown only
    // once the feed has named this install's counter entities.
    this._maintPanel = document.createElement("div");
    this._maintPanel.className = "legend maint";
    wrap.appendChild(this._maintPanel);
    this._maintBtn = this._roundButton(ICONS.wrench, () => this._toggleMaint());
    this._maintBtn.classList.add("maint-btn");
    this._maintBtn.setAttribute("aria-expanded", "false");
    this._maintBtn.style.display = "none";
    wrap.appendChild(this._maintBtn);

    // bottom-centre: the replay scrubber, shown only while replay is on
    this._replayBar = document.createElement("div");
    this._replayBar.className = "replay";
    this._replayBar.style.display = "none";
    this._replayPlayBtn = document.createElement("button");
    this._replayPlayBtn.className = "rp-play";
    this._replayPlayBtn.addEventListener("click", () =>
      this._setReplayPlaying(!this._replay.playing)
    );
    this._replaySlider = document.createElement("input");
    this._replaySlider.type = "range";
    this._replaySlider.min = "0";
    this._replaySlider.step = "1";
    this._replaySlider.addEventListener("input", () => {
      // Dragging takes over from playback: the user is steering now.
      this._setReplayPlaying(false);
      this._replay.index = Number(this._replaySlider.value);
      this._requestDraw();
    });
    this._replayLabel = document.createElement("span");
    this._replayLabel.className = "rp-label";
    this._replayBar.append(
      this._replayPlayBtn,
      this._replaySlider,
      this._replayLabel
    );
    wrap.appendChild(this._replayBar);

    this._msg = document.createElement("div");
    this._msg.className = "msg";
    wrap.appendChild(this._msg);

    card.appendChild(wrap);
    this.shadowRoot.replaceChildren(style, card);

    this._bindPointerEvents();
    this._resizeObserver = new ResizeObserver(() => {
      this._root.classList.toggle("narrow", this._root.clientWidth < 420);
      this._syncCanvasSize();
      this._refitOnResize();
      this._requestDraw();
    });
    this._resizeObserver.observe(wrap);
    this._syncCanvasSize();
    this._updateHud();
    this._updateControls();
    this._updateCompass();
    this._updateMaintBtn();
    this._requestDraw();
  }

  _roundButton(iconPath, onClick) {
    const btn = document.createElement("button");
    btn.className = "rbtn";
    btn.innerHTML = svgIcon(iconPath);
    btn.addEventListener("click", onClick);
    return btn;
  }

  /* --------------------------------------------------------- view modes */

  _initViewMode() {
    let mode = null;
    try {
      mode = window.localStorage.getItem(VIEW_MODE_KEY + this._config.entity);
    } catch (e) {
      /* storage blocked (private mode) — fall through to the config default */
    }
    this._viewMode = VIEW_MODES.includes(mode) ? mode : this._deriveViewMode();
  }

  /** Seed the initial mode from the show_* config flags, so cards/dashboards
   *  that used them to pick what to draw keep their look on first load. */
  _deriveViewMode() {
    const c = this._config;
    if (
      c.show_wifi &&
      !c.show_coverage &&
      !c.show_current_path &&
      !c.show_history_path
    ) {
      return "wlan";
    }
    if (c.show_coverage && !c.show_current_path && !c.show_history_path) {
      return "flaeche";
    }
    return c.show_coverage ? "beides" : "weg";
  }

  _cycleViewMode() {
    const i = VIEW_MODES.indexOf(this._viewMode);
    this._viewMode = VIEW_MODES[(i + 1) % VIEW_MODES.length];
    try {
      window.localStorage.setItem(
        VIEW_MODE_KEY + this._config.entity,
        this._viewMode
      );
    } catch (e) {
      /* storage blocked; the choice just won't persist across reloads */
    }
    this._updateModeBtn();
    if (this._legend && this._legend.classList.contains("visible")) {
      this._buildLegend();
    }
    this._requestDraw();
  }

  /** Effective layer flags for the active view mode. */
  _layers() {
    switch (this._viewMode) {
      case "wlan":
        return { coverage: false, history: false, current: false, wifi: true, season: false };
      case "saison":
        // The season heatmap alone: any live track drawn over it would be
        // read as part of the pattern.
        return { coverage: false, history: false, current: false, wifi: false, season: true };
      case "flaeche":
        return { coverage: true, history: false, current: false, wifi: false, season: false };
      case "weg":
        return { coverage: false, history: true, current: true, wifi: false, season: false };
      default: // beides
        return { coverage: true, history: true, current: true, wifi: false, season: false };
    }
  }

  /**
   * The track the mower drove this session, in the order it drove it:
   * the legs archived before a mid-session dock, then the live path.
   * The previous session's history path is deliberately excluded — replaying
   * "this mow" must not sweep in the last one.
   */
  _replayRuns() {
    const scene = this._scene;
    if (!scene) {
      return [];
    }
    const runs = [];
    for (const segment of scene.session_paths || []) {
      if (Array.isArray(segment) && segment.length) {
        runs.push(segment);
      }
    }
    if (Array.isArray(scene.current_path) && scene.current_path.length) {
      runs.push(scene.current_path);
    }
    return runs;
  }

  _replayTotal() {
    return this._replayRuns().reduce((sum, run) => sum + run.length, 0);
  }

  /** The runs truncated to the first `upto` points overall. */
  _clipRuns(runs, upto) {
    const clipped = [];
    let left = upto;
    for (const run of runs) {
      if (left <= 0) {
        break;
      }
      clipped.push(left >= run.length ? run : run.slice(0, left));
      left -= run.length;
    }
    return clipped;
  }

  /** Show the replay button only when there is a track worth replaying. */
  _updateReplayBtn() {
    if (!this._replayBtn) {
      return;
    }
    const available = Boolean(this._config.show_replay) && this._replayTotal() > 1;
    this._replayBtn.style.display = available ? "" : "none";
    if (!available && this._replay.active) {
      this._exitReplay();
    }
    const label = localize(this._hass, "replay");
    this._replayBtn.title = label;
    this._replayBtn.setAttribute("aria-label", label);
    this._replayBtn.setAttribute("aria-pressed", String(this._replay.active));
    this._replayBtn.classList.toggle("active", this._replay.active);
  }

  _toggleReplay() {
    if (this._replay.active) {
      this._exitReplay();
      return;
    }
    this._replay.active = true;
    this._replay.index = 0;
    // Following the live robot while scrubbing the past would fight the user
    // for the viewport.
    this._setFollow(false);
    this._replayBar.style.display = "";
    this._updateReplayBar();
    this._setReplayPlaying(true);
    this._updateReplayBtn();
    this._requestDraw();
  }

  _exitReplay() {
    this._setReplayPlaying(false);
    this._replay.active = false;
    if (this._replayBar) {
      this._replayBar.style.display = "none";
    }
    if (this._replayBtn) {
      this._replayBtn.classList.remove("active");
      this._replayBtn.setAttribute("aria-pressed", "false");
    }
    this._requestDraw();
  }

  _setReplayPlaying(playing) {
    if (this._replay.timer) {
      clearInterval(this._replay.timer);
      this._replay.timer = null;
    }
    this._replay.playing = Boolean(playing) && this._replay.active;
    if (this._replay.playing) {
      const total = this._replayTotal();
      // Fixed wall-clock duration: a long mow should not take longer to
      // watch than a short one, so the step scales with the track length.
      const step = Math.max(1, Math.ceil(total / (REPLAY_SECONDS * 20)));
      if (this._replay.index >= total) {
        this._replay.index = 0; // pressing play at the end starts over
      }
      this._replay.timer = setInterval(() => {
        this._replay.index = Math.min(total, this._replay.index + step);
        if (this._replay.index >= total) {
          this._setReplayPlaying(false);
        }
        this._updateReplayBar();
        this._requestDraw();
      }, 50);
    }
    if (this._replayPlayBtn) {
      this._replayPlayBtn.innerHTML = svgIcon(
        this._replay.playing ? ICONS.pause : ICONS.play
      );
      const label = localize(this._hass, this._replay.playing ? "pause" : "replay_play");
      this._replayPlayBtn.title = label;
      this._replayPlayBtn.setAttribute("aria-label", label);
    }
    this._updateReplayBar();
  }

  _updateReplayBar() {
    if (!this._replayBar || !this._replay.active) {
      return;
    }
    const total = this._replayTotal();
    this._replaySlider.max = String(total);
    this._replaySlider.value = String(Math.min(this._replay.index, total));
    const percent = total > 0 ? Math.round((this._replay.index / total) * 100) : 0;
    this._replayLabel.textContent = `${percent}%`;
  }

  _updateModeBtn() {
    if (!this._modeBtn) {
      return;
    }
    const label = localize(this._hass, `vw_${this._viewMode}`);
    const title = `${localize(this._hass, "view_mode")}: ${label}`;
    this._modeBtn.innerHTML = svgIcon(ICONS.layers) + `<span>${label}</span>`;
    this._modeBtn.title = title;
    this._modeBtn.setAttribute("aria-label", title);
  }

  _showMessage(text) {
    if (this._msg) {
      this._msg.textContent = text || "";
    }
  }

  _setFollow(on) {
    this._follow = Boolean(on) && Boolean(this._robot);
    this._followBtn.classList.toggle("active", this._follow);
    const followLabel = localize(this._hass, "follow");
    this._followBtn.title = followLabel;
    this._followBtn.setAttribute("aria-label", followLabel);
    this._followBtn.setAttribute("aria-pressed", String(this._follow));
    if (this._follow) {
      // Following carries the view away from the fitted one, so a later
      // resize must not snap it back to the whole lawn (issue #327).
      this._viewIsAuto = false;
      this._centerOnRobot();
      this._requestDraw();
    }
  }

  _centerOnRobot() {
    if (!this._robot || !this._view || !this._root) {
      return;
    }
    const [sx, sy] = this._worldToScreenRaw(this._robot.x, this._robot.y);
    this._view.tx += this._root.clientWidth / 2 - sx;
    this._view.ty += this._root.clientHeight / 2 - sy;
  }

  _updateHud() {
    if (!this._hud) {
      return;
    }
    this._updateCanvasLabel();
    if (!this._config.show_hud) {
      this._hud.replaceChildren();
      return;
    }
    const chips = [];
    const colors = this._colors();
    const activity = this._activity();
    // Active faults first and most prominent (issue #171): the readable text
    // comes from the integration's error-code catalog, so a stuck/lifted mower
    // is spelled out on the map, not just in the Active-errors sensor.
    if (Array.isArray(this._errors) && this._errors.length) {
      for (const err of this._errors) {
        const chip = document.createElement("span");
        chip.className = "chip error";
        chip.textContent = `⚠ ${err.text || `Error ${err.code}`}`;
        chip.title = `Error ${err.code}`;
        chips.push(chip);
      }
    }
    const state = this._hass && this._hass.states[this._config.entity];
    if (state) {
      const chip = document.createElement("span");
      chip.className = "chip state";
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = this._activityColor(activity, colors);
      const label = document.createElement("span");
      label.textContent = this._hass.formatEntityState
        ? this._hass.formatEntityState(state)
        : state.state;
      chip.append(dot, label);
      chips.push(chip);
    }
    const level = this._battery && this._battery.level;
    if (typeof level === "number") {
      const chip = document.createElement("span");
      chip.className = "chip battery";
      const charging = Boolean(this._battery.charging);
      chip.innerHTML =
        svgIcon(charging ? ICONS.batteryCharging : ICONS.battery) +
        `<span>${Math.round(level)}%</span>`;
      if (charging) {
        chip.querySelector("svg").style.color = this._activityColor(
          "mowing",
          colors
        );
      }
      chips.push(chip);
    }
    const busy =
      activity === "mowing" || activity === "paused" || activity === "returning";
    const progress = this._work && this._work.progress;
    // Label it "Progress" (issue #212 sibling: a bare "45 %" is ambiguous),
    // and keep it visible for an *incomplete* session even while docked —
    // e.g. the mower returned to the base with the job unfinished. Hidden
    // when idle with no session or once complete (100 %).
    if (
      typeof progress === "number" &&
      (busy || (progress > 0 && progress < 100))
    ) {
      const chip = document.createElement("span");
      chip.className = "chip progress";
      chip.textContent = `${localize(this._hass, "hud_progress")} ${Math.round(
        progress
      )} %`;
      chips.push(chip);
    }
    // ETA (#198): extrapolate the remaining time from the session's pace so
    // far. Only while actively mowing (a paused/charging pace is stale) and
    // once enough is done for the pace to mean anything; the "≈" marks
    // it as an estimate.
    const durationS = this._work && this._work.duration_s;
    if (
      activity === "mowing" &&
      typeof progress === "number" &&
      typeof durationS === "number" &&
      progress >= 3 &&
      progress < 100 &&
      durationS > 60
    ) {
      const remainS = (durationS * (100 - progress)) / progress;
      const chip = document.createElement("span");
      chip.className = "chip eta";
      chip.textContent = `≈ ${formatEtaMinutes(remainS)} ${localize(
        this._hass,
        "hud_eta_left"
      )}`;
      chips.push(chip);
    }
    // Mission detail (#205): what the mower is doing + why it went home,
    // only when there's something non-idle to report. Saves a dashboard card.
    const st = this._status;
    if (st) {
      const missionText = prettyStatus(st.mission, this._hass);
      const parts = [];
      if (st.mission && st.mission !== "MISSION_IDLE") {
        parts.push(missionText);
      }
      const subMissionText = prettyStatus(st.sub_mission, this._hass);
      if (
        st.sub_mission &&
        st.sub_mission !== "SUB_MISSION_IDLE" &&
        subMissionText !== missionText
      ) {
        parts.push(subMissionText);
      }
      if (
        st.back_to_station_reason &&
        st.back_to_station_reason !== "BACK_TO_STATION_REASON_NONE"
      ) {
        parts.push(prettyStatus(st.back_to_station_reason, this._hass));
      }
      if (parts.length) {
        const chip = document.createElement("span");
        chip.className = "chip mission";
        chip.textContent = parts.join(" · ");
        chips.push(chip);
      }
    }
    if (this._scene && this._scene.path_map_mismatch) {
      const chip = document.createElement("span");
      chip.className = "chip warn";
      chip.innerHTML =
        svgIcon(ICONS.refreshing) +
        `<span>${localize(this._hass, "map_refreshing")}</span>`;
      chips.push(chip);
    }
    if (this._scene && this._scene.map_name) {
      const chip = document.createElement("span");
      chip.className = "chip map";
      // Name + area as separate spans so narrow (phone) cards can drop the
      // name and keep just the area, instead of hiding the whole chip.
      const nameSpan = document.createElement("span");
      nameSpan.className = "m-name";
      nameSpan.textContent = this._scene.map_name;
      chip.appendChild(nameSpan);
      // total_area is in units of 0.1 m² (same as sensor.map_area) — NOT mm²
      const area = Number(this._scene.total_area);
      if (Number.isFinite(area) && area > 0) {
        const areaSpan = document.createElement("span");
        areaSpan.className = "m-area";
        areaSpan.textContent = `${Math.round(area / 10)} m²`;
        chip.appendChild(areaSpan);
      }
      chips.push(chip);
    }
    this._hud.replaceChildren(...chips);
  }

  _updateControls() {
    this._updateButtons();
  }

  /** Keep the canvas's assistive-tech label in sync with visible status. */
  _updateCanvasLabel() {
    if (!this._canvas) {
      return;
    }
    const parts = [];
    const state = this._hass && this._hass.states[this._config.entity];
    if (state) {
      parts.push(
        this._hass.formatEntityState
          ? this._hass.formatEntityState(state)
          : state.state
      );
    }
    const level = this._battery && this._battery.level;
    if (typeof level === "number") {
      parts.push(`${Math.round(level)}%`);
    }
    if (this._scene && this._scene.map_name) {
      parts.push(this._scene.map_name);
    }
    this._canvas.setAttribute("aria-label", parts.join(", ") || "TerraMow map");
  }

  _updateButtons() {
    if (!this._controls) {
      return;
    }
    if (!this._config.show_controls || !this._hass) {
      this._controls.replaceChildren();
      return;
    }
    // Show the follow toggle only when there is a robot pose to follow
    this._followBtn.style.display = this._robot ? "" : "none";
    const followLabel = localize(this._hass, "follow");
    this._followBtn.title = followLabel;
    this._followBtn.setAttribute("aria-label", followLabel);
    const fitLabel = localize(this._hass, "reset_view");
    this._fitBtn.title = fitLabel;
    this._fitBtn.setAttribute("aria-label", fitLabel);

    const activity = this._activity();
    const wanted = [];
    if (activity === "docked") {
      wanted.push("start");
    } else if (activity === "paused") {
      wanted.push("start", "dock");
    } else if (activity === "mowing") {
      wanted.push("pause", "dock");
    } else if (activity === "returning") {
      wanted.push("pause");
    } else if (activity === "error") {
      wanted.push("start", "dock");
    }
    const sig = wanted.join(",");
    if (this._controls.dataset.sig === sig) {
      return;
    }
    this._controls.dataset.sig = sig;
    const defs = {
      start: {
        icon: ICONS.play,
        title: localize(this._hass, "start_mowing"),
        service: "start_mowing",
        primary: true,
      },
      pause: {
        icon: ICONS.pause,
        title: localize(this._hass, "pause"),
        service: "pause",
        primary: true,
      },
      dock: {
        icon: ICONS.dock,
        title: localize(this._hass, "dock"),
        service: "dock",
        primary: false,
      },
    };
    const buttons = wanted.map((key) => {
      const def = defs[key];
      const btn = this._roundButton(def.icon, () =>
        this._hass.callService("lawn_mower", def.service, {
          entity_id: this._config.entity,
        })
      );
      btn.title = def.title;
      btn.setAttribute("aria-label", def.title);
      if (def.primary) {
        btn.classList.add("primary");
      }
      return btn;
    });
    this._controls.replaceChildren(...buttons);
  }

  _updateActionBar() {
    if (!this._actionBar) {
      return;
    }
    const count = this._pending.size;
    this._root.classList.toggle("selecting", count > 0);
    if (!count) {
      this._preflightText.textContent = "";
      this._actionBar.classList.remove("visible");
      return;
    }
    // Custom-named zones are listed by name; unnamed ones are grouped into a
    // single compact "Zones 1, 3, 5" instead of repeating the word per zone.
    const names = [];
    const unnamedIds = [];
    let areaM2 = 0;
    for (const region of this._scene?.regions || []) {
      for (const sub of region.sub_regions) {
        if (this._pending.has(sub.id)) {
          if (sub.name) {
            names.push(sub.name);
          } else {
            unnamedIds.push(sub.id);
          }
          areaM2 += zoneAreaM2(sub);
        }
      }
    }
    if (unnamedIds.length) {
      const word = pluralWord(this._hass, unnamedIds.length, "zone", "zones");
      names.push(
        `${word.charAt(0).toUpperCase()}${word.slice(1)} ${unnamedIds.join(", ")}`
      );
    }
    let text = names.join(", ");
    if (areaM2 > 0.5) {
      text += ` · ${Math.round(areaM2)} m²`;
    }
    this._actionNames.textContent = text;
    const preflightKey = [...this._pending]
      .sort((a, b) => Number(a) - Number(b))
      .join(",");
    const estimate = this._preflight?.[preflightKey];
    if (!estimate?.available) {
      this._preflightText.textContent = localize(this._hass, "preflight_none");
    } else {
      const parts = [
        `${localize(this._hass, "preflight_estimate")}: ${formatEtaMinutes(
          estimate.duration_seconds
        )}`,
        `${estimate.battery_percent}% ${localize(
          this._hass,
          "preflight_battery"
        )}`,
        `${estimate.recharge_legs} ${localize(
          this._hass,
          "preflight_recharges"
        )}`,
        `${estimate.sample_count} samples · ${estimate.confidence}`,
      ];
      if (estimate.daylight_warning) {
        parts.push(localize(this._hass, "preflight_daylight"));
      }
      this._preflightText.textContent = parts.join(" · ");
    }
    const unit = pluralWord(this._hass, count, "zone", "zones");
    this._goBtn.textContent = `${localize(this._hass, "start")} ${count} ${unit}`;
    this._clearBtn.textContent = localize(this._hass, "clear");
    this._actionBar.classList.add("visible");
  }

  async _startSelectedZones() {
    if (!this._hass || !this._pending.size) {
      return;
    }
    const regionIds = [...this._pending];
    try {
      await this._hass.callService("terramow", "start_select_region", {
        entity_id: this._config.entity,
        region_ids: regionIds,
      });
      this._pending.clear();
      this._updateActionBar();
      this._requestDraw();
      this._toast(localize(this._hass, "sent"));
    } catch (err) {
      this._toast((err && err.message) || String(err));
    }
  }

  _toast(message) {
    this.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { message },
        bubbles: true,
        composed: true,
      })
    );
  }

  _moreInfo() {
    this._openMoreInfo(this._config.entity);
  }

  _openMoreInfo(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  /* ------------------------------------------------------- interaction */

  _bindPointerEvents() {
    const canvas = this._canvas;
    canvas.addEventListener("pointerdown", (ev) => {
      canvas.setPointerCapture(ev.pointerId);
      this._pointers.set(ev.pointerId, { x: ev.offsetX, y: ev.offsetY });
      this._dragged = false;
      this._hideZoneInfo();
      this._cancelLongPress();
      if (this._pointers.size === 1 && this._config.zone_info) {
        const { offsetX, offsetY } = ev;
        this._lpTimer = setTimeout(() => {
          this._lpTimer = null;
          if (!this._dragged && this._pointers.size === 1) {
            this._lpFired = true;
            this._onZoneInfo(offsetX, offsetY);
          }
        }, 550);
      }
      if (this._pointers.size === 2 && this._view) {
        const [a, b] = [...this._pointers.values()];
        const cx = (a.x + b.x) / 2;
        const cy = (a.y + b.y) / 2;
        // Anchor the world point currently under the pinch midpoint; the
        // gesture keeps it under the fingers as they scale/rotate/pan.
        const [wx, wy] = this._screenToWorld(cx, cy);
        this._pinchStart = {
          dist: Math.hypot(a.x - b.x, a.y - b.y),
          angle: Math.atan2(b.y - a.y, b.x - a.x),
          scale: this._view.scale,
          rot: this._rot,
          wx,
          wy,
          engaged: false,
          angleOffset: 0,
        };
      }
      canvas.classList.add("dragging");
    });
    canvas.addEventListener("pointermove", (ev) => {
      const prev = this._pointers.get(ev.pointerId);
      if (!prev || !this._view) {
        return;
      }
      const cur = { x: ev.offsetX, y: ev.offsetY };
      if (this._pointers.size === 1) {
        const dx = cur.x - prev.x;
        const dy = cur.y - prev.y;
        if (Math.abs(dx) + Math.abs(dy) > 0) {
          if (Math.hypot(dx, dy) > 2) {
            this._dragged = true;
            this._setFollow(false);
            this._cancelLongPress();
          }
          this._view.tx += dx;
          this._view.ty += dy;
          this._viewIsAuto = false;
          this._requestDraw();
        }
      }
      this._pointers.set(ev.pointerId, cur);
      if (this._pointers.size === 2 && this._pinchStart) {
        this._dragged = true;
        this._setFollow(false);
        const ps = this._pinchStart;
        const [a, b] = [...this._pointers.values()];
        const cx = (a.x + b.x) / 2;
        const cy = (a.y + b.y) / 2;
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        let scale = this._view.scale;
        if (dist > 0 && ps.dist > 0) {
          scale = ps.scale * (dist / ps.dist);
        }
        let rot = ps.rot;
        if (this._config.rotate_gesture) {
          const angle = Math.atan2(b.y - a.y, b.x - a.x);
          // Twist since the gesture began, unwrapped to (-pi, pi]; engage
          // only past the dead-zone, then continue smoothly from there.
          const twist = Math.atan2(
            Math.sin(angle - ps.angle),
            Math.cos(angle - ps.angle)
          );
          if (!ps.engaged && Math.abs(twist) > ROTATE_DEADZONE) {
            ps.engaged = true;
            ps.angleOffset = Math.sign(twist) * ROTATE_DEADZONE;
          }
          if (ps.engaged) {
            rot = ps.rot + (twist - ps.angleOffset);
          }
        }
        this._applyPinch(cx, cy, ps.wx, ps.wy, scale, rot);
      }
    });
    const endPointer = (ev) => {
      this._cancelLongPress();
      const wasTap =
        this._pointers.size === 1 && !this._dragged && !this._lpFired;
      this._pointers.delete(ev.pointerId);
      if (this._pointers.size < 2) {
        this._pinchStart = null;
      }
      if (!this._pointers.size) {
        this._canvas.classList.remove("dragging");
        this._lpFired = false;
        // Gesture settled: re-rasterize the layers crisply at the final view
        // (during the gesture they were only transform-blitted).
        this._requestDraw();
      }
      if (wasTap && ev.type === "pointerup") {
        this._onTap(ev.offsetX, ev.offsetY);
      }
    };
    canvas.addEventListener("pointerup", endPointer);
    canvas.addEventListener("pointercancel", endPointer);
    canvas.addEventListener(
      "wheel",
      (ev) => {
        if (!this._view) {
          return;
        }
        ev.preventDefault();
        this._setFollow(false);
        const factor = Math.exp(-ev.deltaY * 0.0015);
        this._zoomAt(ev.offsetX, ev.offsetY, factor);
      },
      { passive: false }
    );
    canvas.addEventListener("dblclick", () => {
      this._setFollow(false);
      this._fitView();
      this._requestDraw();
    });
    canvas.addEventListener("keydown", (ev) => {
      if (!this._config.zone_selection || !this._scene) {
        return;
      }
      switch (ev.key) {
        case "ArrowRight":
        case "ArrowDown":
          this._focusZone(1);
          ev.preventDefault();
          break;
        case "ArrowLeft":
        case "ArrowUp":
          this._focusZone(-1);
          ev.preventDefault();
          break;
        case "Enter":
        case " ": {
          const sub = this._orderedZones().find(
            (z) => z.id === this._focusedZoneId
          );
          if (sub) {
            this._toggleZoneSelection(sub);
            this._announceZone(sub);
          }
          ev.preventDefault();
          break;
        }
        case "Escape":
          if (this._focusedZoneId !== null) {
            this._focusedZoneId = null;
            this._requestDraw();
          }
          break;
        default:
          break;
      }
    });
    // Drop the focus ring when the map loses keyboard focus.
    canvas.addEventListener("blur", () => {
      if (this._focusedZoneId !== null) {
        this._focusedZoneId = null;
        this._requestDraw();
      }
    });
  }

  _zoomAt(px, py, factor) {
    const view = this._view;
    if (!view) {
      return;
    }
    const newScale = Math.min(Math.max(view.scale * factor, 1e-4), 10);
    const realFactor = newScale / view.scale;
    view.tx = px - (px - view.tx) * realFactor;
    view.ty = py - (py - view.ty) * realFactor;
    view.scale = newScale;
    this._viewIsAuto = false;
    this._requestDraw();
  }

  /**
   * Apply a pinch's scale + rotation while pinning world point (wx, wy) under
   * screen point (sx, sy) — the point the fingers grabbed. Solves the view
   * translation from `screen = R(rot)·scale·world + t` for that constraint,
   * which also yields two-finger pan for free as the midpoint moves.
   */
  _applyPinch(sx, sy, wx, wy, scale, rot) {
    const view = this._view;
    if (!view) {
      return;
    }
    view.scale = Math.min(Math.max(scale, 1e-4), 10);
    this._rot = rot;
    const cos = Math.cos(rot);
    const sin = Math.sin(rot);
    view.tx = sx - (wx * cos - wy * sin) * view.scale;
    view.ty = sy - (wx * sin + wy * cos) * view.scale;
    this._viewIsAuto = false;
    this._updateCompass();
    this._persistLiveRotation();
    this._requestDraw();
  }

  /** Mirror the current rotation (whole degrees, 0-359) to localStorage so the
   *  config editor's "use current rotation" button can read it. */
  _persistLiveRotation() {
    if (!this._config || !this._config.entity) {
      return;
    }
    const deg = (((Math.round((this._rot * 180) / Math.PI) % 360) + 360) % 360);
    if (deg === this._lastPersistedRot) {
      return;
    }
    this._lastPersistedRot = deg;
    try {
      window.localStorage.setItem(LIVE_ROT_KEY + this._config.entity, String(deg));
    } catch (e) {
      /* storage blocked (private mode); capture button just won't update */
    }
  }

  /** Reset the map to the configured rotation, pivoting about the view center. */
  _resetRotation() {
    if (!this._view || !this._root) {
      return;
    }
    const cx = this._root.clientWidth / 2;
    const cy = this._root.clientHeight / 2;
    const [wx, wy] = this._screenToWorld(cx, cy);
    this._applyPinch(cx, cy, wx, wy, this._view.scale, this._baseRot);
  }

  /**
   * Show the compass button only once the map is turned away from its
   * configured angle, and spin its needle to reflect how far it is turned.
   */
  _updateCompass() {
    if (!this._compassBtn) {
      return;
    }
    const delta = Math.atan2(
      Math.sin(this._rot - this._baseRot),
      Math.cos(this._rot - this._baseRot)
    );
    const turned = Math.abs(delta) > 0.01;
    this._compassBtn.style.display = turned ? "inline-flex" : "none";
    const svg = this._compassBtn.querySelector("svg");
    if (svg) {
      svg.style.transform = `rotate(${-delta}rad)`;
    }
  }

  /** World (mm) to screen (CSS px) under the current view + rotation. */
  _worldToScreenRaw(x, y) {
    const cos = Math.cos(this._rot);
    const sin = Math.sin(this._rot);
    const view = this._view;
    return [
      (x * cos - y * sin) * view.scale + view.tx,
      (x * sin + y * cos) * view.scale + view.ty,
    ];
  }

  _screenToWorld(sx, sy) {
    const cos = Math.cos(this._rot);
    const sin = Math.sin(this._rot);
    const view = this._view;
    const xr = (sx - view.tx) / view.scale;
    const yr = (sy - view.ty) / view.scale;
    return [xr * cos + yr * sin, -xr * sin + yr * cos];
  }

  _onTap(px, py) {
    if (!this._scene || !this._view) {
      return;
    }
    // Robot first: tapping the marker opens the entity's more-info dialog
    if (this._robot) {
      const [rx, ry] = this._worldToScreenRaw(this._robot.x, this._robot.y);
      const radius = Math.max(16, (380 * this._view.scale) / 2);
      if (Math.hypot(px - rx, py - ry) <= radius) {
        this._moreInfo();
        return;
      }
    }
    if (!this._config.zone_selection) {
      return;
    }
    const sub = this._zoneAt(px, py);
    if (!sub) {
      return;
    }
    this._toggleZoneSelection(sub);
  }

  /** Toggle a zone's pending-selection (shared by tap and keyboard). */
  _toggleZoneSelection(sub) {
    if (!sub || sub.id === null) {
      return;
    }
    if (this._pending.has(sub.id)) {
      this._pending.delete(sub.id);
    } else {
      this._pending.add(sub.id);
    }
    this._staticCache = null; // selection tint lives on the static layer
    this._updateActionBar();
    this._requestDraw();
  }

  /** Selectable zones in a stable order, for keyboard cycling. */
  _orderedZones() {
    const zones = [];
    for (const region of this._scene?.regions || []) {
      for (const sub of region.sub_regions || []) {
        if (sub.id !== null && sub.boundary && sub.boundary.length >= 3) {
          zones.push(sub);
        }
      }
    }
    return zones;
  }

  /** Move keyboard focus to the next (+1) / previous (-1) zone. */
  _focusZone(step) {
    const zones = this._orderedZones();
    if (!zones.length) {
      return;
    }
    let idx = zones.findIndex((z) => z.id === this._focusedZoneId);
    if (idx < 0) {
      idx = 0; // first key press lands on the first zone
    } else {
      idx = (idx + step + zones.length) % zones.length;
    }
    const sub = zones[idx];
    this._focusedZoneId = sub.id;
    this._ensureZoneVisible(sub);
    this._announceZone(sub);
    this._requestDraw();
  }

  /** Pan so the focused zone's center is on screen (keyboard navigation). */
  _ensureZoneVisible(sub) {
    if (!sub.center || !this._view || !this._root) {
      return;
    }
    const [sx, sy] = this._worldToScreenRaw(sub.center[0], sub.center[1]);
    const w = this._root.clientWidth;
    const h = this._root.clientHeight;
    const m = 44;
    if (sx < m || sx > w - m || sy < m || sy > h - m) {
      this._setFollow(false);
      this._view.tx += w / 2 - sx;
      this._view.ty += h / 2 - sy;
      this._viewIsAuto = false;
    }
  }

  /** Announce the focused zone (name + selection state) to assistive tech. */
  _announceZone(sub) {
    if (!this._srLive) {
      return;
    }
    const word = localize(this._hass, "zone");
    const name =
      sub.name ||
      `${word.charAt(0).toUpperCase()}${word.slice(1)} ${sub.id}`;
    this._srLive.textContent = this._pending.has(sub.id)
      ? `${name}, ${localize(this._hass, "kbd_selected")}`
      : name;
  }

  /** The zone (sub-region) under a screen point, or null. */
  _zoneAt(px, py) {
    const [wx, wy] = this._screenToWorld(px, py);
    for (const region of this._scene.regions) {
      for (const sub of region.sub_regions) {
        if (sub.id === null || sub.boundary.length < 3) {
          continue;
        }
        if (!pointInPolygon(wx, wy, sub.boundary)) {
          continue;
        }
        const inHole = (sub.inner_boundaries || []).some((hole) =>
          pointInPolygon(wx, wy, hole)
        );
        if (!inHole) {
          return sub;
        }
      }
    }
    return null;
  }

  _cancelLongPress() {
    if (this._lpTimer) {
      clearTimeout(this._lpTimer);
      this._lpTimer = null;
    }
  }

  _hideZoneInfo() {
    if (this._infoPanel) {
      this._infoPanel.classList.remove("visible");
    }
  }

  /**
   * Open the legend once, on a browser's very first visit with a real map, so
   * newcomers discover what the glyphs mean. A localStorage flag makes it
   * one-shot; after that the legend is purely user-controlled.
   */
  _maybeAutoOpenLegend() {
    if (this._legendAutoDone || !this._legend || !this._hasGeometry()) {
      return;
    }
    this._legendAutoDone = true;
    let seen = false;
    try {
      seen = window.localStorage.getItem(LEGEND_SEEN_KEY) === "1";
    } catch (e) {
      seen = true; // storage blocked (private mode): don't nag every load
    }
    if (seen) {
      return;
    }
    try {
      window.localStorage.setItem(LEGEND_SEEN_KEY, "1");
    } catch (e) {
      /* ignore */
    }
    if (!this._legend.classList.contains("visible")) {
      this._toggleLegend();
    }
  }

  _toggleLegend() {
    if (!this._legend) {
      return;
    }
    const show = !this._legend.classList.contains("visible");
    if (show) {
      this._buildLegend();
      if (this._maintPanel && this._maintPanel.classList.contains("visible")) {
        this._toggleMaint(); // both panels live in the same corner
      }
    }
    this._legend.classList.toggle("visible", show);
    this._legendBtn.classList.toggle("active", show);
    this._legendBtn.setAttribute("aria-expanded", String(show));
    const label = localize(this._hass, show ? "legend_hide" : "legend_show");
    this._legendBtn.title = label;
    this._legendBtn.setAttribute("aria-label", label);
  }

  /**
   * Populate the legend with one row per glyph *actually present* on the
   * current map, so it never explains something the user can't see. Called
   * on open and, while open, whenever a full scene arrives.
   */
  _buildLegend() {
    if (!this._legend) {
      return;
    }
    const c = this._colors();
    const scene = this._scene || {};
    const cfg = this._config || {};
    const L = this._layers();
    const subs = [];
    for (const region of scene.regions || []) {
      for (const sub of region.sub_regions || []) {
        subs.push(sub);
      }
    }
    const markers = (cfg.show_markers && scene.markers) || {};
    const hasAngle =
      typeof scene.main_direction_angle === "number" ||
      subs.some((s) => typeof s.direction_angle === "number");
    const noGo =
      (scene.forbidden_zones || []).length +
      (scene.physical_forbidden_zones || []).length;
    const entries = [];
    const add = (cond, kind, key) => {
      if (cond) {
        entries.push([kind, key]);
      }
    };
    // One "Mowing zone" entry; the swatch matches what's on the map — blue
    // when a zone is selected for the next mow, otherwise the default green.
    add(
      subs.length > 0,
      subs.some((s) => s.selected) ? "zone_selected" : "zone",
      "lg_zone"
    );
    // Zones the user tapped to mow render yellow (pending); explain that too.
    add(this._pending.size > 0, "zone_pending", "lg_zone_pending");
    add(Boolean(this._robot), "mower", "lg_mower");
    add(Boolean(scene.station), "dock", "lg_dock");
    add(subs.some((s) => s.order > 0), "order", "lg_order");
    add(subs.some((s) => s.params), "custom", "lg_custom");
    add(cfg.show_direction && hasAngle, "direction", "lg_direction");
    add((markers.trapped || []).length > 0, "stuck", "lg_stuck");
    add(
      Boolean(cfg.show_hotspots && (scene.fault_hotspots || []).length),
      "hotspot",
      "lg_hotspot"
    );
    add((markers.maintenance || []).length > 0, "maint", "lg_maint");
    add((markers.cross_boundary || []).length > 0, "passage", "lg_passage");
    add(noGo > 0, "nogo", "lg_nogo");
    add((scene.virtual_walls || []).length > 0, "wall", "lg_wall");
    add(Boolean(L.coverage), "coverage", "lg_coverage");
    add(
      Boolean(
        L.wifi &&
          scene.wifi_heatmap &&
          (scene.wifi_heatmap.cells || []).length
      ),
      "wifi",
      "lg_wifi"
    );
    add(
      Boolean(
        L.season && scene.mow_counts && (scene.mow_counts.cells || []).length
      ),
      "season",
      "lg_season"
    );

    const rows = entries
      .map(
        ([kind, key]) =>
          `<div class="lg-row"><span class="lg-sw">${legendSwatch(
            kind,
            c
          )}</span><span>${localize(this._hass, key)}</span></div>`
      )
      .join("");
    const title = localize(this._hass, "legend");
    const hide = localize(this._hass, "legend_hide");
    this._legend.innerHTML =
      `<div class="lg-head"><span>${title}</span>` +
      `<button type="button" aria-label="${hide}">${svgIcon(
        ICONS.close
      )}</button></div>` +
      (rows || `<div class="lg-row"><span>${localize(this._hass, "no_map")}</span></div>`) +
      this._layerCountsHtml(scene, subs, markers);
    const closeBtn = this._legend.querySelector(".lg-head button");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => this._toggleLegend());
    }
  }

  /**
   * Debug section (opt-in via `show_layer_counts`): how many of each layer the
   * card actually received. Answers "why isn't my no-go zone / wall showing?"
   * at a glance — a count of 0 means the device never sent it. Off by default.
   */
  _layerCountsHtml(scene, subs, markers) {
    if (!this._config || !this._config.show_layer_counts) {
      return "";
    }
    const counts = [
      ["dbg_zones", subs.length],
      [
        "dbg_nogo",
        (scene.forbidden_zones || []).length +
          (scene.physical_forbidden_zones || []).length,
      ],
      ["dbg_walls", (scene.virtual_walls || []).length],
      ["dbg_obstacles", (scene.obstacles || []).length],
      ["dbg_passthrough", (scene.pass_through_zones || []).length],
      ["dbg_required", (scene.required_zones || []).length],
      ["dbg_tunnels", (scene.tunnels || []).length],
      [
        "dbg_markers",
        (markers.trapped || []).length +
          (markers.maintenance || []).length +
          (markers.cross_boundary || []).length,
      ],
      ["dbg_draw", (scene.draw_regions || []).length],
      [
        "dbg_paths",
        (scene.current_path || []).length +
          (scene.history_path || []).length +
          (scene.session_paths || []).reduce(
            (total, segment) => total + segment.length,
            0
          ),
      ],
    ];
    const rows = counts
      .map(
        ([key, n]) =>
          `<div class="lg-cnt${n ? "" : " zero"}"><span>${localize(
            this._hass,
            key
          )}</span><span class="lg-n">${n}</span></div>`
      )
      .join("");
    return `<div class="lg-sec">${localize(this._hass, "dbg_title")}</div>${rows}`;
  }

  /* -------------------------------------------------------- maintenance */

  /**
   * The counter states as one string. Every state change anywhere in Home
   * Assistant lands in `set hass`; without this gate the panel would rebuild
   * on all of them, for two values that move once a minute.
   */
  _maintSignature() {
    const maintenance = this._maintenance;
    if (!maintenance || !this._hass) {
      return "";
    }
    return MAINT_ROWS.map(([role]) => {
      const state = maintenance[role] && this._hass.states[maintenance[role]];
      return state ? `${state.state}` : "-";
    }).join("|");
  }

  /**
   * One row per maintenance counter that actually has a state — firmware
   * without dp_125/dp_126, or a sensor someone disabled, simply drops out,
   * and with both gone the wrench never appears at all.
   *
   * `due` is the counter at zero (blades want changing, station wants
   * cleaning); `soon` is the last tenth of the cycle, measured against the
   * sensor's own `recommended_cycle` attribute rather than a number repeated
   * here.
   */
  _maintRows() {
    const hass = this._hass;
    const maintenance = this._maintenance;
    if (!hass || !maintenance) {
      return [];
    }
    const rows = [];
    for (const [role, labelKey, resetRole] of MAINT_ROWS) {
      const entityId = maintenance[role];
      const state = entityId ? hass.states[entityId] : null;
      if (!state) {
        continue;
      }
      const minutes = Number(state.state);
      const known = Number.isFinite(minutes);
      const cycle = Number((state.attributes || {}).recommended_cycle);
      const due = known && minutes <= 0;
      const soon =
        known &&
        !due &&
        Number.isFinite(cycle) &&
        cycle > 0 &&
        minutes <= cycle * MAINT_SOON_FRACTION;
      let value;
      if (due) {
        value = localize(hass, "maint_due");
      } else if (known) {
        value = formatMaintenanceMinutes(minutes);
      } else {
        // unknown / unavailable: show whatever Home Assistant would show.
        value = hass.formatEntityState
          ? hass.formatEntityState(state)
          : `${state.state}`;
      }
      const resetId = maintenance[resetRole];
      rows.push({
        entityId,
        label: localize(hass, labelKey),
        value,
        due,
        soon,
        // A reset button that isn't in the state machine (disabled) can't be
        // pressed; the row then shows the counter alone.
        resetId: resetId && hass.states[resetId] ? resetId : null,
      });
    }
    return rows;
  }

  /**
   * Show the wrench only when there is a counter behind it, and colour it by
   * the worse of the two: red once one has run out, orange shortly before —
   * the point of the chip is noticing without opening it (issue #304).
   */
  _updateMaintBtn() {
    if (!this._maintBtn) {
      return;
    }
    const rows = this._config.show_maintenance ? this._maintRows() : [];
    if (!rows.length) {
      this._maintBtn.style.display = "none";
      if (this._maintPanel.classList.contains("visible")) {
        this._toggleMaint();
      }
      return;
    }
    this._maintBtn.style.display = "";
    const due = rows.some((row) => row.due);
    const soon = !due && rows.some((row) => row.soon);
    this._maintBtn.classList.toggle("due", due);
    this._maintBtn.classList.toggle("soon", soon);
    const open = this._maintPanel.classList.contains("visible");
    const label = localize(this._hass, open ? "maint_hide" : "maint_show");
    const title = due
      ? `${label} — ${localize(this._hass, "maint_due")}`
      : label;
    this._maintBtn.title = title;
    this._maintBtn.setAttribute("aria-label", title);
    if (open) {
      this._buildMaint();
    }
  }

  _toggleMaint() {
    if (!this._maintPanel) {
      return;
    }
    const show = !this._maintPanel.classList.contains("visible");
    if (show) {
      this._buildMaint();
      if (this._legend && this._legend.classList.contains("visible")) {
        this._toggleLegend(); // both panels live in the same corner
      }
    }
    this._maintPanel.classList.toggle("visible", show);
    this._maintBtn.classList.toggle("active", show);
    this._maintBtn.setAttribute("aria-expanded", String(show));
    const label = localize(this._hass, show ? "maint_hide" : "maint_show");
    this._maintBtn.title = label;
    this._maintBtn.setAttribute("aria-label", label);
  }

  /**
   * Fill the panel: one row per counter, the value tappable for the sensor's
   * more-info dialog and a reset button that presses this install's own reset
   * button entity. Built from DOM nodes rather than markup so a state string
   * can never be interpreted as HTML.
   */
  _buildMaint() {
    const hass = this._hass;
    const head = document.createElement("div");
    head.className = "lg-head";
    const heading = document.createElement("span");
    heading.textContent = localize(hass, "maint");
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", localize(hass, "maint_hide"));
    closeBtn.innerHTML = svgIcon(ICONS.close);
    closeBtn.addEventListener("click", () => this._toggleMaint());
    head.append(heading, closeBtn);

    const children = [head];
    const resetLabel = localize(hass, "maint_reset");
    for (const row of this._maintRows()) {
      const rowEl = document.createElement("div");
      rowEl.className = "mt-row";
      if (row.due) {
        rowEl.classList.add("due");
      } else if (row.soon) {
        rowEl.classList.add("soon");
      }
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "mt-cell";
      const label = document.createElement("span");
      label.className = "mt-label";
      label.textContent = row.label;
      const value = document.createElement("span");
      value.className = "mt-value";
      value.textContent = row.value;
      cell.append(label, value);
      cell.addEventListener("click", () => this._openMoreInfo(row.entityId));
      rowEl.appendChild(cell);
      if (row.resetId) {
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "mt-reset";
        resetBtn.innerHTML = svgIcon(ICONS.restore);
        resetBtn.title = `${resetLabel}: ${row.label}`;
        resetBtn.setAttribute("aria-label", `${resetLabel}: ${row.label}`);
        resetBtn.addEventListener("click", () =>
          this._resetMaintCounter(row.resetId)
        );
        rowEl.appendChild(resetBtn);
      }
      children.push(rowEl);
    }
    this._maintPanel.replaceChildren(...children);
  }

  async _resetMaintCounter(entityId) {
    if (!this._hass) {
      return;
    }
    try {
      await this._hass.callService("button", "press", { entity_id: entityId });
      this._toast(localize(this._hass, "maint_reset_done"));
    } catch (err) {
      this._toast((err && err.message) || String(err));
    }
  }

  /**
   * Long-press on a zone: show its effective mow settings. Zones with custom
   * params (the app's per-zone overrides) show those; others show the global
   * block, with a footer naming which scope applies.
   */
  _onZoneInfo(px, py) {
    if (!this._scene || !this._view) {
      return;
    }
    const sub = this._zoneAt(px, py);
    if (!sub) {
      return;
    }
    const t = (key) => localize(this._hass, key);
    const level = (value) => {
      if (typeof value !== "string") {
        return null;
      }
      const token = value.split("_").pop().toLowerCase();
      const localized = t(`lvl_${token}`);
      return localized !== `lvl_${token}`
        ? localized
        : token.charAt(0).toUpperCase() + token.slice(1);
    };
    const custom = !!sub.params;
    const params = sub.params || this._scene.mow_params || {};
    const zoneWord = t("zone");
    const title =
      sub.name ||
      `${zoneWord.charAt(0).toUpperCase()}${zoneWord.slice(1)} ${sub.id}`;
    const areaM2 = zoneAreaM2(sub);
    const angle =
      typeof sub.direction_angle === "number"
        ? sub.direction_angle
        : this._scene.main_direction_angle;

    const rows = [];
    const push = (key, value) => {
      if (value !== null && value !== undefined && value !== "") {
        rows.push([t(key), String(value)]);
      }
    };
    push(
      "zi_cut_height",
      typeof params.mow_height === "number" ? `${params.mow_height} mm` : null
    );
    push("zi_speed", level(params.mow_speed));
    push(
      "zi_spacing",
      typeof params.mow_spacing === "number"
        ? `${params.mow_spacing} mm`
        : null
    );
    push("zi_blade", level(params.blade_disk_speed));
    push(
      "zi_edge",
      typeof params.edge_cutting_distance === "number" &&
        params.edge_cutting_distance > 0
        ? `${params.edge_cutting_distance} mm`
        : null
    );
    push("zi_direction", typeof angle === "number" ? `${angle}°` : null);
    push("zi_order", sub.order && sub.order > 0 ? sub.order : null);

    const panel = this._infoPanel;
    panel.replaceChildren();
    const head = document.createElement("div");
    head.className = "zi-title";
    const name = document.createElement("span");
    name.textContent = title;
    const area = document.createElement("span");
    area.className = "zi-area";
    area.textContent = areaM2 > 0.5 ? `${Math.round(areaM2)} m²` : "";
    head.append(name, area);
    panel.appendChild(head);
    for (const [label, value] of rows) {
      const row = document.createElement("div");
      row.className = "zi-row";
      const labelEl = document.createElement("span");
      labelEl.className = "zi-label";
      labelEl.textContent = label;
      const valueEl = document.createElement("span");
      valueEl.textContent = value;
      row.append(labelEl, valueEl);
      panel.appendChild(row);
    }
    const scope = document.createElement("div");
    scope.className = "zi-scope";
    scope.textContent = custom ? t("zi_custom") : t("zi_global");
    panel.appendChild(scope);
    panel.classList.add("visible");
  }

  /* ----------------------------------------------------------- drawing */

  _syncCanvasSize() {
    if (!this._canvas || !this._root) {
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    const w = this._root.clientWidth;
    const h = this._root.clientHeight;
    if (w <= 0 || h <= 0) {
      return;
    }
    if (
      this._canvas.width !== Math.round(w * dpr) ||
      this._canvas.height !== Math.round(h * dpr)
    ) {
      this._canvas.width = Math.round(w * dpr);
      this._canvas.height = Math.round(h * dpr);
    }
  }

  _fitView() {
    if (!this._scene || !this._root) {
      return;
    }
    // Fit to the drawn content (lawn, zones, walls, station) rather than the
    // full scanned extent, which the card never draws — otherwise the view
    // pads out to an invisible rectangle and leaves the lawn tiny. Older
    // payloads without content_bounds fall back to the full bounds.
    const box = this._scene.content_bounds || this._scene.bounds;
    if (!box) {
      return;
    }
    const [minX, minY, maxX, maxY] = box;
    const w = this._root.clientWidth;
    const h = this._root.clientHeight;
    if (w <= 0 || h <= 0) {
      return;
    }
    // Bounds of the rotated content
    const cos = Math.cos(this._rot);
    const sin = Math.sin(this._rot);
    const corners = [
      [minX, minY],
      [maxX, minY],
      [maxX, maxY],
      [minX, maxY],
    ].map(([x, y]) => [x * cos - y * sin, x * sin + y * cos]);
    const rMinX = Math.min(...corners.map((c) => c[0]));
    const rMaxX = Math.max(...corners.map((c) => c[0]));
    const rMinY = Math.min(...corners.map((c) => c[1]));
    const rMaxY = Math.max(...corners.map((c) => c[1]));
    const bw = Math.max(1, rMaxX - rMinX);
    const bh = Math.max(1, rMaxY - rMinY);
    // fit_padding is the fraction of the card the content fills (0.5–1.0);
    // the remainder is breathing room around the edges.
    const pad = Math.min(Math.max(Number(this._config.fit_padding) || 0.95, 0.5), 1);
    const scale = Math.min(w / bw, h / bh) * pad;
    this._view = {
      scale,
      tx: (w - bw * scale) / 2 - rMinX * scale,
      ty: (h - bh * scale) / 2 - rMinY * scale,
    };
    this._viewIsAuto = true;
    this._fitBox = [minX, minY, maxX, maxY];
  }

  /**
   * Whether the box the automatic view was framed against has since changed.
   *
   * The card used to fit exactly once, when the first scene carrying any
   * geometry arrived (issue #327). That first scene can be incomplete: the
   * backend derives content_bounds from the *drawn* geometry and falls back to
   * the full scanned extent while there is none, and _hasGeometry() is already
   * satisfied by that extent alone. The one and only fit was then spent on a
   * rectangle the card never draws, leaving the lawn small and off-centre, and
   * the later scene that did carry the lawn never re-framed it — which is why
   * pressing fit put it right. A view the user has moved is left alone.
   */
  _fitBasisChanged() {
    if (!this._viewIsAuto || !this._scene) {
      return false;
    }
    const box = this._scene.content_bounds || this._scene.bounds;
    if (!box) {
      return false;
    }
    if (!this._fitBox) {
      return true;
    }
    return box.some((value, index) => value !== this._fitBox[index]);
  }

  /**
   * Re-frame the map after the card changed size. Returns whether it re-fit.
   *
   * A scene can arrive before the browser has settled the card's size — a
   * `rows: auto` grid row reports a provisional height first. The fit computed
   * against that size is wrong but non-zero, so before issue #327 nothing ever
   * recomputed it and the map stayed mis-zoomed until the user pressed fit.
   * Re-fitting also keeps the map framed across sidebars, device rotation and
   * expanding dashboard sections — but only while the view is still the
   * automatic one, because a view the user panned or zoomed to is theirs.
   */
  _refitOnResize() {
    if (!this._viewIsAuto || !this._hasGeometry()) {
      return false;
    }
    this._fitView();
    return true;
  }

  _requestDraw() {
    if (this._rafHandle) {
      return;
    }
    this._rafHandle = requestAnimationFrame(() => {
      this._rafHandle = 0;
      this._draw();
    });
  }

  _activityColor(activity, colors) {
    const pair = ACTIVITY_COLORS[activity];
    if (!pair) {
      return colors.subtext;
    }
    return pair[colors.dark ? 1 : 0];
  }

  /** Lightweight theme fingerprint from hass, no layout read. */
  _themeSignature(hass) {
    const themes = hass && hass.themes;
    if (!themes) {
      return "";
    }
    const selected = hass.selectedTheme ? JSON.stringify(hass.selectedTheme) : "";
    return `${themes.darkMode}|${themes.theme || ""}|${selected}`;
  }

  /** Resolved theme colors, cached until the theme fingerprint changes. */
  _colors() {
    if (!this._colorCache) {
      this._colorCache = this._computeColors();
    }
    return this._colorCache;
  }

  _computeColors() {
    const styles = getComputedStyle(this);
    const pick = (name, fallback) =>
      styles.getPropertyValue(name).trim() || fallback;
    const primaryText = pick("--primary-text-color", "#212121");
    // Prefer Home Assistant's own light/dark signal; the text-color sniff
    // below is only a fallback for stubs or themes that omit darkMode.
    const themeDark = this._hass && this._hass.themes && this._hass.themes.darkMode;
    const dark =
      typeof themeDark === "boolean"
        ? themeDark
        : primaryText.startsWith("#e") ||
          primaryText.startsWith("#f") ||
          primaryText.toLowerCase() === "white" ||
          primaryText.startsWith("rgb(2");
    return {
      dark,
      accent: pick("--primary-color", "#03a9f4"),
      text: primaryText,
      subtext: pick("--secondary-text-color", "#727272"),
      bg: dark ? "#151a17" : "#f2f7f0",
      lawn: dark ? "#24402c" : "#cde8c4",
      lawnEdge: dark ? "#4e7a58" : "#7cb56f",
      zoneFill: dark ? "rgba(120,190,120,0.10)" : "rgba(70,140,60,0.07)",
      zoneEdge: dark ? "rgba(150,210,150,0.55)" : "rgba(70,130,60,0.5)",
      zoneSelected: dark ? "rgba(80,170,255,0.30)" : "rgba(3,169,244,0.22)",
      zonePending: dark ? "rgba(255,200,40,0.38)" : "rgba(255,180,0,0.32)",
      forbidden: dark ? "rgba(230,80,80,0.30)" : "rgba(220,60,60,0.22)",
      forbiddenEdge: dark ? "#e66" : "#c33",
      obstacle: dark ? "rgba(200,200,200,0.25)" : "rgba(90,90,90,0.25)",
      passThrough: dark ? "rgba(255,170,60,0.16)" : "rgba(255,150,0,0.14)",
      passThroughEdge: dark ? "#ffb74d" : "#ef6c00",
      wall: dark ? "#ff8a80" : "#d32f2f",
      coverage: dark ? "rgba(26,150,122,0.42)" : "rgba(20,130,105,0.42)",
      historyPath: dark ? "rgba(180,220,180,0.35)" : "rgba(90,140,90,0.35)",
      currentPath: dark ? "#7fd4ff" : "#0288d1",
      // Amber, not green: the charging base has to stand out against the
      // (green) mowed-coverage area, where a green house was invisible (#214).
      station: dark ? "#ffca28" : "#f9a825",
      robot: dark ? "#ffd54f" : "#f57f17",
      grid: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)",
      // Marker badges mirror the PNG camera palette (badge_orange/badge_blue).
      markerTrapped: dark ? "#ffb74d" : "#ef6c00",
      markerMaintenance: dark ? "#64b5f6" : "#1565c0",
      markerOutline: dark ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.85)",
      badgeOrder: dark ? "#ef5350" : "#d32f2f",
    };
  }

  /** Apply the world transform (translate → scale → rotate). */
  _applyWorldTransform(ctx, dpr) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.translate(this._view.tx, this._view.ty);
    ctx.scale(this._view.scale, this._view.scale);
    ctx.rotate(this._rot);
  }

  _draw() {
    if (!this._canvas) {
      return;
    }
    this._syncCanvasSize();
    const ctx = this._canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = this._canvas.width / dpr;
    const h = this._canvas.height / dpr;
    const colors = this._colors();

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, w, h);

    if (!this._hasGeometry()) {
      this._showMessage(
        localize(
          this._hass,
          this._unsub || this._scene ? "no_map" : "not_connected"
        )
      );
      return;
    }
    this._showMessage("");

    if (!this._view) {
      this._fitView();
    }
    const view = this._view;
    if (!view || !Number.isFinite(view.scale) || view.scale <= 0) {
      return;
    }

    const themeSig = colors.bg + colors.accent;
    const sizeSig = `${this._canvas.width}x${this._canvas.height}`;

    // The two offscreen layers are rasterized at a *baseline* view and then
    // composited under a cheap affine transform, so a pan/zoom never re-traces
    // the (expensive) geometry and path polylines. While a touch/pinch gesture
    // is in flight the baseline is frozen and the cached bitmap is merely
    // transformed; once the gesture settles (no active pointers) the baseline
    // snaps back to the live view and the layers re-rasterize crisply.
    const interacting = this._pointers.size > 0;
    if (
      !this._layerView ||
      (!interacting &&
        (this._layerView.scale !== view.scale ||
          this._layerView.tx !== view.tx ||
          this._layerView.ty !== view.ty ||
          this._layerView.rot !== this._rot))
    ) {
      this._layerView = {
        scale: view.scale,
        tx: view.tx,
        ty: view.ty,
        rot: this._rot,
      };
    }
    const layerView = this._layerView;

    // Layer 1: static geometry (zones, forbidden areas, walls, station …)
    const staticSig = [
      this._sceneRev,
      sizeSig,
      themeSig,
      [...this._pending].sort().join(","),
    ].join("§");
    // Layer 2: coverage + paths (changes on every path push)
    const pathSig = [
      this._sceneRev,
      this._pathRev,
      sizeSig,
      themeSig,
      this._viewMode,
      // Scrubbing redraws only the path layer: the geometry underneath it
      // does not change while the track is clipped.
      this._replay.active ? this._replay.index : "live",
    ].join("§");

    const needStatic =
      !this._staticCache ||
      this._staticCache.sig !== staticSig ||
      this._staticCache.view !== layerView;
    const needPath =
      !this._pathCache ||
      this._pathCache.sig !== pathSig ||
      this._pathCache.view !== layerView;

    if (needStatic || needPath) {
      // Rasterize at the baseline view: briefly point the world transform at
      // layerView (a no-op when idle, since layerView === the live view).
      const liveTx = view.tx;
      const liveTy = view.ty;
      const liveScale = view.scale;
      const liveRot = this._rot;
      view.tx = layerView.tx;
      view.ty = layerView.ty;
      view.scale = layerView.scale;
      this._rot = layerView.rot;
      if (needStatic) {
        const canvas =
          this._staticCache?.canvas || document.createElement("canvas");
        canvas.width = this._canvas.width;
        canvas.height = this._canvas.height;
        const sctx = canvas.getContext("2d");
        sctx.setTransform(1, 0, 0, 1, 0, 0);
        sctx.clearRect(0, 0, canvas.width, canvas.height);
        this._drawStaticLayer(sctx, dpr, w, h, colors);
        this._staticCache = { canvas, sig: staticSig, view: layerView };
      }
      if (needPath) {
        const canvas =
          this._pathCache?.canvas || document.createElement("canvas");
        canvas.width = this._canvas.width;
        canvas.height = this._canvas.height;
        const pctx = canvas.getContext("2d");
        pctx.setTransform(1, 0, 0, 1, 0, 0);
        pctx.clearRect(0, 0, canvas.width, canvas.height);
        this._drawPathLayer(pctx, dpr, colors);
        this._pathCache = { canvas, sig: pathSig, view: layerView };
      }
      view.tx = liveTx;
      view.ty = liveTy;
      view.scale = liveScale;
      this._rot = liveRot;
    }

    // Composite both cached layers with the transform that maps the baseline
    // view to the live view: identity when idle → pixel-crisp; a pure
    // translation while panning → still crisp; a scale/rotation during a pinch
    // → briefly resampled, then re-rasterized sharp once the gesture settles.
    const k = view.scale / layerView.scale;
    const dth = this._rot - layerView.rot;
    const rc = Math.cos(dth);
    const rs = Math.sin(dth);
    const a = k * rc;
    const b = k * rs;
    const c = -k * rs;
    const d = k * rc;
    const e = dpr * view.tx - (a * dpr * layerView.tx + c * dpr * layerView.ty);
    const f = dpr * view.ty - (b * dpr * layerView.tx + d * dpr * layerView.ty);
    ctx.setTransform(a, b, c, d, e, f);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(this._staticCache.canvas, 0, 0);
    ctx.drawImage(this._pathCache.canvas, 0, 0);

    // Layer 3: dynamic (robot marker + pulse) straight onto the main canvas
    this._drawRobot(ctx, dpr, view, colors);

    this._drawScaleBar(ctx, view, w, h, colors);

    // The live frame is now on screen: drop the mount-time overlay, and stash
    // this frame (throttled — toDataURL isn't free) so the next mount can show
    // it instantly instead of flickering through a blank canvas.
    if (this._frameImg && this._frameImg.classList.contains("show")) {
      this._frameImg.classList.remove("show");
    }
    const now = window.performance.now();
    if (now - this._frameStamp > 800) {
      this._frameStamp = now;
      try {
        FRAME_MEMO.set(
          this._config.entity,
          this._canvas.toDataURL("image/webp", 0.6)
        );
      } catch (e) {
        /* toDataURL can throw on a tainted canvas — just skip caching */
      }
    }
  }

  _drawStaticLayer(ctx, dpr, w, h, colors) {
    const view = this._view;
    const scene = this._scene;
    this._applyWorldTransform(ctx, dpr);
    const lw = (pixels) => pixels / view.scale;

    const tracePolygon = (points) => {
      ctx.moveTo(points[0][0], points[0][1]);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i][0], points[i][1]);
      }
      ctx.closePath();
    };
    const fillStrokePolys = (polys, fill, stroke, widthPx) => {
      for (const points of polys) {
        if (points.length < 3) {
          continue;
        }
        ctx.beginPath();
        tracePolygon(points);
        if (fill) {
          ctx.fillStyle = fill;
          ctx.fill();
        }
        if (stroke) {
          ctx.strokeStyle = stroke;
          ctx.lineWidth = lw(widthPx || 1);
          ctx.stroke();
        }
      }
    };
    const strokeLines = (lines, stroke, widthPx, dash) => {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = lw(widthPx);
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.setLineDash(dash ? dash.map(lw) : []);
      for (const line of lines) {
        if (line.length < 2) {
          continue;
        }
        ctx.beginPath();
        ctx.moveTo(line[0][0], line[0][1]);
        for (let i = 1; i < line.length; i++) {
          ctx.lineTo(line[i][0], line[i][1]);
        }
        ctx.stroke();
      }
      ctx.setLineDash([]);
    };

    this._drawGrid(ctx, view, w, h, colors);

    for (const region of scene.regions) {
      if (region.boundary.length >= 3) {
        ctx.beginPath();
        tracePolygon(region.boundary);
        ctx.fillStyle = colors.lawn;
        ctx.fill();
        ctx.strokeStyle = colors.lawnEdge;
        ctx.lineWidth = lw(2);
        ctx.stroke();
      }
    }

    for (const region of scene.regions) {
      for (const sub of region.sub_regions) {
        if (sub.boundary.length < 3) {
          continue;
        }
        ctx.beginPath();
        tracePolygon(sub.boundary);
        for (const hole of sub.inner_boundaries || []) {
          if (hole.length >= 3) {
            tracePolygon(hole);
          }
        }
        const pending = this._pending.has(sub.id);
        ctx.fillStyle = pending
          ? colors.zonePending
          : sub.selected
            ? colors.zoneSelected
            : colors.zoneFill;
        ctx.fill("evenodd");
        // Per-zone progress shading (#197): tint the zone with the coverage
        // color, opacity scaled by how much of it is mowed this cycle.
        if (typeof sub.coverage === "number" && sub.coverage > 0.01) {
          ctx.save();
          ctx.globalAlpha = Math.min(1, sub.coverage);
          ctx.fillStyle = colors.coverage;
          ctx.fill("evenodd");
          ctx.restore();
        }
        ctx.strokeStyle = pending ? colors.robot : colors.zoneEdge;
        ctx.lineWidth = lw(pending ? 2.5 : 1.2);
        ctx.stroke();
      }
    }

    // Pass-through ("Durchfahrt") zones: orange outline like the vendor app,
    // clearly visible — they mark where the mower may cross between regions.
    fillStrokePolys(
      scene.pass_through_zones,
      colors.passThrough,
      colors.passThroughEdge,
      1.5
    );
    // Other auxiliary device geometry (required zones, tunnels) stays subtle:
    // on real lawns the device reports many of these boxes and full-strength
    // accent strokes would dominate the map.
    ctx.globalAlpha = 0.45;
    fillStrokePolys(scene.required_zones, null, colors.accent, 1);
    ctx.globalAlpha = 1;
    fillStrokePolys(scene.obstacles, colors.obstacle, null);
    fillStrokePolys(
      scene.physical_forbidden_zones,
      colors.forbidden,
      colors.forbiddenEdge,
      1.5
    );
    fillStrokePolys(
      scene.forbidden_zones,
      colors.forbidden,
      colors.forbiddenEdge,
      1.5
    );
    strokeLines(scene.virtual_walls, colors.wall, 2.5, [8, 6]);
    ctx.globalAlpha = 0.45;
    for (const tunnel of scene.tunnels) {
      fillStrokePolys(tunnel.polygons, colors.passThrough, colors.accent, 1);
      strokeLines(tunnel.polylines, colors.accent, 1.5, [4, 4]);
    }
    ctx.globalAlpha = 1;
    fillStrokePolys(scene.draw_regions, null, colors.robot, 2);

    if (this._config.show_markers && scene.markers) {
      this._drawMarkers(ctx, scene.markers, view, colors);
    }
    if (this._config.show_hotspots && scene.fault_hotspots) {
      this._drawHotspots(ctx, scene.fault_hotspots, view, colors);
    }

    // Keyboard focus ring around the focused zone (a11y), on the live layer
    // so arrow-key moves don't invalidate the cached static geometry.
    if (this._focusedZoneId !== null) {
      for (const region of scene.regions) {
        for (const sub of region.sub_regions) {
          if (sub.id !== this._focusedZoneId || sub.boundary.length < 3) {
            continue;
          }
          ctx.save();
          ctx.beginPath();
          ctx.moveTo(sub.boundary[0][0], sub.boundary[0][1]);
          for (let i = 1; i < sub.boundary.length; i++) {
            ctx.lineTo(sub.boundary[i][0], sub.boundary[i][1]);
          }
          ctx.closePath();
          ctx.strokeStyle = colors.accent;
          ctx.lineWidth = 3 / view.scale;
          ctx.setLineDash([8 / view.scale, 5 / view.scale]);
          ctx.stroke();
          ctx.restore();
        }
      }
    }

    // Labels, badges and direction arrows are screen-constant, so they are
    // gated PER ZONE by whether they actually fit inside that zone on screen
    // (its rotated bounding box): a large zone keeps its label at any zoom
    // while a small one sheds it before the glyphs overflow its boundary.
    if (this._config.show_direction) {
      this._drawDirection(ctx, scene, view, colors);
    }

    // Zone labels + badges; kept upright regardless of map rotation.
    {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const zoneWord = localize(this._hass, "zone");
      const zoneFallback = (id) =>
        `${zoneWord.charAt(0).toUpperCase()}${zoneWord.slice(1)} ${id}`;
      for (const region of scene.regions) {
        for (const sub of region.sub_regions) {
          if (!sub.center) {
            continue;
          }
          const [zoneW, zoneH] = this._zoneScreenExtent(sub);
          if (zoneW < 72 || zoneH < 36) {
            continue;
          }
          const label =
            sub.name || (sub.id !== null ? zoneFallback(sub.id) : null);
          if (!label) {
            continue;
          }
          ctx.save();
          ctx.translate(sub.center[0], sub.center[1]);
          ctx.rotate(-this._rot);
          const fontPx = 12 / view.scale;
          ctx.font = `600 ${fontPx}px sans-serif`;
          ctx.lineWidth = lw(3);
          ctx.strokeStyle = colors.bg;
          ctx.strokeText(label, 0, 0);
          ctx.fillStyle = colors.text;
          ctx.fillText(label, 0, 0);
          // Zone progress percentage during the cycle (#197); hidden when
          // untouched or (visually) complete.
          if (
            typeof sub.coverage === "number" &&
            sub.coverage > 0.005 &&
            sub.coverage < 0.995
          ) {
            const pct = `${Math.round(sub.coverage * 100)} %`;
            ctx.font = `500 ${10 / view.scale}px sans-serif`;
            ctx.strokeText(pct, 0, 14 / view.scale);
            ctx.fillText(pct, 0, 14 / view.scale);
            ctx.font = `600 ${fontPx}px sans-serif`;
          }
          // Camera-parity badges beside the label (screen-aligned frame):
          // the red mow-order number top-left, and a small orange dot
          // top-right when the zone has custom mow parameters.
          if (sub.order && sub.order > 0) {
            const r = 8 / view.scale;
            const bx = -22 / view.scale;
            const by = -16 / view.scale;
            ctx.beginPath();
            ctx.arc(bx, by, r, 0, Math.PI * 2);
            ctx.fillStyle = colors.badgeOrder;
            ctx.fill();
            ctx.strokeStyle = colors.markerOutline;
            ctx.lineWidth = 1.5 / view.scale;
            ctx.stroke();
            ctx.font = `700 ${11 / view.scale}px sans-serif`;
            ctx.fillStyle = "#fff";
            ctx.fillText(String(sub.order), bx, by + 0.5 / view.scale);
            ctx.font = `600 ${fontPx}px sans-serif`;
          }
          if (sub.params) {
            const r = 4 / view.scale;
            ctx.beginPath();
            ctx.arc(22 / view.scale, -16 / view.scale, r, 0, Math.PI * 2);
            ctx.fillStyle = colors.markerTrapped;
            ctx.fill();
            ctx.strokeStyle = colors.markerOutline;
            ctx.lineWidth = 1.2 / view.scale;
            ctx.stroke();
          }
          ctx.restore();
        }
      }
    }

    if (scene.move_target) {
      const [mx, my] = scene.move_target;
      ctx.strokeStyle = colors.accent;
      ctx.lineWidth = lw(2);
      ctx.beginPath();
      ctx.arc(mx, my, lw(9), 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(mx, my, lw(2.5), 0, Math.PI * 2);
      ctx.fillStyle = colors.accent;
      ctx.fill();
    }

    if (scene.station) {
      this._drawStation(ctx, scene.station, view, colors);
    }
  }

  /**
   * Point markers from the device map (mirrors the PNG camera's badges):
   * trapped spots as orange triangles, maintenance points as blue hexagons,
   * cross-boundary passage markers as accent diamonds. Marker size is
   * screen-constant and the shapes stay upright under map rotation.
   */
  _drawMarkers(ctx, markers, view, colors) {
    const r = 7 / view.scale;
    const drawShape = (points, sides, phase, fill) => {
      for (const point of points || []) {
        ctx.save();
        ctx.translate(point[0], point[1]);
        ctx.rotate(-this._rot);
        ctx.beginPath();
        for (let i = 0; i < sides; i++) {
          const a = phase + (i * 2 * Math.PI) / sides;
          const x = r * Math.sin(a);
          const y = -r * Math.cos(a);
          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.closePath();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = colors.markerOutline;
        ctx.lineWidth = 1.5 / view.scale;
        ctx.stroke();
        ctx.restore();
      }
    };
    drawShape(markers.cross_boundary, 4, 0, colors.accent);
    drawShape(markers.trapped, 3, 0, colors.markerTrapped);
    drawShape(markers.maintenance, 6, Math.PI / 6, colors.markerMaintenance);
  }

  /**
   * Recorded fault locations: where the mower was standing when an error
   * appeared, merged per spot by the backend. Drawn as a hollow ring so it
   * reads as an annotation rather than another device marker, with the repeat
   * count inside once a spot has caught the mower more than once -- that
   * repetition is the whole reason to look at this layer.
   *
   * Marker size is screen-constant and the text stays upright under map
   * rotation, like the other markers.
   */
  _drawHotspots(ctx, hotspots, view, colors) {
    const r = 9 / view.scale;
    for (const spot of hotspots) {
      ctx.save();
      ctx.translate(spot.x, spot.y);
      ctx.rotate(-this._rot);
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, 2 * Math.PI);
      ctx.strokeStyle = colors.markerTrapped;
      ctx.lineWidth = 2.5 / view.scale;
      ctx.stroke();
      if (spot.count > 1) {
        ctx.fillStyle = colors.markerTrapped;
        ctx.font = `${(11 / view.scale).toFixed(3)}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(spot.count), 0, 0);
      } else {
        // A single occurrence gets a dot, so the ring is never empty.
        ctx.beginPath();
        ctx.arc(0, 0, r / 3, 0, 2 * Math.PI);
        ctx.fillStyle = colors.markerTrapped;
        ctx.fill();
      }
      ctx.restore();
    }
  }

  /**
   * Configured mowing stripe direction (scene.main_direction_angle, degrees):
   * a subtle double-headed arrow per zone, aligned with the lanes the mower
   * will cut. Anchored at the device-provided zone center (always inside the
   * zone -- a concave region's averaged centroid can land off the grass),
   * nudged below the zone label. World-space direction, so it rotates with
   * the map; length is screen-constant. Stripes run both ways -> two heads.
   */
  /**
   * The zone's approximate on-screen extent [width, height] in CSS pixels:
   * its world bounding box scaled to the view and widened for the current
   * map rotation. Used to gate screen-constant glyphs (label, badges,
   * direction arrow) so they never dwarf or overflow the zone they describe.
   */
  _zoneScreenExtent(sub) {
    const boundary = sub.boundary;
    if (!boundary || boundary.length < 3 || !this._view) {
      return [0, 0];
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const point of boundary) {
      if (point[0] < minX) minX = point[0];
      if (point[0] > maxX) maxX = point[0];
      if (point[1] < minY) minY = point[1];
      if (point[1] > maxY) maxY = point[1];
    }
    const w = (maxX - minX) * this._view.scale;
    const h = (maxY - minY) * this._view.scale;
    const cos = Math.abs(Math.cos(this._rot));
    const sin = Math.abs(Math.sin(this._rot));
    return [w * cos + h * sin, w * sin + h * cos];
  }

  _drawDirection(ctx, scene, view, colors) {
    const half = 22 / view.scale;
    const head = 6 / view.scale;
    ctx.strokeStyle = colors.subtext;
    ctx.fillStyle = colors.subtext;
    ctx.lineWidth = 2 / view.scale;
    ctx.lineCap = "round";
    ctx.globalAlpha = 0.75;
    const arrowHead = (tipX, tipY, dx, dy, sign) => {
      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(
        tipX - sign * (dx * head - dy * head * 0.6),
        tipY - sign * (dy * head + dx * head * 0.6)
      );
      ctx.lineTo(
        tipX - sign * (dx * head + dy * head * 0.6),
        tipY - sign * (dy * head - dx * head * 0.6)
      );
      ctx.closePath();
      ctx.fill();
    };
    for (const region of scene.regions) {
      for (const sub of region.sub_regions) {
        // Zone-specific custom angle wins; global is the fallback.
        const angle =
          typeof sub.direction_angle === "number"
            ? sub.direction_angle
            : scene.main_direction_angle;
        if (!sub.center || typeof angle !== "number") {
          continue;
        }
        // The arrow hangs below the zone label, so it needs more vertical
        // room than the label itself before it stops fitting the zone.
        const [zoneW, zoneH] = this._zoneScreenExtent(sub);
        if (zoneW < 72 || zoneH < 84) {
          continue;
        }
        const rad = (angle * Math.PI) / 180;
        // The zone geometry is drawn in the device frame straight to canvas
        // (no y-flip), so the lane vector must use the same +y sense. The old
        // `-sin` mirrored the arrow — invisible at 0/90/180/270 (sin=0 or the
        // double-headed symmetry) but wrong at diagonal angles (issue #209).
        const dx = Math.cos(rad);
        const dy = Math.sin(rad);
        // Keep the arrow's TOP edge a constant screen gap below the zone
        // label: base gap plus the arrow's screen-vertical half-extent (a
        // vertical arrow reaches `half` back up toward the text, a
        // horizontal one not at all). Mapped through the map rotation so
        // "below" stays screen-down.
        const vertical = Math.abs(
          dx * Math.sin(this._rot) + dy * Math.cos(this._rot)
        );
        const off = 16 / view.scale + half * vertical;
        const cx = sub.center[0] + off * Math.sin(this._rot);
        const cy = sub.center[1] + off * Math.cos(this._rot);
        ctx.beginPath();
        ctx.moveTo(cx - dx * half, cy - dy * half);
        ctx.lineTo(cx + dx * half, cy + dy * half);
        ctx.stroke();
        arrowHead(cx + dx * half, cy + dy * half, dx, dy, 1);
        arrowHead(cx - dx * half, cy - dy * half, dx, dy, -1);
      }
    }
    ctx.globalAlpha = 1;
  }

  _drawPathLayer(ctx, dpr, colors) {
    const view = this._view;
    const scene = this._scene;
    this._applyWorldTransform(ctx, dpr);

    // Wi-Fi heatmap (issue #200): self-sampled by the integration from the
    // mower's own signal % at each pose. Drawn first so coverage and paths
    // stay readable on top. Green = strong, red = weak; cells are coarse
    // (the signal doesn't change at blade resolution).
    const L = this._layers();
    const wifi = L.wifi && scene.wifi_heatmap;
    if (wifi && Array.isArray(wifi.cells) && wifi.cells.length) {
      const cell = Number(wifi.cell_mm) || 1500;
      // Interpolated cells draw a touch fainter than real samples, so measured
      // ground still reads stronger than the gap-filled bridges between passes.
      for (const [gx, gy, pct, isFill] of interpolateWifiCells(wifi.cells)) {
        // <=20 % maps to red (hue 0), >=80 % to green (hue 120).
        const hue = Math.max(0, Math.min(120, ((pct - 20) / 60) * 120));
        ctx.fillStyle = `hsla(${hue}, 75%, 45%, ${isFill ? 0.22 : 0.34})`;
        ctx.fillRect(gx * cell - cell / 2, gy * cell - cell / 2, cell, cell);
      }
    }

    // Season heatmap: how many finished cycles reached each cell. Pale means
    // rarely reached, which is the whole point -- a strip the mower keeps
    // skipping looks fine in any single cycle and only shows up stacked.
    const season = L.season && scene.mow_counts;
    if (season && Array.isArray(season.cells) && season.cells.length) {
      const cell = Number(season.cell_mm) || 500;
      const max = Math.max(1, Number(season.max) || 1);
      for (const [gx, gy, count] of season.cells) {
        // Square-root ramp: the difference between one and two passes matters
        // far more than between nine and ten.
        const share = Math.sqrt(Math.max(0, Math.min(1, count / max)));
        ctx.fillStyle = `hsla(140, 70%, 40%, ${(0.12 + share * 0.5).toFixed(3)})`;
        ctx.fillRect(gx * cell - cell / 2, gy * cell - cell / 2, cell, cell);
      }
    }

    const strokePath = (points, stroke, widthWorld) => {
      if (!points || points.length < 2) {
        return;
      }
      ctx.strokeStyle = stroke;
      ctx.lineWidth = widthWorld;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      // A path is a flat list of [x, y] points with empty `[]` sentinels
      // marking run breaks: the mower stopped mowing to transit there, so the
      // pen lifts instead of drawing a straight diagonal across the gap.
      let penDown = false;
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        if (!p || p.length !== 2) {
          penDown = false; // run break — lift the pen
          continue;
        }
        if (penDown) {
          ctx.lineTo(p[0], p[1]);
        } else {
          ctx.moveTo(p[0], p[1]);
          penDown = true;
        }
      }
      ctx.stroke();
    };

    // Mowed swath beneath the thin path lines. Prefer the device-reported
    // stripe spacing (mow_spacing, mm): adjacent lanes are exactly this far
    // apart, so shading at the spacing tiles the mowed area seamlessly,
    // while the blade's wider cutting width would over-shade the overlap.
    // Tracks mowed earlier in the running session, before a mid-session
    // recharge dock (the firmware clears the realtime path on dock, issue
    // #214). One polyline per segment — never joined across the dock gap.
    let sessionPaths = Array.isArray(scene.session_paths)
      ? scene.session_paths
      : [];
    let currentPath = scene.current_path;
    let historyPath = scene.history_path;
    if (this._replay.active) {
      // Replay draws the session as far as the mower had got: the archived
      // legs and the live path clipped to one running point count, and no
      // history path at all (that is the *previous* mow).
      const clipped = this._clipRuns(this._replayRuns(), this._replay.index);
      const liveIndex = (scene.session_paths || []).filter(
        (run) => Array.isArray(run) && run.length
      ).length;
      sessionPaths = clipped.slice(0, liveIndex);
      currentPath = clipped[liveIndex] || [];
      historyPath = [];
    }
    if (L.coverage) {
      const spacing = Number(scene.mow_params && scene.mow_params.mow_spacing);
      const width =
        (spacing > 0 ? spacing : Number(scene.cutting_width)) || 320;
      for (const segment of sessionPaths) {
        strokePath(segment, colors.coverage, width);
      }
      strokePath(historyPath, colors.coverage, width);
      strokePath(currentPath, colors.coverage, width);
    }
    if (L.history) {
      strokePath(historyPath, colors.historyPath, 1.6 / view.scale);
    }
    if (L.current) {
      if (sessionPaths.length) {
        // Same colour as the live path but faded, so the whole session
        // reads as one job with its earlier legs in the background.
        ctx.globalAlpha = 0.55;
        for (const segment of sessionPaths) {
          strokePath(segment, colors.currentPath, 2.2 / view.scale);
        }
        ctx.globalAlpha = 1;
      }
      strokePath(currentPath, colors.currentPath, 2.2 / view.scale);
    }
  }

  _drawGrid(ctx, view, w, h, colors) {
    let step = 1000;
    if (!Number.isFinite(view.scale) || view.scale <= 0) {
      return;
    }
    while (step * view.scale < 28) {
      step *= 2;
    }
    // World-space AABB of the (possibly rotated) viewport
    const corners = [
      this._screenToWorld(0, 0),
      this._screenToWorld(w, 0),
      this._screenToWorld(0, h),
      this._screenToWorld(w, h),
    ];
    const minX = Math.min(...corners.map((c) => c[0]));
    const maxX = Math.max(...corners.map((c) => c[0]));
    const minY = Math.min(...corners.map((c) => c[1]));
    const maxY = Math.max(...corners.map((c) => c[1]));
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1 / view.scale;
    ctx.beginPath();
    for (let x = Math.floor(minX / step) * step; x <= maxX; x += step) {
      ctx.moveTo(x, minY);
      ctx.lineTo(x, maxY);
    }
    for (let y = Math.floor(minY / step) * step; y <= maxY; y += step) {
      ctx.moveTo(minX, y);
      ctx.lineTo(maxX, y);
    }
    ctx.stroke();
  }

  _drawStation(ctx, station, view, colors) {
    ctx.save();
    ctx.translate(station.x, station.y);
    // A house = "home / charging base": instantly readable, and drawn
    // upright (a house has no meaningful heading, so station.theta is not
    // applied). Counter-rotate the configured map rotation so it stays level.
    ctx.rotate(-this._rot);
    const s = Math.max(360, 17 / view.scale); // a touch bigger for visibility
    ctx.fillStyle = colors.station;
    // A contrasting outline so the base pops on any background (the mowed
    // area, the lawn, or bare map), per issue #214.
    ctx.strokeStyle = colors.markerOutline;
    ctx.lineWidth = s * 0.06;
    ctx.lineJoin = "round";
    // roof
    ctx.beginPath();
    ctx.moveTo(0, -0.45 * s);
    ctx.lineTo(0.45 * s, -0.05 * s);
    ctx.lineTo(-0.45 * s, -0.05 * s);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    // body
    ctx.beginPath();
    ctx.rect(-0.32 * s, -0.05 * s, 0.64 * s, 0.5 * s);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  _drawRobot(ctx, dpr, view, colors) {
    const robot = this._robot;
    if (!robot) {
      return;
    }
    const activity = this._activity();
    // The mower must be findable on the (green) mowed area, so the marker keeps
    // a fixed high-contrast colour instead of the green "mowing" activity tint
    // that blended in (#214); a real fault still shows red. The activity itself
    // is already spelled out in the HUD chip.
    const markerColor =
      activity === "error"
        ? this._activityColor("error", colors)
        : colors.robot;

    let { x, y } = robot;
    let animating = false;
    // Ease between consecutive pose pushes so the marker glides.
    if (this._robotPrev) {
      const t = Math.min(1, (performance.now() - this._robotAnimStart) / 400);
      const s = t * (2 - t); // ease-out
      x = this._robotPrev.x + (robot.x - this._robotPrev.x) * s;
      y = this._robotPrev.y + (robot.y - this._robotPrev.y) * s;
      if (t < 1) {
        animating = true;
      } else {
        this._robotPrev = null;
      }
    }
    if (this._follow && animating) {
      // keep the eased marker centered too
      const [sx, sy] = this._worldToScreenRaw(x, y);
      view.tx += this._root.clientWidth / 2 - sx;
      view.ty += this._root.clientHeight / 2 - sy;
    }

    this._applyWorldTransform(ctx, dpr);
    ctx.save();
    ctx.translate(x, y);
    const size = Math.max(380, 16 / view.scale); // >= 38 cm, >= 16 px

    // Gentle pulse ring while mowing (skipped when the tab is hidden)
    const pulsing =
      activity === "mowing" && document.visibilityState === "visible";
    if (pulsing) {
      const phase = (performance.now() % 2000) / 2000;
      ctx.beginPath();
      ctx.arc(0, 0, (size / 2) * (1 + phase * 0.9), 0, Math.PI * 2);
      ctx.strokeStyle = markerColor;
      ctx.globalAlpha = 0.5 * (1 - phase);
      ctx.lineWidth = size * 0.07;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // Heading wedge is drawn nose-up (local -y); rotate so it points along
    // yaw. Must be +pi/2 (not -pi/2) or the wedge points 180° opposite the
    // real heading — issue #211.
    ctx.rotate((robot.yaw || 0) + Math.PI / 2);
    if (robot.source === "dock_fallback") {
      ctx.globalAlpha = 0.55;
    }
    ctx.beginPath();
    ctx.arc(0, 0, size / 2, 0, Math.PI * 2);
    ctx.fillStyle = markerColor;
    ctx.fill();
    ctx.strokeStyle = colors.bg;
    ctx.lineWidth = size * 0.08;
    ctx.stroke();
    // Heading wedge (nose-up before rotation)
    ctx.beginPath();
    ctx.moveTo(0, -size * 0.46);
    ctx.lineTo(size * 0.18, -size * 0.1);
    ctx.lineTo(-size * 0.18, -size * 0.1);
    ctx.closePath();
    ctx.fillStyle = colors.bg;
    ctx.fill();
    ctx.restore();

    // Keep animating while easing or pulsing; the per-frame cost is two
    // cached-layer drawImage calls plus this marker.
    if (animating || pulsing) {
      this._requestDraw();
    }
  }

  _drawScaleBar(ctx, view, w, h, colors) {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const target = 90; // px
    let best = SCALE_BAR_STEPS[0];
    for (const step of SCALE_BAR_STEPS) {
      if (
        Math.abs(step * view.scale - target) <
        Math.abs(best * view.scale - target)
      ) {
        best = step;
      }
    }
    const px = best * view.scale;
    if (px < 20 || px > 240) {
      return;
    }
    const x = 12;
    const y = h - 14;
    ctx.strokeStyle = colors.subtext;
    ctx.fillStyle = colors.subtext;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, y - 4);
    ctx.lineTo(x, y);
    ctx.lineTo(x + px, y);
    ctx.lineTo(x + px, y - 4);
    ctx.stroke();
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    const label = best >= 1000 ? `${best / 1000} m` : `${best / 10} cm`;
    ctx.fillText(label, x + px / 2, y - 3);
  }
}

/* ------------------------------------------------------- config editor */

class TerramowMapCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) {
      return;
    }
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => schema.label || schema.name;
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...this._config, ...ev.detail.value };
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      {
        name: "entity",
        label: "Entity",
        required: true,
        selector: {
          entity: { domain: "lawn_mower", integration: "terramow" },
        },
      },
      {
        name: "show_controls",
        label: "Start / pause / dock buttons",
        selector: { boolean: {} },
      },
      {
        name: "zone_selection",
        label: "Tap zones to mow",
        selector: { boolean: {} },
      },
      {
        name: "show_coverage",
        label: "Shade mowed area (cutting width)",
        selector: { boolean: {} },
      },
      {
        name: "show_wifi",
        label: "Wi-Fi heatmap overlay (green = strong)",
        selector: { boolean: {} },
      },
      {
        name: "show_history_path",
        label: "Show history path",
        selector: { boolean: {} },
      },
      {
        name: "show_current_path",
        label: "Show current path",
        selector: { boolean: {} },
      },
      { name: "show_hud", label: "Show status chips", selector: { boolean: {} } },
      {
        name: "show_maintenance",
        label: "Maintenance button (blade / base-station counters)",
        selector: { boolean: {} },
      },
      {
        name: "show_markers",
        label: "Show trapped / maintenance markers",
        selector: { boolean: {} },
      },
      {
        name: "show_replay",
        label: "Show the session replay button",
        selector: { boolean: {} },
      },
      {
        name: "show_hotspots",
        label: "Show recorded fault locations",
        selector: { boolean: {} },
      },
      {
        name: "show_direction",
        label: "Show mowing direction arrow",
        selector: { boolean: {} },
      },
      {
        name: "zone_info",
        label: "Long-press zones for their mow settings",
        selector: { boolean: {} },
      },
      {
        name: "show_layer_counts",
        label: "Debug: list received layer counts in the legend",
        selector: { boolean: {} },
      },
      {
        name: "rotate_gesture",
        label: "Two-finger rotate (compass button resets)",
        selector: { boolean: {} },
      },
      {
        name: "rotation",
        label: "Default map rotation (degrees)",
        selector: { number: { min: -180, max: 360, mode: "box" } },
      },
      {
        name: "fit_height",
        label: "Card height (px)",
        selector: { number: { min: 200, max: 1200, mode: "box" } },
      },
      {
        name: "fit_padding",
        label: "Zoom fill (fraction of card the lawn fills)",
        selector: { number: { min: 0.5, max: 1, step: 0.01, mode: "box" } },
      },
    ];

    this._renderRotationTools();
  }

  _setRotation(deg) {
    const rotation = (((Math.round(deg) % 360) + 360) % 360);
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: { ...this._config, rotation } },
        bubbles: true,
        composed: true,
      })
    );
  }

  /**
   * Quick-pick rotation presets + a "use current rotation" capture button,
   * appended below the declarative form. Capture reads the live preview's
   * rotation, which the card mirrors to localStorage (the editor and the
   * preview card are isolated DOM, so they cannot talk directly).
   */
  _renderRotationTools() {
    if (!this._rotTools) {
      this._rotTools = document.createElement("div");
      this._rotTools.className = "tm-rot-tools";
      this._rotTools.innerHTML = `
        <style>
          .tm-rot-tools { margin: 8px 4px 4px; }
          .tm-rot-tools .tm-rot-label {
            font-size: 12px; color: var(--secondary-text-color, #727272);
            margin-bottom: 6px;
          }
          .tm-rot-tools .tm-rot-row { display: flex; flex-wrap: wrap; gap: 6px; }
          .tm-rot-tools button {
            border: 1px solid var(--divider-color, rgba(0,0,0,.12));
            background: var(--card-background-color, #fff);
            color: var(--primary-text-color, #212121);
            border-radius: 16px; padding: 5px 12px; font-size: 13px; cursor: pointer;
          }
          .tm-rot-tools button:hover { border-color: var(--primary-color, #03a9f4); }
          .tm-rot-tools button.tm-capture { font-weight: 600; }
        </style>
        <div class="tm-rot-label">Default rotation presets</div>
        <div class="tm-rot-row"></div>
      `;
      const row = this._rotTools.querySelector(".tm-rot-row");
      for (const deg of [0, 90, 180, 270]) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = `${deg}°`;
        btn.addEventListener("click", () => this._setRotation(deg));
        row.appendChild(btn);
      }
      const capture = document.createElement("button");
      capture.type = "button";
      capture.className = "tm-capture";
      capture.textContent = "Use current rotation";
      capture.addEventListener("click", () => {
        let deg = null;
        try {
          const raw = window.localStorage.getItem(
            LIVE_ROT_KEY + (this._config && this._config.entity)
          );
          if (raw !== null) {
            deg = Number(raw);
          }
        } catch (e) {
          deg = null;
        }
        if (Number.isFinite(deg)) {
          this._setRotation(deg);
        }
      });
      row.appendChild(capture);
      this.appendChild(this._rotTools);
    }
  }
}

// The card's own string table, reachable from the element class so the
// language-parity gate can check every table against English on the real
// object instead of re-parsing this file (issue #337). Nothing in the card
// reads it from here — localize() closes over STRINGS directly.
TerramowMapCard.STRINGS = STRINGS;

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, TerramowMapCard);
  customElements.define(`${CARD_TAG}-editor`, TerramowMapCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "TerraMow Map Card",
    description:
      "Interactive TerraMow lawn map: live position, mow controls, coverage, tap-to-mow zones.",
    preview: false,
    documentationURL: "https://github.com/it-rec/TerraMowHA",
  });
}
