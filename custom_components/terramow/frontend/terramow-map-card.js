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
 *   show_history_path: true    # faded, previously mowed path
 *   show_current_path: true    # path of the running job
 *   zone_selection: true       # tap zones to start a selective mow
 *   show_hud: true             # status chips (state, battery, progress)
 *   rotation: 0                # rotate the map view (degrees)
 *   fit_height: 420            # card canvas height in px
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
  en: { no_map: "No map available yet", not_connected: "Waiting for mower data…", start: "Mow", clear: "Clear", zone: "zone", zones: "zones", reset_view: "Fit map to view", follow: "Follow the mower", start_mowing: "Start mowing", pause: "Pause", dock: "Return to dock", sent: "Zone mowing started", missing_entity: "Set a TerraMow lawn mower entity in the card config" },
  bg: { no_map: "Все още няма карта", not_connected: "Изчакване на данни от косачката…", start: "Коси", clear: "Изчисти", zone: "зона", zones: "зони", reset_view: "Побери картата", follow: "Следвай косачката", start_mowing: "Започни косене", pause: "Пауза", dock: "Върни към станцията", sent: "Косенето на зони започна", missing_entity: "Задайте обект на косачка TerraMow в конфигурацията" },
  ca: { no_map: "Encara no hi ha mapa", not_connected: "Esperant dades del tallagespa…", start: "Sega", clear: "Neteja", zone: "zona", zones: "zones", reset_view: "Ajusta el mapa", follow: "Segueix el tallagespa", start_mowing: "Comença a segar", pause: "Pausa", dock: "Torna a la base", sent: "Sega per zones iniciada", missing_entity: "Configureu una entitat de tallagespa TerraMow" },
  cs: { no_map: "Mapa zatím není k dispozici", not_connected: "Čekání na data sekačky…", start: "Sekat", clear: "Vymazat", zone: "zóna", zones: "zóny", reset_view: "Přizpůsobit mapu", follow: "Sledovat sekačku", start_mowing: "Zahájit sekání", pause: "Pozastavit", dock: "Zpět na stanici", sent: "Sekání zón zahájeno", missing_entity: "Nastavte entitu sekačky TerraMow v konfiguraci karty" },
  da: { no_map: "Intet kort tilgængeligt endnu", not_connected: "Venter på data fra plæneklipperen…", start: "Klip", clear: "Ryd", zone: "zone", zones: "zoner", reset_view: "Tilpas kortet", follow: "Følg plæneklipperen", start_mowing: "Start klipning", pause: "Pause", dock: "Kør til base", sent: "Zoneklipning startet", missing_entity: "Angiv en TerraMow-plæneklipperentitet i kortets konfiguration" },
  de: { no_map: "Noch keine Karte verfügbar", not_connected: "Warte auf Mäherdaten…", start: "Mähen", clear: "Leeren", zone: "Zone", zones: "Zonen", reset_view: "Karte einpassen", follow: "Dem Mäher folgen", start_mowing: "Mähen starten", pause: "Pausieren", dock: "Zur Station", sent: "Zonenmähen gestartet", missing_entity: "TerraMow-Mäher-Entität in der Kartenkonfiguration setzen" },
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

const ICONS = {
  play: "M8,5.14V19.14L19,12.14L8,5.14Z",
  pause: "M14,19H18V5H14M6,19H10V5H6V19Z",
  dock: "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z",
  fit: "M9.5,13.09L10.92,14.5L6.41,19H10V21H3V14H5V17.59L9.5,13.09M10.91,9.5L9.5,10.91L5,6.41V10H3V3H10V5H6.41L10.91,9.5M14.5,13.09L19,17.59V14H21V21H14V19H17.59L13.08,14.5L14.5,13.09M13.09,9.5L17.59,5H14V3H21V10H19V6.41L14.5,10.91L13.09,9.5Z",
  follow: "M12,8A4,4 0 0,1 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12A4,4 0 0,1 12,8M3.05,13H1V11H3.05C3.5,6.83 6.83,3.5 11,3.05V1H13V3.05C17.17,3.5 20.5,6.83 20.95,11H23V13H20.95C20.5,17.17 17.17,20.5 13,20.95V23H11V20.95C6.83,20.5 3.5,17.17 3.05,13M12,5A7,7 0 0,0 5,12A7,7 0 0,0 12,19A7,7 0 0,0 19,12A7,7 0 0,0 12,5Z",
  battery: "M16,18H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  batteryCharging: "M16,20H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.66C6,21.4 6.6,22 7.33,22H16.66C17.4,22 18,21.4 18,20.66V5.33C18,4.6 17.4,4 16.67,4M11,20V14.5H9L13,7V12.5H15L11,20Z",
};

