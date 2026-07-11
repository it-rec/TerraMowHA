# Contributing to TerraMowHA

Thanks for your interest in improving the TerraMow Home Assistant integration.
This guide covers the local setup, the quality gates every change must pass,
and the pull-request and release process.

## Project layout

```
custom_components/terramow/   # the integration (shipped to users)
tests/                        # pytest suite (100% line + branch coverage)
docs/                         # user & developer documentation
  ARCHITECTURE.md             # integration internals (start here to extend it)
  UPSTREAM_DELTA.md           # what this fork adds over TerraMow/TerraMowHA
  en/developers.md            # on-the-wire MQTT/HTTP protocol reference
blueprints/                   # importable automation blueprints
.github/workflows/            # validate.yml (CI) + release.yml
```

New to the codebase? Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the
integration internals and [`docs/en/developers.md`](docs/en/developers.md) for
the device protocol.

## Local setup

Python 3.13 is used in CI. Create a virtual environment and install the test
dependencies:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
```

## Quality gates

Every pull request must pass **all five CI checks**. Run them locally before
pushing:

### 1. Tests + coverage (must stay at 100%)

The coverage floor is enforced at **100% line and branch** via
`--cov-fail-under=100`. Any new line of shipped code needs a test that exercises
it.

```bash
pytest tests/ \
  --cov=custom_components/terramow \
  --cov-report=term-missing \
  --cov-fail-under=100
```

If a branch is genuinely unreachable defensive code, mark it with
`# pragma: no cover` and a short reason (there is exactly one today: the dp-id
`ValueError` handler in `hub.py`, guarded by a `\d+` regex). Do not use pragmas
to skip testable code.

Tests follow a consistent style — build a real `TerraMowHub` with a `MagicMock`
hass, feed device data points through the `on_*` handlers
(`asyncio.run(hub.on_mission_status(json.dumps({...})))`; note the mission
payload key is `"state"`, not `"mission_state"`), and read entity properties
directly. Entities have `entity_id = None` in tests, so the thread-safe state
helpers safely no-op.

### 2. Type checking (`mypy --strict`)

The whole shipped package is type-checked in strict mode
(`[tool.mypy]` in `pyproject.toml`).

```bash
mypy
```

### 3. Lint (ruff)

```bash
ruff check custom_components/terramow
```

### 4. Hassfest & 5. HACS

These validate the manifest, `strings.json`, translations, `quality_scale.yaml`
and HACS metadata. They run in CI; `python -m script.hassfest` requires a
Home Assistant checkout, so relying on CI for these is fine.

## Translations (all 33 languages)

`strings.json` is the source of truth. **Any new user-facing string must be
added to every file in `translations/`** — the integration ships full
translations and an incomplete language is a regression.

Placeholders (e.g. `{hours}`, `{entity_id}`) must be preserved verbatim in every
language. `zh-CN.json` is a symlink to `zh-Hans.json`. The translation files
round-trip through `json.dumps(..., ensure_ascii=False, indent=2)`, which makes
scripted edits safe.

## Quality scale

The integration targets **Platinum** on the Home Assistant Integration Quality
Scale (`custom_components/terramow/quality_scale.yaml`, `manifest.json`
`quality_scale`). New entities/platforms must keep the relevant rules satisfied
(entity translations, icon translations, disabled-by-default where appropriate,
strict typing, etc.).

## Pull-request process

1. Branch from `main`; keep each PR focused on one logical change.
2. Ensure all five checks are green locally, then open the PR.
3. PRs are squash-merged once CI is green.
4. Do **not** add a `CHANGELOG.md`; release notes are generated automatically.

## Release process

1. Bump `version` in `custom_components/terramow/manifest.json` in its own PR and
   merge it.
2. Run the **Release** workflow (`release.yml`) via *workflow dispatch* with the
   `tag` input set to `vX.Y.Z`. It builds `terramow.zip` and publishes the
   GitHub release with auto-generated notes.

## Where things live (quick reference)

| Task | File(s) |
|---|---|
| Add a data point / device command | `hub.py` (`on_*` handler, `register_all_callbacks`) |
| Add an entity | the matching platform module + `strings.json`/`translations/*` + `icons.json` |
| Add a platform | new module + register it in `__init__.py` `PLATFORMS` |
| Add a repair issue | `issues.py` + hub hook + `strings.json`/translations |
| Config/discovery changes | `config_flow.py` |
| Tune the CI gate | `.github/workflows/validate.yml` |

## Map card resource registration

The interactive map card's Lovelace resource type is version-sensitive on
the Home Assistant side (classic `js` is deprecated and broken on
HA 2026.7+; see issue #140). When touching `map_card.py` resource
registration or the card's loading behaviour, verify on the **latest**
HA Core release that the card renders on a normal page load with only the
auto-registered resource — no manual import, at most one hard refresh.
