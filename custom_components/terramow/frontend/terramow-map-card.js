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
/* Keys: no_map, not_connected, start, clear, zone, zones, reset_view,
   follow, start_mowing, pause, dock, sent, missing_entity */
const STRINGS = {
  en: { no_map: "No map available yet", not_connected: "Waiting for mower data…", start: "Mow", clear: "Clear", zone: "zone", zones: "zones", reset_view: "Fit map to view", reset_rotation: "Reset to default rotation", follow: "Follow the mower", replay: "Replay this session", replay_play: "Play the replay", start_mowing: "Start mowing", pause: "Pause", hud_progress: "Progress", hud_eta_left: "left", dock: "Return to dock", sent: "Zone mowing started", preflight_none: "Not enough comparable history", preflight_estimate: "Estimate", preflight_battery: "battery", preflight_recharges: "recharges", preflight_daylight: "may finish after sunset", missing_entity: "Set a TerraMow lawn mower entity in the card config", zi_cut_height: "Cut height", zi_speed: "Mow speed", zi_spacing: "Stripe spacing", zi_blade: "Blade speed", zi_edge: "Edge cutting", zi_direction: "Direction", zi_order: "Mow order", zi_custom: "Custom settings", zi_global: "Global settings", lvl_low: "Low", lvl_medium: "Medium", lvl_high: "High", kbd_selected: "selected", legend: "Legend", legend_show: "Show legend", legend_hide: "Hide legend", lg_zone: "Mowing zone", lg_zone_pending: "Selected to mow", lg_mower: "Mower position", lg_dock: "Charging base", lg_order: "Mow order", lg_custom: "Custom zone settings", lg_direction: "Mow direction", lg_stuck: "Got stuck here", lg_hotspot: "Fault happened here (repeat count)", lg_maint: "Maintenance point", lg_passage: "Passage point", lg_nogo: "No-go zone", lg_wall: "Virtual wall", lg_coverage: "Mowed area", lg_wifi: "Wi-Fi signal (green = strong)", view_mode: "View", vw_beides: "Both", vw_weg: "Path", vw_flaeche: "Area", vw_wlan: "Wi-Fi", vw_saison: "Season", lg_season: "Times mowed (pale = rarely)", map_refreshing: "Map refreshing…", dbg_title: "Layers received", dbg_zones: "Zones", dbg_nogo: "No-go zones", dbg_walls: "Walls", dbg_obstacles: "Obstacles", dbg_passthrough: "Pass-through", dbg_required: "Required", dbg_tunnels: "Tunnels", dbg_markers: "Markers", dbg_draw: "Draw regions", dbg_paths: "Path points" },
  bg: { no_map: "Все още няма карта", not_connected: "Изчакване на данни от косачката…", start: "Коси", clear: "Изчисти", zone: "зона", zones: "зони", reset_view: "Побери картата", follow: "Следвай косачката", start_mowing: "Започни косене", pause: "Пауза", dock: "Върни към станцията", sent: "Косенето на зони започна", missing_entity: "Задайте обект на косачка TerraMow в конфигурацията" },
  ca: { no_map: "Encara no hi ha mapa", not_connected: "Esperant dades del tallagespa…", start: "Sega", clear: "Neteja", zone: "zona", zones: "zones", reset_view: "Ajusta el mapa", follow: "Segueix el tallagespa", start_mowing: "Comença a segar", pause: "Pausa", dock: "Torna a la base", sent: "Sega per zones iniciada", missing_entity: "Configureu una entitat de tallagespa TerraMow" },
  cs: { no_map: "Mapa zatím není k dispozici", not_connected: "Čekání na data sekačky…", start: "Sekat", clear: "Vymazat", zone: "zóna", zones: "zóny", reset_view: "Přizpůsobit mapu", follow: "Sledovat sekačku", start_mowing: "Zahájit sekání", pause: "Pozastavit", dock: "Zpět na stanici", sent: "Sekání zón zahájeno", missing_entity: "Nastavte entitu sekačky TerraMow v konfiguraci karty" },
  da: { no_map: "Intet kort tilgængeligt endnu", not_connected: "Venter på data fra plæneklipperen…", start: "Klip", clear: "Ryd", zone: "zone", zones: "zoner", reset_view: "Tilpas kortet", follow: "Følg plæneklipperen", start_mowing: "Start klipning", pause: "Pause", dock: "Kør til base", sent: "Zoneklipning startet", missing_entity: "Angiv en TerraMow-plæneklipperentitet i kortets konfiguration" },
  de: { no_map: "Noch keine Karte verfügbar", not_connected: "Warte auf Mäherdaten…", start: "Mähen", clear: "Leeren", zone: "Zone", zones: "Zonen", reset_view: "Karte einpassen", reset_rotation: "Auf Standarddrehung zurücksetzen", follow: "Dem Mäher folgen", replay: "Diese Sitzung abspielen", replay_play: "Wiedergabe starten", start_mowing: "Mähen starten", pause: "Pausieren", hud_progress: "Fortschritt", hud_eta_left: "übrig", dock: "Zur Station", sent: "Zonenmähen gestartet", missing_entity: "TerraMow-Mäher-Entität in der Kartenkonfiguration setzen", zi_cut_height: "Schnitthöhe", zi_speed: "Mähgeschwindigkeit", zi_spacing: "Bahnabstand", zi_blade: "Messerdrehzahl", zi_edge: "Kantenschnitt", zi_direction: "Richtung", zi_order: "Mähreihenfolge", zi_custom: "Eigene Einstellungen", zi_global: "Globale Einstellungen", lvl_low: "Niedrig", lvl_medium: "Mittel", lvl_high: "Hoch", kbd_selected: "ausgewählt", legend: "Legende", legend_show: "Legende anzeigen", legend_hide: "Legende ausblenden", lg_zone: "Rasenmähzone", lg_zone_pending: "Zum Mähen ausgewählt", lg_mower: "Mäherposition", lg_dock: "Ladestation", lg_order: "Mähreihenfolge", lg_custom: "Eigene Zoneneinstellungen", lg_direction: "Mährichtung", lg_stuck: "Hier steckengeblieben", lg_hotspot: "Hier trat eine Störung auf (Anzahl)", lg_maint: "Wartungspunkt", lg_passage: "Durchgangspunkt", lg_nogo: "Sperrzone", lg_wall: "Virtuelle Wand", lg_coverage: "Gemähte Fläche", lg_wifi: "WLAN-Signal (grün = stark)", view_mode: "Ansicht", vw_beides: "Beides", vw_weg: "Weg", vw_flaeche: "Fläche", vw_wlan: "WLAN", vw_saison: "Saison", lg_season: "Mähhäufigkeit (blass = selten)", map_refreshing: "Karte wird aktualisiert…", dbg_title: "Empfangene Ebenen", dbg_zones: "Zonen", dbg_nogo: "Sperrzonen", dbg_walls: "Wände", dbg_obstacles: "Hindernisse", dbg_passthrough: "Durchgänge", dbg_required: "Pflichtzonen", dbg_tunnels: "Tunnel", dbg_markers: "Markierungen", dbg_draw: "Zeichenregionen", dbg_paths: "Pfadpunkte" },
  el: { no_map: "Δεν υπάρχει ακόμη χάρτης", not_connected: "Αναμονή δεδομένων χλοοκοπτικού…", start: "Κούρεμα", clear: "Καθαρισμός", zone: "ζώνη", zones: "ζώνες", reset_view: "Προσαρμογή χάρτη", follow: "Ακολούθησε το χλοοκοπτικό", start_mowing: "Έναρξη κουρέματος", pause: "Παύση", dock: "Επιστροφή στη βάση", sent: "Το κούρεμα ζωνών ξεκίνησε", missing_entity: "Ορίστε οντότητα χλοοκοπτικού TerraMow στη διαμόρφωση" },
  es: { no_map: "Aún no hay mapa disponible", not_connected: "Esperando datos del cortacésped…", start: "Cortar", clear: "Borrar", zone: "zona", zones: "zonas", reset_view: "Ajustar mapa", follow: "Seguir al cortacésped", start_mowing: "Iniciar corte", pause: "Pausar", dock: "Volver a la base", sent: "Corte por zonas iniciado", missing_entity: "Configura la entidad del cortacésped TerraMow" },
  et: { no_map: "Kaarti pole veel saadaval", not_connected: "Ootan niiduki andmeid…", start: "Niida", clear: "Tühjenda", zone: "tsoon", zones: "tsooni", reset_view: "Mahuta kaart", follow: "Jälgi niidukit", start_mowing: "Alusta niitmist", pause: "Paus", dock: "Tagasi baasi", sent: "Tsooniniitmine alustatud", missing_entity: "Määra kaardi seadetes TerraMow niiduki olem" },
  fi: { no_map: "Karttaa ei vielä saatavilla", not_connected: "Odotetaan leikkurin tietoja…", start: "Leikkaa", clear: "Tyhjennä", zone: "vyöhyke", zones: "vyöhykettä", reset_view: "Sovita kartta", follow: "Seuraa leikkuria", start_mowing: "Aloita leikkuu", pause: "Tauko", dock: "Palaa asemalle", sent: "Vyöhykeleikkuu aloitettu", missing_entity: "Aseta TerraMow-leikkurientiteetti kortin asetuksissa" },
  fr: { no_map: "Aucune carte disponible", not_connected: "En attente des données de la tondeuse…", start: "Tondre", clear: "Effacer", zone: "zone", zones: "zones", reset_view: "Ajuster la carte", follow: "Suivre la tondeuse", start_mowing: "Démarrer la tonte", pause: "Pause", dock: "Retour à la base", sent: "Tonte de zone démarrée", missing_entity: "Définissez l'entité tondeuse TerraMow dans la configuration" },
  hr: { no_map: "Karta još nije dostupna", not_connected: "Čekanje podataka kosilice…", start: "Kosi", clear: "Očisti", zone: "zona", zones: "zone", reset_view: "Prilagodi kartu", follow: "Prati kosilicu", start_mowing: "Pokreni košnju", pause: "Pauza", dock: "Povratak na stanicu", sent: "Košnja zona pokrenuta", missing_entity: "Postavite entitet TerraMow kosilice u konfiguraciji kartice" },
  hu: { no_map: "Még nincs elérhető térkép", not_connected: "Várakozás a fűnyíró adataira…", start: "Nyírás", clear: "Törlés", zone: "zóna", zones: "zóna", reset_view: "Térkép igazítása", follow: "Fűnyíró követése", start_mowing: "Nyírás indítása", pause: "Szünet", dock: "Vissza a dokkolóba", sent: "Zónanyírás elindítva", missing_entity: "Állítson be TerraMow fűnyíró entitást a kártya beállításaiban" },
  it: { no_map: "Nessuna mappa disponibile", not_connected: "In attesa dei dati del robot…", start: "Taglia", clear: "Svuota", zone: "zona", zones: "zone", reset_view: "Adatta mappa", follow: "Segui il rasaerba", start_mowing: "Avvia taglio", pause: "Pausa", dock: "Torna alla base", sent: "Taglio a zone avviato", missing_entity: "Imposta l'entità del rasaerba TerraMow nella configurazione" },
  ja: { no_map: "マップはまだありません", not_connected: "芝刈り機のデータを待機中…", start: "刈る", clear: "クリア", zone: "ゾーン", zones: "ゾーン", reset_view: "マップを全体表示", follow: "芝刈り機を追跡", start_mowing: "芝刈り開始", pause: "一時停止", dock: "ドックに戻る", sent: "ゾーン芝刈りを開始しました", missing_entity: "カード設定でTerraMow芝刈り機エンティティを設定してください" },
  ko: { no_map: "아직 지도가 없습니다", not_connected: "잔디깎이 데이터 대기 중…", start: "깎기", clear: "지우기", zone: "구역", zones: "구역", reset_view: "지도 맞추기", follow: "잔디깎이 따라가기", start_mowing: "잔디깎기 시작", pause: "일시정지", dock: "도크로 복귀", sent: "구역 잔디깎기 시작됨", missing_entity: "카드 설정에서 TerraMow 잔디깎이 엔티티를 설정하세요" },
  lt: { no_map: "Žemėlapio dar nėra", not_connected: "Laukiama vejapjovės duomenų…", start: "Pjauti", clear: "Išvalyti", zone: "zona", zones: "zonos", reset_view: "Sutalpinti žemėlapį", follow: "Sekti vejapjovę", start_mowing: "Pradėti pjovimą", pause: "Pristabdyti", dock: "Grįžti į stotelę", sent: "Zonų pjovimas pradėtas", missing_entity: "Kortelės nustatymuose nurodykite TerraMow vejapjovės objektą" },
  lv: { no_map: "Karte vēl nav pieejama", not_connected: "Gaida pļāvēja datus…", start: "Pļaut", clear: "Notīrīt", zone: "zona", zones: "zonas", reset_view: "Ietilpināt karti", follow: "Sekot pļāvējam", start_mowing: "Sākt pļaušanu", pause: "Pauze", dock: "Atgriezties stacijā", sent: "Zonu pļaušana sākta", missing_entity: "Kartītes konfigurācijā iestatiet TerraMow pļāvēja entītiju" },
  nb: { no_map: "Ingen kart tilgjengelig ennå", not_connected: "Venter på data fra gressklipperen…", start: "Klipp", clear: "Tøm", zone: "sone", zones: "soner", reset_view: "Tilpass kartet", follow: "Følg gressklipperen", start_mowing: "Start klipping", pause: "Pause", dock: "Tilbake til basen", sent: "Soneklipping startet", missing_entity: "Angi en TerraMow-gressklipperentitet i kortkonfigurasjonen" },
  nl: { no_map: "Nog geen kaart beschikbaar", not_connected: "Wachten op maaierdata…", start: "Maaien", clear: "Wissen", zone: "zone", zones: "zones", reset_view: "Kaart passend maken", follow: "Volg de maaier", start_mowing: "Maaien starten", pause: "Pauzeren", dock: "Terug naar dock", sent: "Zonemaaien gestart", missing_entity: "Stel een TerraMow-maaierentiteit in bij de kaartconfiguratie" },
  pl: { no_map: "Mapa nie jest jeszcze dostępna", not_connected: "Oczekiwanie na dane kosiarki…", start: "Koś", clear: "Wyczyść", zone: "strefa", zones: "strefy", reset_view: "Dopasuj mapę", follow: "Śledź kosiarkę", start_mowing: "Rozpocznij koszenie", pause: "Wstrzymaj", dock: "Wróć do stacji", sent: "Rozpoczęto koszenie stref", missing_entity: "Ustaw encję kosiarki TerraMow w konfiguracji karty" },
  pt: { no_map: "Ainda não há mapa disponível", not_connected: "A aguardar dados do corta-relva…", start: "Cortar", clear: "Limpar", zone: "zona", zones: "zonas", reset_view: "Ajustar mapa", follow: "Seguir o corta-relva", start_mowing: "Iniciar corte", pause: "Pausar", dock: "Voltar à base", sent: "Corte por zonas iniciado", missing_entity: "Defina a entidade do corta-relva TerraMow na configuração" },
  "pt-BR": { no_map: "Nenhum mapa disponível ainda", not_connected: "Aguardando dados do cortador…", start: "Cortar", clear: "Limpar", zone: "zona", zones: "zonas", reset_view: "Ajustar mapa", follow: "Seguir o cortador", start_mowing: "Iniciar corte", pause: "Pausar", dock: "Voltar à base", sent: "Corte por zonas iniciado", missing_entity: "Defina a entidade do cortador TerraMow na configuração do cartão" },
  ro: { no_map: "Încă nu există hartă", not_connected: "Se așteaptă datele mașinii de tuns…", start: "Tunde", clear: "Golește", zone: "zonă", zones: "zone", reset_view: "Potrivește harta", follow: "Urmărește mașina", start_mowing: "Pornește tunderea", pause: "Pauză", dock: "Înapoi la stație", sent: "Tunderea pe zone a început", missing_entity: "Setați entitatea mașinii de tuns TerraMow în configurația cardului" },
  ru: { no_map: "Карта пока недоступна", not_connected: "Ожидание данных газонокосилки…", start: "Косить", clear: "Очистить", zone: "зона", zones: "зоны", reset_view: "Вписать карту", follow: "Следовать за косилкой", start_mowing: "Начать стрижку", pause: "Пауза", dock: "Вернуться на базу", sent: "Стрижка зон начата", missing_entity: "Укажите сущность газонокосилки TerraMow в настройках карточки" },
  sk: { no_map: "Mapa zatiaľ nie je k dispozícii", not_connected: "Čaká sa na údaje kosačky…", start: "Kosiť", clear: "Vymazať", zone: "zóna", zones: "zóny", reset_view: "Prispôsobiť mapu", follow: "Sledovať kosačku", start_mowing: "Spustiť kosenie", pause: "Pozastaviť", dock: "Späť na stanicu", sent: "Kosenie zón spustené", missing_entity: "Nastavte entitu kosačky TerraMow v konfigurácii karty" },
  sl: { no_map: "Zemljevid še ni na voljo", not_connected: "Čakanje na podatke kosilnice…", start: "Kosi", clear: "Počisti", zone: "cona", zones: "cone", reset_view: "Prilagodi zemljevid", follow: "Sledi kosilnici", start_mowing: "Začni košnjo", pause: "Premor", dock: "Nazaj na postajo", sent: "Košnja con se je začela", missing_entity: "Nastavite entiteto kosilnice TerraMow v konfiguraciji kartice" },
  sr: { no_map: "Мапа још није доступна", not_connected: "Чекање података косачице…", start: "Коси", clear: "Очисти", zone: "зона", zones: "зоне", reset_view: "Уклопи мапу", follow: "Прати косачицу", start_mowing: "Покрени кошење", pause: "Пауза", dock: "Назад на станицу", sent: "Кошење зона покренуто", missing_entity: "Подесите ентитет TerraMow косачице у конфигурацији картице" },
  sv: { no_map: "Ingen karta tillgänglig ännu", not_connected: "Väntar på data från gräsklipparen…", start: "Klipp", clear: "Rensa", zone: "zon", zones: "zoner", reset_view: "Anpassa kartan", follow: "Följ gräsklipparen", start_mowing: "Starta klippning", pause: "Pausa", dock: "Åter till basen", sent: "Zonklippning startad", missing_entity: "Ange en TerraMow-gräsklipparentitet i kortets konfiguration" },
  tr: { no_map: "Henüz harita yok", not_connected: "Çim biçme makinesi verileri bekleniyor…", start: "Biç", clear: "Temizle", zone: "bölge", zones: "bölge", reset_view: "Haritayı sığdır", follow: "Makineyi takip et", start_mowing: "Biçmeyi başlat", pause: "Duraklat", dock: "İstasyona dön", sent: "Bölge biçme başlatıldı", missing_entity: "Kart yapılandırmasında bir TerraMow çim biçme varlığı ayarlayın" },
  uk: { no_map: "Мапа поки недоступна", not_connected: "Очікування даних газонокосарки…", start: "Косити", clear: "Очистити", zone: "зона", zones: "зони", reset_view: "Вписати мапу", follow: "Слідкувати за косаркою", start_mowing: "Почати косіння", pause: "Пауза", dock: "Повернутися на базу", sent: "Косіння зон розпочато", missing_entity: "Вкажіть сутність газонокосарки TerraMow у налаштуваннях картки" },
  "zh-Hans": { no_map: "暂无地图", not_connected: "等待割草机数据…", start: "开始割草", clear: "清除", zone: "个区域", zones: "个区域", reset_view: "适配地图视图", follow: "跟随割草机", start_mowing: "开始割草", pause: "暂停", dock: "返回充电站", sent: "已开始选区割草", missing_entity: "请在卡片配置中设置 TerraMow 割草机实体" },
  "zh-Hant": { no_map: "尚無地圖", not_connected: "等待割草機資料…", start: "開始割草", clear: "清除", zone: "個區域", zones: "個區域", reset_view: "縮放至全圖", follow: "跟隨割草機", start_mowing: "開始割草", pause: "暫停", dock: "返回充電站", sent: "已開始選區割草", missing_entity: "請在卡片設定中設定 TerraMow 割草機實體" },
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
      if (this._follow && this._robot) {
        this._centerOnRobot();
      }
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
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId: this._config.entity },
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
