# AI 3D Print Designer

Personal, internal-use web app for generating **functional, print-ready** 3D
designs from text and photos — including fixing broken parts (photograph next to a
credit card for scale) and creating multi-colour signs for the Anycubic ACE Pro.

Standalone app · cloud AI APIs · CPU-only friendly · exports **standard 3MF** for
**Anycubic Slicer Next**.

**See [PLAN.md](./PLAN.md) for the full project plan** — architecture, the four
core workflows, phased roadmap, tech stack, costs, risks, and research sources.

---

## Status

| Phase | What | State |
|---|---|---|
| **0** | FastAPI + SQLite + three.js preview; parametric **demo** model → build → download STL/STEP | ✅ Done |
| **1** | Describe a part in words → Claude writes CadQuery → same build/preview/download pipeline, with live parameter sliders, a manifold check, and a self-repair retry | ✅ Done |
| **2** | Print-readiness assistant: overhang/support detection, min-wall estimate, feature-size check, auto-repair, orientation suggestion, editable printer profile + FDM tolerance/fit reference (also fed into the AI prompt) | ✅ Done |
| **3** | Photo → fix a broken part: upload a photo, pick a **reference object** (library of cards/coins/paper/ruler + custom), click to calibrate scale (mm/px) and measure features, then Claude vision rebuilds it parametrically at the measured sizes → into the same build/preview/readiness pipeline | ✅ Done |
| **4** | Multi-colour signs: text + coloured plate / text / border builder → **standard multi-body 3MF** (each colour a separate object with a base material) that Anycubic Slicer Next reads and maps to ACE Pro slots. Coloured 3D preview. No API key needed. | ✅ Done |
| **4.5** | **Multicolour everywhere**: the generation contract now returns named coloured **bodies**; the AI splits parts into logical colours you can recolour; **every design exports a multi-body 3MF** (+ STL/STEP); one colour-aware multi-body 3D preview shared across designs & signs; **AI sign generation** ("describe a sign") added alongside the form builder | ✅ Done |

---

## Quickstart

```bash
# 1. Install (CadQuery pulls a large native wheel — first install is slow)
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
#   edit .env and set ANTHROPIC_API_KEY to enable AI generation.
#   (The demo model works with no key.)

# 3. Run
python run.py            # -> http://127.0.0.1:8000
```

Or with Docker:

```bash
cp .env.example .env     # set your key
docker compose up --build
```

### Using it

- **Demo (no key):** home page → *Open demo model* → drag the sliders → *Rebuild* →
  download STL/STEP. Proves the whole pipeline.
- **AI (needs key):** type a part description, e.g.
  *"A 60 mm cable clip for a 12 mm desk edge, 3 mm cable channel, M3 screw hole"* →
  *Generate*. Claude writes parametric CadQuery, the server builds and **verifies it
  before you see it** (one automatic repair retry on failure), then you tweak
  parameters live and export.

---

## How it works

```
Browser (HTMX + Bootstrap + three.js STL viewer)
   │
FastAPI
   ├─ /generate   prompt ─▶ Claude ─▶ {name, parameters[], CadQuery code}
   │                                   └─ validated + build-tested before saving
   ├─ /design/{id}          slider values ─▶ rebuild ─▶ STL + STEP + mesh report
   └─ /design/{id}/model.stl|step   downloads
```

- **Multicolour by default.** The AI splits every model into named coloured **bodies**
  (`build(params) -> {"body": ..., "label": ...}`); each is printed in its own filament
  and they assemble into ONE print. You recolour bodies in the UI, and **every design
  exports a standard multi-body 3MF** (a single-colour part is just one body) alongside
  STL/STEP. Signs can be created by the AI (describe them) or the form builder.
- **Parametric, not mesh.** The AI writes *code*, so parts are dimensionally exact,
  editable, and watertight — the right tool for functional prints. (Organic mesh
  generation comes later; see PLAN.md.)
- **Designs are re-editable.** SQLite stores the CadQuery source + parameter set, not
  just a mesh, so you can reopen a part and change one number.
- **Every export is inspected** and scored for printability (`app/print_check/`):
  watertight (+ auto-repair), overhangs that need support, an estimated minimum
  wall thickness (inward ray casting), smallest feature vs. nozzle, and a
  suggested orientation. The printer profile (nozzle Ø, layer height, overhang
  angle, default clearance) is editable in the UI and is also injected into the
  AI prompt so generated parts respect your nozzle and fit clearances.

## Project layout

```
app/
  main.py              # FastAPI routes (pages, rebuild, downloads)
  config.py            # settings from .env
  database.py          # SQLite: designs + assets
  cad/
    executor.py        # run build(params) -> STL/STEP + mesh report
    validate.py        # static guard for model-written code
    primitives.py      # Phase 0 demo model
  ai/
    generator.py       # prompt/photo -> Claude -> parametric design (+ self-repair)
    prompts.py         # system prompt / JSON contract / reconstruction note
  measure/
    references.py      # scale-reference library (cards, coins, paper, ruler, custom)
    scale.py           # mm-per-pixel calibration + measurement math
  print_check/         # overhang, wall, feature, repair, orientation, fit presets
  signs/
    builder.py         # sign geometry -> separate coloured bodies (base/text/border)
    threemf.py         # standard multi-body / multi-material 3MF writer
    service.py         # writes 3MF + per-body STLs + preview manifest
  services/build_service.py
  templates/  static/  # HTMX pages + three.js viewer
tests/                 # engine + app smoke tests (no API key needed)
```

## Safety note

`/generate` executes Python that the model wrote. `app/cad/validate.py` blocks the
obvious footguns (imports outside `cadquery`/`math`/`numpy`, `os`/`sys`/`subprocess`,
file access, dunder escapes) and the executor runs it with stripped builtins and a
restricted importer. This is **not** a full sandbox — it's sized for single-user,
local, internal use. If you ever expose it more widely, move execution into a real
sandbox (subprocess + seccomp/nsjail or a container).

## Tests

```bash
pip install pytest
pytest -q        # engine + app smoke tests, no API key required
```

> Internal use only. Not for resale.
