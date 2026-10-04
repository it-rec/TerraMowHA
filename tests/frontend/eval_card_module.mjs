// Regression guard for the map card's frontend module.
//
// Home Assistant loads the card as an ES module (strict mode, module goal),
// so a strict-only violation or module-goal parse error would silently leave
// `customElements.get("terramow-map-card")` undefined in the browser. This
// script evaluates the exact shipped file under Node's module goal with
// minimal DOM stubs and fails unless top-level evaluation reaches BOTH
// customElements.define calls.
//
// Run:  node tests/frontend/eval_card_module.mjs

import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { copyFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";

globalThis.HTMLElement = class HTMLElement {
  attachShadow() {
    return { replaceChildren() {} };
  }
  addEventListener() {}
  dispatchEvent() {}
  appendChild() {}
};
const defined = new Map();
globalThis.customElements = {
  get: (name) => defined.get(name),
  define: (name, cls) => defined.set(name, cls),
};
globalThis.window = globalThis;
globalThis.document = {
  createElement: () => ({
    addEventListener() {},
    appendChild() {},
    append() {},
    classList: { add() {}, remove() {} },
    style: {},
  }),
};
globalThis.ResizeObserver = class {
  observe() {}
};
globalThis.requestAnimationFrame = () => 0;
globalThis.getComputedStyle = () => ({ getPropertyValue: () => "" });
globalThis.CustomEvent = class {};
globalThis.performance = { now: () => 0 };

const here = dirname(fileURLToPath(import.meta.url));
const source = join(
  here,
  "..",
  "..",
  "custom_components",
  "terramow",
  "frontend",
  "terramow-map-card.js"
);
// Copy to .mjs so Node applies the module goal regardless of extension rules.
const target = join(mkdtempSync(join(tmpdir(), "terramow-card-")), "card.mjs");
copyFileSync(source, target);

await import(pathToFileURL(target).href);

const expected = ["terramow-map-card", "terramow-map-card-editor"];
const missing = expected.filter((name) => !defined.has(name));
if (missing.length) {
  console.error("Card module evaluated but did not define:", missing);
  process.exit(1);
}
if (!Array.isArray(globalThis.customCards) || !globalThis.customCards.length) {
  console.error("Card module did not register in window.customCards");
  process.exit(1);
}
// Beyond the module-goal smoke test, exercise the pure replay helpers on the
// prototype: clipping the session track is what decides whether scrubbing
// shows the right amount of mowing, and it is plain arithmetic worth pinning.
const CardClass = defined.get("terramow-map-card");
const clip = CardClass.prototype._clipRuns;
const runs = [
  [1, 2, 3],
  [4, 5],
  [6, 7, 8, 9],
];
const cases = [
  [0, []],
  [2, [[1, 2]]],
  [3, [[1, 2, 3]]],
  [4, [[1, 2, 3], [4]]],
  [5, [[1, 2, 3], [4, 5]]],
  [7, [[1, 2, 3], [4, 5], [6, 7]]],
  [9, [[1, 2, 3], [4, 5], [6, 7, 8, 9]]],
  [99, [[1, 2, 3], [4, 5], [6, 7, 8, 9]]],
];
for (const [upto, want] of cases) {
  const got = clip.call({}, runs, upto);
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    console.error(
      `_clipRuns(${upto}) = ${JSON.stringify(got)}, expected ${JSON.stringify(want)}`
    );
    process.exit(1);
  }
}

// Issue #327: the card is sometimes drawn at the wrong zoom until the user
// presses fit. A scene can arrive before the browser has settled the card's
// size — a `rows: auto` grid row reports a provisional height first — and the
// fit computed against that size is wrong but non-zero, so nothing recomputed
// it. These pin the re-fit rule the ResizeObserver relies on.
const fail = (msg) => {
  console.error(msg);
  process.exit(1);
};
const makeCard = (w, h) => ({
  _scene: {
    bounds: [0, 0, 1000, 1000],
    content_bounds: [0, 0, 1000, 1000],
    regions: [{}],
    map_extent: [],
  },
  _root: { clientWidth: w, clientHeight: h },
  _config: { fit_padding: 1 },
  _rot: 0,
  _view: null,
  _viewIsAuto: true,
  _fitView: CardClass.prototype._fitView,
  _hasGeometry: CardClass.prototype._hasGeometry,
  _refitOnResize: CardClass.prototype._refitOnResize,
});