function svgIcon(path) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${path}"/></svg>`;
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
 */
function decimatePath(points, cap) {
  while (points.length > cap) {
    let write = 0;
    for (let read = 0; read < points.length; read += 2) {
      points[write++] = points[read];
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
    this._robotPrev = null;
    this._robotAnimStart = 0;
    this._view = null; // {scale, tx, ty}
    this._follow = false;
    this._pending = new Set(); // sub-region ids tapped by the user
    this._pointers = new Map();
    this._dragged = false;
    this._pinchStart = null;
    this._unsub = null;
    this._subscribedEntity = null;
    this._resizeObserver = null;
    this._rafHandle = 0;
    this._lastFrameTs = 0;
    this._lastEntityState = null;
    this._staticCache = null; // {canvas, sig}
    this._pathCache = null; // {canvas, sig}
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
      zone_selection: true,
      show_hud: true,
      show_controls: true,
      rotation: 0,
      fit_height: 420,
      ...config,
    };
    this._rot = ((Number(this._config.rotation) || 0) * Math.PI) / 180;
    this._buildDom();
    this._staticCache = null;
    this._pathCache = null;
    this._resubscribe();
    this._requestDraw();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._unsub) {
      this._resubscribe();
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
    this._resubscribe();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
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
      this._sceneRev += 1;
      this._pathRev += 1;
      this._pruneStaleSelection();
      if (!hadScene && this._hasGeometry()) {
        this._fitView();
      }
      this._updateHud();
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
      if (this._follow && this._robot) {
        this._centerOnRobot();
      }
      this._updateHud();
      this._updateButtons();
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
  }

  /* --------------------------------------------------------------- DOM */

  _buildDom() {
    if (this._root) {
      this._root.style.height = `${this._config.fit_height}px`;
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
      .chip .dot {
        width: 8px; height: 8px; border-radius: 50%; flex: none;
        background: var(--secondary-text-color, #727272);
      }
      .chip.state { text-transform: capitalize; }
      .wrap.narrow .chip.map { display: none; }
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
    `;

    const card = document.createElement("ha-card");
    const wrap = document.createElement("div");
    wrap.className = "wrap";
    wrap.style.height = `${this._config.fit_height}px`;
    this._root = wrap;

    this._canvas = document.createElement("canvas");
    this._canvas.className = "main";
    // The canvas is a status surface for assistive tech; the actionable
    // controls live in the labelled button rows beside it.
    this._canvas.setAttribute("role", "img");
    wrap.appendChild(this._canvas);

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
    side.append(this._fitBtn, this._followBtn);
    wrap.appendChild(side);

    // bottom-right: contextual mow controls
    this._controls = document.createElement("div");
    this._controls.className = "controls";
    wrap.appendChild(this._controls);

    this._actionBar = document.createElement("div");
    this._actionBar.className = "actions";
    this._actionNames = document.createElement("span");
    this._actionNames.className = "names";
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
    this._actionBar.append(this._actionNames, this._goBtn, this._clearBtn);
    wrap.appendChild(this._actionBar);

    this._msg = document.createElement("div");
    this._msg.className = "msg";
    wrap.appendChild(this._msg);

    card.appendChild(wrap);
    this.shadowRoot.replaceChildren(style, card);

    this._bindPointerEvents();
    this._resizeObserver = new ResizeObserver(() => {
      this._root.classList.toggle("narrow", this._root.clientWidth < 420);
      this._syncCanvasSize();
      this._requestDraw();
    });
    this._resizeObserver.observe(wrap);
    this._syncCanvasSize();
    this._updateHud();
    this._updateControls();
    this._requestDraw();
  }

  _roundButton(iconPath, onClick) {
    const btn = document.createElement("button");
    btn.className = "rbtn";
    btn.innerHTML = svgIcon(iconPath);
    btn.addEventListener("click", onClick);
    return btn;
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
    if (busy && typeof progress === "number") {
      const chip = document.createElement("span");
      chip.className = "chip progress";
      chip.textContent = `${Math.round(progress)} %`;
      chips.push(chip);
    }
    if (this._scene && this._scene.map_name) {
      const chip = document.createElement("span");
      chip.className = "chip map";
      let label = this._scene.map_name;
      const area = Number(this._scene.total_area);
      if (Number.isFinite(area) && area > 0) {
        // total_area arrives in square millimetres
        label += ` · ${Math.round(area / 1e6)} m²`;
      }
      chip.textContent = label;
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
      this._actionBar.classList.remove("visible");
      return;
    }
    const zoneWord = localize(this._hass, "zone");
    const names = [];
    let areaM2 = 0;
    for (const region of this._scene?.regions || []) {
      for (const sub of region.sub_regions) {
        if (this._pending.has(sub.id)) {
          names.push(
            sub.name ||
              `${zoneWord.charAt(0).toUpperCase()}${zoneWord.slice(1)} ${sub.id}`
          );
          areaM2 += zoneAreaM2(sub);
        }
      }
    }
    let text = names.join(", ");
    if (areaM2 > 0.5) {
      text += ` · ${Math.round(areaM2)} m²`;
    }
    this._actionNames.textContent = text;
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
      if (this._pointers.size === 2) {
        const [a, b] = [...this._pointers.values()];
        this._pinchStart = {
          dist: Math.hypot(a.x - b.x, a.y - b.y),
          scale: this._view ? this._view.scale : 1,
          cx: (a.x + b.x) / 2,
          cy: (a.y + b.y) / 2,
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
          }
          this._view.tx += dx;
          this._view.ty += dy;
          this._requestDraw();
        }
      }
      this._pointers.set(ev.pointerId, cur);
      if (this._pointers.size === 2 && this._pinchStart) {
        this._dragged = true;
        this._setFollow(false);
        const [a, b] = [...this._pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist > 0 && this._pinchStart.dist > 0) {
          const factor = dist / this._pinchStart.dist;
          this._zoomAt(
            this._pinchStart.cx,
            this._pinchStart.cy,
            (this._pinchStart.scale * factor) / this._view.scale
          );
        }
      }
    });
    const endPointer = (ev) => {
      const wasTap = this._pointers.size === 1 && !this._dragged;
      this._pointers.delete(ev.pointerId);
      if (this._pointers.size < 2) {
        this._pinchStart = null;
      }
      if (!this._pointers.size) {
        this._canvas.classList.remove("dragging");
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
    this._requestDraw();
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
        if (inHole) {
          continue;
        }
        if (this._pending.has(sub.id)) {
          this._pending.delete(sub.id);
        } else {
          this._pending.add(sub.id);
        }
        this._staticCache = null; // selection tint lives on the static layer
        this._updateActionBar();
        this._requestDraw();
        return;
      }
    }
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
    if (!this._scene || !this._scene.bounds || !this._root) {
      return;
    }
    const [minX, minY, maxX, maxY] = this._scene.bounds;
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
    const scale = Math.min(w / bw, h / bh) * 0.9;
    this._view = {
      scale,
      tx: (w - bw * scale) / 2 - rMinX * scale,
      ty: (h - bh * scale) / 2 - rMinY * scale,
    };
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
      passThrough: dark ? "rgba(140,140,255,0.18)" : "rgba(90,90,220,0.12)",
      wall: dark ? "#ff8a80" : "#d32f2f",
      coverage: dark ? "rgba(48,220,187,0.20)" : "rgba(48,180,150,0.22)",
      historyPath: dark ? "rgba(180,220,180,0.35)" : "rgba(90,140,90,0.35)",
      currentPath: dark ? "#7fd4ff" : "#0288d1",
      station: dark ? "#9ccc65" : "#558b2f",
      robot: dark ? "#ffd54f" : "#f57f17",
      grid: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)",
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
    const viewSig = `${view.scale.toFixed(6)}|${view.tx.toFixed(1)}|${view.ty.toFixed(1)}|${this._rot}`;
    const sizeSig = `${this._canvas.width}x${this._canvas.height}`;

    // Layer 1: static geometry (zones, forbidden areas, walls, station …)
    const staticSig = [
      this._sceneRev,
      viewSig,
      sizeSig,
      themeSig,
      [...this._pending].sort().join(","),
    ].join("§");
    if (!this._staticCache || this._staticCache.sig !== staticSig) {
      const canvas = this._staticCache?.canvas || document.createElement("canvas");
      canvas.width = this._canvas.width;
      canvas.height = this._canvas.height;
      const sctx = canvas.getContext("2d");
      sctx.setTransform(1, 0, 0, 1, 0, 0);
      sctx.clearRect(0, 0, canvas.width, canvas.height);
      this._drawStaticLayer(sctx, dpr, w, h, colors);
      this._staticCache = { canvas, sig: staticSig };
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.drawImage(this._staticCache.canvas, 0, 0, w, h);

    // Layer 2: coverage + paths (changes on every path push)
    const pathSig = [this._sceneRev, this._pathRev, viewSig, sizeSig, themeSig].join("§");
    if (!this._pathCache || this._pathCache.sig !== pathSig) {
      const canvas = this._pathCache?.canvas || document.createElement("canvas");
      canvas.width = this._canvas.width;
      canvas.height = this._canvas.height;
      const pctx = canvas.getContext("2d");
      pctx.setTransform(1, 0, 0, 1, 0, 0);
      pctx.clearRect(0, 0, canvas.width, canvas.height);
      this._drawPathLayer(pctx, dpr, colors);
      this._pathCache = { canvas, sig: pathSig };
    }
    ctx.drawImage(this._pathCache.canvas, 0, 0, w, h);

    // Layer 3: dynamic (robot marker + pulse) straight onto the main canvas
    this._drawRobot(ctx, dpr, view, colors);

    this._drawScaleBar(ctx, view, w, h, colors);
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
        ctx.strokeStyle = pending ? colors.robot : colors.zoneEdge;
        ctx.lineWidth = lw(pending ? 2.5 : 1.2);
        ctx.stroke();
      }
    }

    // Auxiliary device geometry (pass-through, required zones, tunnels) is
    // kept subtle: on real lawns the device reports many of these boxes and
    // full-strength accent strokes would dominate the map.
    ctx.globalAlpha = 0.45;
    fillStrokePolys(scene.pass_through_zones, colors.passThrough, null);
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

    // Zone labels once zones are reasonably large on screen; kept upright
    // regardless of the configured map rotation.
    if (view.scale * 2000 >= 46) {
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

  _drawPathLayer(ctx, dpr, colors) {
    const view = this._view;
    const scene = this._scene;
    this._applyWorldTransform(ctx, dpr);

    const strokePath = (points, stroke, widthWorld) => {
      if (points.length < 2) {
        return;
      }
      ctx.strokeStyle = stroke;
      ctx.lineWidth = widthWorld;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i][0], points[i][1]);
      }
      ctx.stroke();
    };

    // Mowed swath at true cutting width, beneath the thin path lines
    if (this._config.show_coverage) {
      const width = Number(scene.cutting_width) || 320;
      strokePath(scene.history_path, colors.coverage, width);
      strokePath(scene.current_path, colors.coverage, width);
    }
    if (this._config.show_history_path) {
      strokePath(scene.history_path, colors.historyPath, 1.6 / view.scale);
    }
    if (this._config.show_current_path) {
      strokePath(scene.current_path, colors.currentPath, 2.2 / view.scale);
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
    // Station body is drawn nose-up; theta rotates it into the map frame
    // (same convention as the camera renderer: theta - 90°, clockwise).
    ctx.rotate((station.theta || 0) - Math.PI / 2);
    const size = Math.max(300, 14 / view.scale); // >= 30 cm, >= 14 px
    ctx.fillStyle = colors.station;
    const r = size * 0.25;
    const x0 = -size / 2;
    const y0 = -size / 2;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(x0, y0, size, size, r);
    } else {
      ctx.rect(x0, y0, size, size);
    }
    ctx.fill();
    ctx.fillStyle = colors.bg;
    ctx.beginPath();
    ctx.arc(0, -size * 0.18, size * 0.14, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  _drawRobot(ctx, dpr, view, colors) {
    const robot = this._robot;
    if (!robot) {
      return;
    }
    const activity = this._activity();
    const markerColor =
      activity && ACTIVITY_COLORS[activity] && activity !== "docked"
        ? this._activityColor(activity, colors)
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

    ctx.rotate((robot.yaw || 0) - Math.PI / 2);
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
        name: "rotation",
        label: "Map rotation (degrees)",
        selector: { number: { min: -180, max: 180, mode: "box" } },
      },
      {
        name: "fit_height",
        label: "Card height (px)",
        selector: { number: { min: 200, max: 1200, mode: "box" } },
      },
    ];
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
