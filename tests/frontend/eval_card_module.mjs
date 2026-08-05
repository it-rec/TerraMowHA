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

console.log("card module OK:", [...defined.keys()].join(", "));