// The reported failure itself, driven through the real scene handler: the
// first scene carries nothing but the scanned extent, so the backend's
// content_bounds falls back to that full box. Fitting to it leaves the lawn
// small and off-centre; the scene that finally carries the lawn has to
// re-frame it, or the map stays wrong until the user presses fit.
const extentOnly = {
  bounds: [0, 0, 2000, 2000],
  content_bounds: [0, 0, 2000, 2000],
  regions: [],
  map_extent: [
    [0, 0],
    [2000, 0],
    [2000, 2000],
    [0, 2000],
  ],
};
const withLawn = {
  ...extentOnly,
  content_bounds: [0, 0, 1000, 1000],
  regions: [{}],
};
const feedCard = () => ({
  _config: { entity: "lawn_mower.test", fit_padding: 1 },
  _root: { clientWidth: 600, clientHeight: 600 },
  _rot: 0,
  _view: null,
  _viewIsAuto: true,
  _fitBox: null,
  _scene: null,
  _sceneRev: 0,
  _pathRev: 0,
  _legend: null,
  _fitView: CardClass.prototype._fitView,
  _hasGeometry: CardClass.prototype._hasGeometry,
  _fitBasisChanged: CardClass.prototype._fitBasisChanged,
  _onFeedMessage: CardClass.prototype._onFeedMessage,
  _pruneStaleSelection() {},
  _updateHud() {},
  _maybeAutoOpenLegend() {},
  _requestDraw() {},
});

const feed = feedCard();
feed._onFeedMessage({ type: "scene", scene: extentOnly });
// 2000 world units across 600 px: the lawn is framed inside the scanned box.
if (Math.abs(feed._view.scale - 0.3) > 1e-9) {
  fail(`#327: first fit scale ${feed._view.scale}, expected 0.3`);
}
feed._onFeedMessage({ type: "scene", scene: withLawn });
if (Math.abs(feed._view.scale - 0.6) > 1e-9) {
  fail(
    `#327: the lawn scene did not re-frame the map (scale ${feed._view.scale}, expected 0.6)`
  );
}

// Same sequence, but the user framed the map themselves in between: their
// view must survive the incoming scene untouched.
const held = feedCard();
held._onFeedMessage({ type: "scene", scene: extentOnly });
held._view.tx += 42;
held._viewIsAuto = false;
const heldView = { ...held._view };
held._onFeedMessage({ type: "scene", scene: withLawn });
if (JSON.stringify(held._view) !== JSON.stringify(heldView)) {
  fail("#327: a scene overrode the view the user had framed");
}

// A scene that only moves the mower leaves the same geometry, so it must not
// re-frame. Comparing the view would prove nothing — re-fitting the same
// geometry at the same size yields the same numbers — so count the fits.
const steady = feedCard();
let fits = 0;
steady._fitView = function (...args) {
  fits += 1;
  return CardClass.prototype._fitView.apply(this, args);
};
steady._onFeedMessage({ type: "scene", scene: withLawn });
steady._onFeedMessage({ type: "scene", scene: { ...withLawn } });
if (fits !== 1) {
  fail(`#327: unchanged geometry triggered ${fits} fits, expected 1`);
}

// A fit against a provisional height, then the real one: the view must follow.
const card = makeCard(600, 100);
card._fitView();
const provisional = card._view.scale;
card._root.clientHeight = 600;
if (card._refitOnResize() !== true) {
  fail("#327: resize did not re-fit an automatic view");
}
if (!(card._view.scale > provisional)) {
  fail(
    `#327: view kept the provisional fit (${provisional} -> ${card._view.scale})`
  );
}
// 1000 world units across 600 px at fit_padding 1 — the frame now fits exactly.
if (Math.abs(card._view.scale - 0.6) > 1e-9) {
  fail(`#327: re-fit scale ${card._view.scale}, expected 0.6`);
}

