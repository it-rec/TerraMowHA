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

console.log("card module OK:", [...defined.keys()].join(", "));
