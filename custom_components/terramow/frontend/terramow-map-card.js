/**
 * TerraMow interactive map card.
 *
 * Vector map card for the TerraMow integration. Auto-registered by the
 * integration (no manual Lovelace resource needed). Subscribes to the
 * `terramow/map/subscribe` WebSocket feed for the structured scene
 * (regions, zones, forbidden areas, paths, station) and the live robot
 * pose, renders everything on a canvas with pan/zoom, and starts a
 * zone mow via the `terramow.start_select_region` service when zones
 * are tapped.
 *
 * Usage (YAML):
 *   type: custom:terramow-map-card
 *   entity: lawn_mower.terramow
 *
 * Options:
 *   show_history_path: true   # faded, previously mowed path
 *   show_current_path: true   # path of the running job
 *   zone_selection: true      # tap zones to start a selective mow
 *   show_hud: true            # top status chip
 *   fit_height: 420           # card canvas height in px
 */

"use strict";

const CARD_TAG = "terramow-map-card";

const STRINGS = {
  en: {
    no_map: "No map available yet",
    not_connected: "Waiting for mower data…",
    start: "Mow",
    clear: "Clear",
    zones: "zones",
    zone: "zone",
    reset_view: "Fit map to view",
    sent: "Zone mowing started",
    missing_entity: "Set a TerraMow lawn mower entity in the card config",
  },
  de: {
    no_map: "Noch keine Karte verfügbar",
    not_connected: "Warte auf Mäherdaten…",
    start: "Mähen",
    clear: "Leeren",
    zones: "Zonen",
    zone: "Zone",
    reset_view: "Karte einpassen",
    sent: "Zonenmähen gestartet",
    missing_entity: "TerraMow-Mäher-Entität in der Kartenkonfiguration setzen",
  },
  fr: {
    no_map: "Aucune carte disponible",
    not_connected: "En attente des données de la tondeuse…",
    start: "Tondre",
    clear: "Effacer",
    zones: "zones",
    zone: "zone",
    reset_view: "Ajuster la carte",
    sent: "Tonte de zone démarrée",
    missing_entity: "Définissez l'entité tondeuse TerraMow dans la configuration",
  },
  es: {
    no_map: "Aún no hay mapa disponible",
    not_connected: "Esperando datos del cortacésped…",
    start: "Cortar",
    clear: "Borrar",
    zones: "zonas",
    zone: "zona",
    reset_view: "Ajustar mapa",
    sent: "Corte por zonas iniciado",
    missing_entity: "Configura la entidad del cortacésped TerraMow",
  },
  it: {
    no_map: "Nessuna mappa disponibile",
    not_connected: "In attesa dei dati del robot…",
    start: "Taglia",
    clear: "Svuota",
    zones: "zone",
    zone: "zona",
    reset_view: "Adatta mappa",
    sent: "Taglio a zone avviato",
    missing_entity: "Imposta l'entità del rasaerba TerraMow nella configurazione",
  },
  nl: {
    no_map: "Nog geen kaart beschikbaar",
    not_connected: "Wachten op maaierdata…",
    start: "Maaien",
    clear: "Wissen",
    zones: "zones",
    zone: "zone",
    reset_view: "Kaart passend maken",
    sent: "Zonemaaien gestart",
    missing_entity: "Stel een TerraMow-maaierentiteit in bij de kaartconfiguratie",
  },
  pl: {
    no_map: "Mapa nie jest jeszcze dostępna",
    not_connected: "Oczekiwanie na dane kosiarki…",
    start: "Koś",
    clear: "Wyczyść",
    zones: "strefy",
    zone: "strefa",
    reset_view: "Dopasuj mapę",
    sent: "Rozpoczęto koszenie stref",
    missing_entity: "Ustaw encję kosiarki TerraMow w konfiguracji karty",
  },
  pt: {
    no_map: "Ainda não há mapa disponível",
    not_connected: "A aguardar dados do corta-relva…",
    start: "Cortar",
    clear: "Limpar",
    zones: "zonas",
    zone: "zona",
    reset_view: "Ajustar mapa",
    sent: "Corte por zonas iniciado",
    missing_entity: "Defina a entidade do corta-relva TerraMow na configuração",
  },
  cs: {
    no_map: "Mapa zatím není k dispozici",
    not_connected: "Čekání na data sekačky…",
    start: "Sekat",
    clear: "Vymazat",
    zones: "zóny",
    zone: "zóna",
    reset_view: "Přizpůsobit mapu",
    sent: "Sekání zón zahájeno",
    missing_entity: "Nastavte entitu sekačky TerraMow v konfiguraci karty",
  },
  sv: {
    no_map: "Ingen karta tillgänglig ännu",
    not_connected: "Väntar på data från gräsklipparen…",
    start: "Klipp",
    clear: "Rensa",
    zones: "zoner",
    zone: "zon",
    reset_view: "Anpassa kartan",
    sent: "Zonklippning startad",
    missing_entity: "Ange en TerraMow-gräsklipparentitet i kortets konfiguration",
  },
  "zh-Hans": {
    no_map: "暂无地图",
    not_connected: "等待割草机数据…",
    start: "开始割草",
    clear: "清除",
    zones: "个区域",
    zone: "个区域",
    reset_view: "适配地图视图",
    sent: "已开始选区割草",
    missing_entity: "请在卡片配置中设置 TerraMow 割草机实体",
  },
};