// A view the user moved is theirs: a resize must leave it exactly alone.
const moved = makeCard(600, 600);
moved._fitView();
moved._view.tx += 137;
moved._viewIsAuto = false;
const before = { ...moved._view };
moved._root.clientWidth = 300;
if (moved._refitOnResize() !== false) {
  fail("#327: resize overrode a view the user had panned");
}
if (JSON.stringify(moved._view) !== JSON.stringify(before)) {
  fail("#327: user view mutated on resize");
}

// Pressing fit hands control back, so later resizes track again.
moved._fitView();
if (moved._viewIsAuto !== true) {
  fail("#327: fit did not restore the automatic view");
}

// Without geometry there is nothing to frame — must not throw or fit.
const empty = makeCard(600, 600);
empty._scene = null;
if (empty._refitOnResize() !== false || empty._view !== null) {
  fail("#327: re-fit ran without geometry");
}

// Issue #304: the maintenance panel's row builder decides what the wrench
// shows and when it warns. It is pure over (hass.states, feed payload), so it
// is worth pinning: the entity ids always come from the feed — the reporter's
// install prefixes them with the area name, ours does not — a counter at zero
// reads as due, the last tenth of a cycle as soon, and anything without a
// state drops out instead of rendering an empty row.
const maintCard = (states, maintenance) => ({
  _hass: { language: "en", states },
  _maintenance: maintenance,
  _maintRows: CardClass.prototype._maintRows,
  _maintSignature: CardClass.prototype._maintSignature,
});
const counterState = (minutes, cycle) => ({
  state: `${minutes}`,
  attributes: { recommended_cycle: cycle },
});
// Entity ids exactly as the reporter's install names them.
const maintIds = {
  base_station_time: "sensor.garten_terramow_restzeit_basisstation",
  base_station_reset: "button.garten_terramow_basisstation_zahler_zurucksetzen",
  blade_time: "sensor.garten_terramow_restzeit_klingen",
  blade_reset: "button.garten_terramow_klingen_zahler_zurucksetzen",
};
const pressable = { state: "unknown", attributes: {} };
const maintStates = {
  [maintIds.base_station_time]: counterState(21600, 43200), // half a cycle
  [maintIds.base_station_reset]: pressable,
  [maintIds.blade_time]: counterState(0, 14400), // used up
  [maintIds.blade_reset]: pressable,
};
const maintRows = maintCard(maintStates, maintIds)._maintRows();
if (maintRows.length !== 2) {
  fail(`#304: expected two maintenance rows, got ${maintRows.length}`);
}
if (maintRows[0].due || maintRows[0].soon) {
  fail("#304: a half-used base-station counter warned");
}
if (maintRows[0].value !== "15 d") {
  fail(`#304: base-station value ${maintRows[0].value}, expected "15 d"`);
}
if (!maintRows[1].due || maintRows[1].value !== "due now") {
  fail("#304: a blade counter at zero did not read as due");
}
if (maintRows[1].resetId !== maintIds.blade_reset) {
  fail("#304: the row lost the reset button entity from the feed");
}
// The last tenth of the cycle warns, without claiming the blade is finished.
const soonRows = maintCard(
  { ...maintStates, [maintIds.blade_time]: counterState(1000, 14400) },
  maintIds
)._maintRows();
if (soonRows[1].due || !soonRows[1].soon) {
  fail("#304: a nearly used-up blade counter did not warn");
}
if (soonRows[1].value !== "16 h 40 min") {
  fail(`#304: blade value ${soonRows[1].value}, expected "16 h 40 min"`);
}
// A reset button that has no state (disabled) leaves the counter readable.
const noResetRows = maintCard(
  { [maintIds.blade_time]: counterState(500, 14400) },
  maintIds
)._maintRows();
if (noResetRows.length !== 1 || noResetRows[0].resetId !== null) {
  fail("#304: a disabled reset button was offered anyway");
}
// Nothing to show: no rows, so the card hides the wrench entirely.
if (maintCard({}, maintIds)._maintRows().length) {
  fail("#304: rows were built for counters that have no state");
}
if (maintCard(maintStates, null)._maintRows().length) {
  fail("#304: rows were built before the feed named the entities");
}
if (maintCard(maintStates, maintIds)._maintSignature() !== "21600|0") {
  fail("#304: the counter signature does not track both counters");
}
if (maintCard(maintStates, null)._maintSignature() !== "") {
  fail("#304: a signature was built without maintenance entities");
}

