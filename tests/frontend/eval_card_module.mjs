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

console.log("card module OK:", [...defined.keys()].join(", "));