function localize(hass, key) {
  const lang = (hass && hass.language) || "en";
  const table =
    STRINGS[lang] || STRINGS[lang.split("-")[0]] || STRINGS.en;
  return table[key] || STRINGS.en[key] || key;
}

/** Ray-casting point-in-polygon. */
function pointInPolygon(x, y, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i][0];
    const yi = polygon[i][1];
    const xj = polygon[j][0];
    const yj = polygon[j][1];
    if (
      yi > y !== yj > y &&
      x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    ) {
      inside = !inside;
    }
  }
  return inside;
}

/** Nice scale-bar lengths in mm (0.1 m … 50 m). */
const SCALE_BAR_STEPS = [
  100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000,
];

class TerramowMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scene = null;
    this._robot = null;
    this._robotPrev = null;
    this._robotAnimStart = 0;
    this._view = null; // {scale, tx, ty}
    this._pending = new Set(); // sub-region ids tapped by the user
    this._pointers = new Map();
    this._dragged = false;
    this._pinchStart = null;
    this._unsub = null;
    this._subscribedEntity = null;
    this._resizeObserver = null;
    this._rafHandle = 0;
    this._lastEntityState = null;
  }

  /* ---------------------------------------------------------- card API */

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("terramow-map-card: 'entity' is required");
    }
    this._config = {
      show_history_path: true,
      show_current_path: true,
      zone_selection: true,
      show_hud: true,
      fit_height: 420,
      ...config,
    };
    this._buildDom();
    this._resubscribe();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._unsub) {
      this._resubscribe();
    }
    const state = hass && hass.states[this._config?.entity];
    const stateStr = state ? `${state.state}` : null;
    if (stateStr !== this._lastEntityState) {
      this._lastEntityState = stateStr;
      this._updateHud();
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
    this._resubscribe();
  }

  disconnectedCallback() {
    this._teardownSubscription();
  }

  /* ------------------------------------------------------ subscription */

  async _resubscribe() {
    if (!this._hass || !this._config || !this.isConnected) {
      return;
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
      this._pruneStaleSelection();
      if (!hadScene && this._hasGeometry()) {
        this._fitView();
      }
      this._updateHud();
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
      return;
    }
    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; }
      ha-card { overflow: hidden; position: relative; }
      .wrap { position: relative; width: 100%; touch-action: none; }
      canvas { display: block; width: 100%; height: 100%; cursor: grab; }
      canvas.dragging { cursor: grabbing; }
      .hud {
        position: absolute; top: 8px; left: 8px; display: flex; gap: 6px;
        flex-wrap: wrap; pointer-events: none; max-width: calc(100% - 60px);
      }
      .chip {
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        border-radius: 14px; padding: 3px 10px; font-size: 12px;
        opacity: .92; white-space: nowrap; overflow: hidden;
        text-overflow: ellipsis;
      }
      .chip.state { text-transform: capitalize; }
      .fit-btn {
        position: absolute; top: 8px; right: 8px; width: 34px; height: 34px;
        border-radius: 50%; border: 1px solid var(--divider-color, rgba(0,0,0,.12));
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        font-size: 16px; line-height: 1; cursor: pointer; opacity: .92;
      }
      .fit-btn:hover { opacity: 1; }
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
        max-width: 40vw;
      }
      .actions button {
        border: none; border-radius: 16px; padding: 6px 14px; font-size: 13px;
        cursor: pointer;
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
    wrap.appendChild(this._canvas);

    this._hud = document.createElement("div");
    this._hud.className = "hud";
    wrap.appendChild(this._hud);

    this._fitBtn = document.createElement("button");
    this._fitBtn.className = "fit-btn";
    this._fitBtn.textContent = "⛶";
    this._fitBtn.addEventListener("click", () => {
      this._fitView();
      this._requestDraw();
    });
    wrap.appendChild(this._fitBtn);

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
      this._syncCanvasSize();
      this._requestDraw();
    });
    this._resizeObserver.observe(wrap);
    this._syncCanvasSize();
    this._requestDraw();
  }

  _showMessage(text) {
    if (this._msg) {
      this._msg.textContent = text || "";
    }
  }

  _updateHud() {
    if (!this._hud) {
      return;
    }
    if (!this._config.show_hud) {
      this._hud.replaceChildren();
      return;
    }
    const chips = [];
    const state = this._hass && this._hass.states[this._config.entity];
    if (state) {
      const chip = document.createElement("span");
      chip.className = "chip state";
      chip.textContent = this._hass.formatEntityState
        ? this._hass.formatEntityState(state)
        : state.state;
      chips.push(chip);
    }
    if (this._scene && this._scene.map_name) {
      const chip = document.createElement("span");
      chip.className = "chip";
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

  _updateActionBar() {
    if (!this._actionBar) {
      return;
    }
    const count = this._pending.size;
    if (!count) {
      this._actionBar.classList.remove("visible");
      return;
    }
    const names = [];
    for (const region of this._scene?.regions || []) {
      for (const sub of region.sub_regions) {
        if (this._pending.has(sub.id)) {
          names.push(sub.name || `#${sub.id}`);
        }
      }
    }
    this._actionNames.textContent = names.join(", ");
    const unit = localize(this._hass, count === 1 ? "zone" : "zones");
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
          }
          this._view.tx += dx;
          this._view.ty += dy;
          this._requestDraw();
        }
      }
      this._pointers.set(ev.pointerId, cur);
      if (this._pointers.size === 2 && this._pinchStart) {
        this._dragged = true;
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
        const factor = Math.exp(-ev.deltaY * 0.0015);
        this._zoomAt(ev.offsetX, ev.offsetY, factor);
      },
      { passive: false }
    );
    canvas.addEventListener("dblclick", () => {
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

  _onTap(px, py) {
    if (!this._config.zone_selection || !this._scene || !this._view) {
      return;
    }
    const wx = (px - this._view.tx) / this._view.scale;
    const wy = (py - this._view.ty) / this._view.scale;
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
    const bw = Math.max(1, maxX - minX);
    const bh = Math.max(1, maxY - minY);
    const scale = Math.min(w / bw, h / bh) * 0.9;
    this._view = {
      scale,
      tx: (w - bw * scale) / 2 - minX * scale,
      ty: (h - bh * scale) / 2 - minY * scale,
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

  _colors() {
    const styles = getComputedStyle(this);
    const pick = (name, fallback) =>
      styles.getPropertyValue(name).trim() || fallback;
    const primaryText = pick("--primary-text-color", "#212121");
    const dark =
      primaryText.startsWith("#e") ||
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
      historyPath: dark ? "rgba(180,220,180,0.35)" : "rgba(90,140,90,0.35)",
      currentPath: dark ? "#7fd4ff" : "#0288d1",
      station: dark ? "#9ccc65" : "#558b2f",
      robot: dark ? "#ffd54f" : "#f57f17",
      grid: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)",
    };
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
    const scene = this._scene;
    ctx.save();
    ctx.translate(view.tx, view.ty);
    ctx.scale(view.scale, view.scale);
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

    // Region lawns
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

    // Zones (sub-regions) with holes
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

    fillStrokePolys(scene.pass_through_zones, colors.passThrough, null);
    fillStrokePolys(scene.required_zones, null, colors.accent, 1.5);
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
    for (const tunnel of scene.tunnels) {
      fillStrokePolys(tunnel.polygons, colors.passThrough, colors.accent, 1);
      strokeLines(tunnel.polylines, colors.accent, 1.5, [4, 4]);
    }
    fillStrokePolys(scene.draw_regions, null, colors.robot, 2);

    // Mowing paths
    if (this._config.show_history_path && scene.history_path.length > 1) {
      strokeLines([scene.history_path], colors.historyPath, 1.6);
    }
    if (this._config.show_current_path && scene.current_path.length > 1) {
      strokeLines([scene.current_path], colors.currentPath, 2.2);
    }

    // Zone labels once zones are reasonably large on screen
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const region of scene.regions) {
      for (const sub of region.sub_regions) {
        if (!sub.center) {
          continue;
        }
        const label = sub.name || (sub.id !== null ? `#${sub.id}` : null);
        if (!label) {
          continue;
        }
        const fontPx = 12 / view.scale;
        if (view.scale * 2000 < 46) {
          continue; // zone would be under ~46px per 2 m — too small to label
        }
        ctx.font = `600 ${fontPx}px sans-serif`;
        ctx.lineWidth = lw(3);
        ctx.strokeStyle = colors.bg;
        ctx.strokeText(label, sub.center[0], sub.center[1]);
        ctx.fillStyle = colors.text;
        ctx.fillText(label, sub.center[0], sub.center[1]);
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
    this._drawRobot(ctx, view, colors);
    ctx.restore();

    this._drawScaleBar(ctx, view, w, h, colors);
  }

  _drawGrid(ctx, view, w, h, colors) {
    // Metre grid in world space; pick a step that stays >= ~28 px apart.
    let step = 1000;
    if (!Number.isFinite(view.scale) || view.scale <= 0) {
      return;
    }
    while (step * view.scale < 28) {
      step *= 2;
    }
    const minX = (0 - view.tx) / view.scale;
    const maxX = (w - view.tx) / view.scale;
    const minY = (0 - view.ty) / view.scale;
    const maxY = (h - view.ty) / view.scale;
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

  _drawRobot(ctx, view, colors) {
    const robot = this._robot;
    if (!robot) {
      return;
    }
    let { x, y } = robot;
    // Ease between consecutive pose pushes so the marker glides.
    if (this._robotPrev) {
      const t = Math.min(
        1,
        (performance.now() - this._robotAnimStart) / 400
      );
      const s = t * (2 - t); // ease-out
      x = this._robotPrev.x + (robot.x - this._robotPrev.x) * s;
      y = this._robotPrev.y + (robot.y - this._robotPrev.y) * s;
      if (t < 1) {
        this._requestDraw();
      } else {
        this._robotPrev = null;
      }
    }
    ctx.save();
    ctx.translate(x, y);
    const size = Math.max(380, 16 / view.scale); // >= 38 cm, >= 16 px
    ctx.rotate((robot.yaw || 0) - Math.PI / 2);
    if (robot.source === "dock_fallback") {
      ctx.globalAlpha = 0.55;
    }
    ctx.beginPath();
    ctx.arc(0, 0, size / 2, 0, Math.PI * 2);
    ctx.fillStyle = colors.robot;
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
  }

  _drawScaleBar(ctx, view, w, h, colors) {
    const target = 90; // px
    let best = SCALE_BAR_STEPS[0];
    for (const step of SCALE_BAR_STEPS) {
      if (Math.abs(step * view.scale - target) < Math.abs(best * view.scale - target)) {
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
        name: "zone_selection",
        label: "Tap zones to mow",
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
      "Interactive TerraMow lawn map: live position, mowing path, tap-to-mow zones.",
    preview: false,
    documentationURL: "https://github.com/it-rec/TerraMowHA",
  });
}