// Issue #337: the card ships its own translation table, separate from the
// integration's translations/*.json, and nothing ever checked it. localize()
// falls back silently — `table[key] || STRINGS.en[key] || key` — so a language
// that never got a new key still looks translated while showing English, which
// is how 28 of 30 languages ended up missing 68 of their 81 labels. English is
// the source of truth: every table must carry exactly its key set. Missing
// keys are the drift itself; unknown keys are a typo that can never be shown,
// because localize() only ever asks for keys that exist in English.
const STRINGS = CardClass.STRINGS;
if (!STRINGS || !STRINGS.en) {
  fail("#337: the card no longer exposes its string table");
}
const enKeys = Object.keys(STRINGS.en);
if (enKeys.length < 50) {
  fail(`#337: English has only ${enKeys.length} keys — table looks truncated`);
}
for (const [lang, table] of Object.entries(STRINGS)) {
  const missing = enKeys.filter((key) => !(key in table));
  const unknown = Object.keys(table).filter((key) => !enKeys.includes(key));
  const empty = enKeys.filter(
    (key) => key in table && (typeof table[key] !== "string" || !table[key].trim())
  );
  if (missing.length || unknown.length || empty.length) {
    fail(
      [
        `#337: ${lang} does not match the English key set`,
        missing.length ? `missing: ${missing.join(", ")}` : "",
        unknown.length ? `unknown: ${unknown.join(", ")}` : "",
        empty.length ? `empty: ${empty.join(", ")}` : "",
      ]
        .filter(Boolean)
        .join(" — ")
    );
  }
}

// Issue #359: the ETA chip switches between time left and the finish time,
// and a finish that would land after the mower's own sunset reads "continues
// tomorrow" — the firmware docks for the night and resumes the next day, so
// an evening clock time would be a promise it does not keep. Pinned in the
// server's zone so the result does not depend on the machine running CI.
const etaCard = (locale = {}, language = "en") => ({
  _hass: {
    language,
    locale: { time_format: "24", time_zone: "server", ...locale },
    config: { time_zone: "Europe/Berlin" },
  },
  _etaText: CardClass.prototype._etaText,
});
const at = (hhmm, day = "04") => Date.parse(`2026-10-${day}T${hhmm}:00+02:00`);
const sunset = "2026-10-04T19:00:00+02:00";
const H = 3600;

let eta = etaCard()._etaText(2 * H, at("14:00"), null, "remaining");
if (eta.text !== "≈ 2 h left" || eta.icon !== "timerSand") {
  fail(`#359: remaining form read ${JSON.stringify(eta)}`);
}
if (eta.title !== "≈ 2 h left · done ≈ 16:00") {
  fail(`#359: the tooltip must carry both forms, got "${eta.title}"`);
}
eta = etaCard()._etaText(2 * H, at("14:00"), sunset, "finish");
if (eta.text !== "done ≈ 16:00" || eta.icon !== "clock" || eta.pastSunset) {
  fail(`#359: finish before sunset read ${JSON.stringify(eta)}`);
}
// Past the device's sunset: no evening time, in either form's icon.
eta = etaCard()._etaText(6 * H, at("14:00"), sunset, "finish");
if (eta.text !== "continues tomorrow" || eta.icon !== "moon" || !eta.pastSunset) {
  fail(`#359: a finish after sunset read ${JSON.stringify(eta)}`);
}
if (eta.title !== "≈ 6 h left · runs past sunset (19:00) · continues tomorrow") {
  fail(`#359: the after-sunset tooltip read "${eta.title}"`);
}
eta = etaCard()._etaText(6 * H, at("14:00"), sunset, "remaining");
if (eta.text !== "≈ 6 h left" || eta.icon !== "moon") {
  fail(`#359: time left past sunset read ${JSON.stringify(eta)}`);
}
// Still mowing after sunset: the dark is not stopping it, the clock stands.
eta = etaCard()._etaText(1 * H, at("19:30"), sunset, "finish");
if (eta.text !== "done ≈ 20:30" || eta.pastSunset) {
  fail(`#359: mowing after sunset read ${JSON.stringify(eta)}`);
}
// A finish past midnight says so instead of a bare, ambiguous early time.
eta = etaCard()._etaText(2 * H, at("23:00"), null, "finish");
if (eta.text !== "done tomorrow ≈ 01:00") {
  fail(`#359: a finish after midnight read "${eta.text}"`);
}
// Localized label, and the user's 12-hour profile setting.
eta = etaCard({}, "de")._etaText(2 * H, at("14:00"), null, "finish");
if (eta.text !== "fertig ≈ 16:00") {
  fail(`#359: German finish form read "${eta.text}"`);
}
eta = etaCard({ time_format: "12" })._etaText(2 * H, at("14:00"), null, "finish");
if (!/^done ≈ 4:00\sPM$/u.test(eta.text)) {
  fail(`#359: 12-hour finish form read "${eta.text}"`);
}
// An unusable sunset report is ignored rather than guessed at.
eta = etaCard()._etaText(6 * H, at("14:00"), "not a date", "finish");
if (eta.pastSunset || eta.text !== "done ≈ 20:00") {
  fail(`#359: a malformed sunset changed the chip: ${JSON.stringify(eta)}`);
}

// The chosen form: the configured default until a tap, then the tap sticks
// (per entity, across reloads) — and blocked storage still toggles.
const etaModeCard = (config) => ({
  _config: { entity: "lawn_mower.test", ...config },
  _etaMode: null,
  _etaDisplay: CardClass.prototype._etaDisplay,
  _toggleEtaDisplay: CardClass.prototype._toggleEtaDisplay,
  _updateHud() {},
});
const blocked = etaModeCard({});
if (blocked._etaDisplay() !== "remaining") {
  fail("#359: the chip did not default to time left");
}
blocked._toggleEtaDisplay();
if (blocked._etaDisplay() !== "finish") {
  fail("#359: a tap did not switch the chip with storage blocked");
}
if (etaModeCard({ eta_display: "finish" })._etaDisplay() !== "finish") {
  fail("#359: eta_display: finish was not honored");
}
if (etaModeCard({ eta_display: "bogus" })._etaDisplay() !== "remaining") {
  fail("#359: an unknown eta_display did not fall back to time left");
}
const stored = new Map();
globalThis.localStorage = {
  getItem: (key) => (stored.has(key) ? stored.get(key) : null),
  setItem: (key, value) => stored.set(key, String(value)),
};
const tapped = etaModeCard({ eta_display: "finish" });
tapped._toggleEtaDisplay();
if (stored.get("terramow-map-card:eta:lawn_mower.test") !== "remaining") {
  fail("#359: the tapped form was not remembered");
}
if (etaModeCard({ eta_display: "finish" })._etaDisplay() !== "remaining") {
  fail("#359: a remembered tap did not override the configured default");
}
delete globalThis.localStorage;

console.log("card module OK:", [...defined.keys()].join(", "));
console.log(
  `card i18n OK: ${Object.keys(STRINGS).length} languages x ${enKeys.length} keys`
);
