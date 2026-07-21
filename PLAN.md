# AI-Driven 3D Print Design Tool — Project Plan

> A personal, internal-use web app for generating **functional, print-ready** 3D
> designs from text and photos. Fix broken parts by photographing them next to a
> credit card for scale, generate multi-colour signs, and export straight into
> **Anycubic Slicer Next** (+ ACE Pro) for printing.

**Status:** Planning · **Owner:** internal single user · **Not for resale**

---

## 1. Decisions locked in

| Decision | Choice | Why it matters |
|---|---|---|
| Printer / slicer | **Anycubic Slicer Next** (OrcaSlicer-based) + **ACE Pro** multi-colour | Export target = **standard 3MF** (multi-body / standard colour block). Slicer Next does *not* read Bambu's proprietary 3MF colour data, so we must emit Orca-standard colour, not Bambu paint. |
| AI hosting | **Cloud APIs** | Fastest to build, best quality, runs on any machine. |
| Compute | **CPU / laptop only** | No local GPU. All heavy generation (vision, text-to-CAD, image→3D mesh) is offloaded to cloud services. Local box only runs Python glue + light OpenCV. |
| Codebase | **Standalone new app** | Kept separate from the unrelated Archive-Tools HR app. |
| Audience | **You, internal only** | No auth/multi-tenant/billing complexity. Optimise for your workflow, not scale. |

---

## 2. The core insight that shapes everything

There are **two fundamentally different kinds of 3D generation**, and mixing them
up is the #1 reason AI print tools disappoint:

1. **Mesh generation** (Meshy, Tripo, Rodin, Hyper3D) — turns a photo/prompt into
   an organic textured mesh. Great for *decorative / figurine / "looks like X"*
   objects. **Bad** for functional parts: not dimensionally accurate, often
   non-manifold, no clean flat faces, holes, or threads. You cannot trust a
   measured 40.0 mm bolt-hole to come out at 40.0 mm.

2. **Parametric / code CAD** (LLM → CadQuery or OpenSCAD → STEP/STL) — the AI
   writes *code* that builds the geometry from real dimensions. Editable,
   measurable, watertight, and functional. This is what you want for a **bracket,
   clip, gear, adapter, or a broken-part replacement**.

**→ This tool leads with the parametric engine for functional work, and uses the
mesh engine only for organic/decorative jobs.** That single decision is what makes
it actually useful for "fix my broken part" instead of a toy.

---

## 3. The four workflows you asked for

### Workflow A — Functional design from a text prompt
> "A 60 mm cable clip for a 12 mm desk edge, 3 mm cable channel, screw hole for M3."

1. You describe the part (+ optional target dimensions, material, tolerances).
2. LLM generates **CadQuery** (Python) or **OpenSCAD** code with named parameters.
3. Server executes the code headlessly → renders a preview (PNG/GLB) + STEP + STL.
4. You see **parameter sliders** (length, wall thickness, hole Ø…) and tweak live.
5. Manifold check + auto-repair → export STL/3MF.

Editable code + sliders = you can nudge a dimension without regenerating from
scratch. This is the killer feature over pure mesh tools.

### Workflow B — Fix a broken part from photos (with scale reference)
> Photograph the broken part next to a **credit card** (ISO/IEC 7810 ID-1 =
> **85.60 × 53.98 mm**, the reference of record).

1. Upload 1–3 photos (ideally straight-on + a side view).
2. **Scale calibration:** detect the credit card rectangle (OpenCV contour /
   segmentation), compute the mm-per-pixel ratio from its known size.
3. **Measurement:** you click key features (or the vision model proposes them);
   the app returns real-world dimensions with an error estimate (<1–4% typical
   for a square-on, high-res shot).
4. **Reconstruction path — you choose:**
   - **Parametric rebuild (preferred for functional parts):** vision model +
     measurements → LLM writes parametric CAD that *matches the measured dims*.
     Clean, printable, and you can correct the broken/missing region.
   - **Mesh capture (for organic shapes):** send photos to a cloud image→3D
     service, then rescale the mesh using the card calibration, remesh/repair.
5. Repair the broken region (fill, mirror from the intact side, re-thread a hole),
   re-verify dimensions, export.

### Workflow C — Multi-colour signs
> Text signs and layered logos for the ACE Pro.

1. Enter text (font, size, board shape, border) **or** upload a logo/image.
2. For images: **AI colour separation** — quantise to N filament colours, vectorise
   each colour region.
3. Build geometry as a **base plate + raised/inset coloured layers**, one 3MF
   object (body) per colour so each maps to an ACE Pro slot.
4. Export **standard multi-body 3MF** → opens in Anycubic Slicer Next with colours
   already separated (assign each body to a filament slot).
5. Optional: preview the colour layout and per-colour height before export.

> Format note: emit *standard* 3MF colour, not Bambu-proprietary paint — Slicer
> Next reads the former, not the latter.

### Workflow D — Print-readiness assistant (the quiet value-add)
Before every export, run a checklist and surface fixes:
- Watertight / manifold check + auto-repair.
- Min wall thickness & small-feature warnings vs. nozzle Ø.
- Overhang / support hint.
- **Tolerance & fit helper** for mating parts (clearance/interference presets for
  FDM shrink — e.g. 0.2 mm clearance for a slip fit) so assemblies actually fit.
- Suggested orientation and a note on where colour changes land (for signs).

---

## 4. Architecture (cloud-first, CPU-only)

```
Browser (HTMX + Bootstrap + three.js preview)
        │
        ▼
FastAPI app  ──────────────────────────────────────────────┐
  • /design      text → parametric CAD                       │
  • /fix         photos → measure → rebuild                  │  Local, CPU-only:
  • /sign        text/image → multi-colour 3MF               │  Python glue,
  • /measure     card calibration + feature dims             │  OpenCV, CadQuery/
  • /export      manifold check, repair, STL/3MF             │  OpenSCAD exec,
  • jobs (async, SQLite-backed queue)                        │  trimesh repair
        │                                                    │
        ├── LLM (Claude API) ── text/vision → CAD code, feature ID
        ├── Image→3D service (Meshy / Tripo / Rodin API) ── organic meshes
        └── (optional) hosted text-to-CAD (Zoo/AdamCAD API) as a second opinion
```

**Why this shape:** identical stack to tools you already run (FastAPI + HTMX +
SQLite), everything heavy is an outbound HTTPS call, and the laptop only does
lightweight CPU work (executing CAD scripts, OpenCV contour math, mesh repair).

### Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | FastAPI + Uvicorn | Async, matches your existing tooling |
| Frontend | HTMX + Bootstrap 5 + **three.js** | Server-rendered + a real 3D preview canvas |
| Parametric CAD | **CadQuery** (primary) and/or **OpenSCAD** (subprocess) | Code → STEP + STL; CadQuery gives STEP (true B-rep) |
| Mesh handling | **trimesh** + **manifold3d** | Repair, boolean, watertight check, rescale |
| Computer vision | **OpenCV** | Card detection, mm/px scale, feature measurement |
| Colour separation | OpenCV / Pillow quantise + vectorise | Sign colour regions |
| 3MF export | **lib3mf** or trimesh 3MF writer | Standard multi-body 3MF for Slicer Next |
| LLM | **Claude API** (text + vision) | CAD-code gen, feature identification, measurement assist |
| Image→3D | Meshy / Tripo / Rodin API | Organic capture path only |
| DB / jobs | SQLite + a simple async job table | Persist designs, params, and generated files |
| Packaging | Docker + docker-compose | One-command local run |

---

## 5. Data model (first cut)

- **projects** — a design/job you're working on.
- **assets** — uploaded photos, generated STL/STEP/3MF, preview PNG/GLB.
- **designs** — the CAD source (CadQuery/OpenSCAD text) + parameter set (JSON) so
  a design is *re-generatable and editable*, not just a binary blob.
- **measurements** — card-calibrated feature dims + error estimate per photo set.
- **jobs** — async generation/export tasks with status + logs.

Storing the **parametric source + params** (not only the mesh) is what lets you
re-open a part months later and change one number.

---

## 6. Phased roadmap

**Phase 0 — Scaffold (½–1 day)**
FastAPI skeleton, SQLite, Docker, `.env` for API keys, three.js preview page,
file storage, health check. One "hello STL" round-trip (CadQuery box → preview →
download).

**Phase 1 — Functional text→CAD (Workflow A)** ← *highest value, build first*
Claude → CadQuery code → execute → preview → STEP/STL. Parameter extraction +
sliders. Manifold check. This alone is immediately useful.

**Phase 2 — Print-readiness assistant (Workflow D)**
Manifold/repair, wall-thickness & feature warnings, tolerance/fit presets,
orientation hint. Bolted onto every export.

**Phase 3 — Photo measurement + fix (Workflow B)**
Card calibration, click-to-measure, error estimate. Parametric-rebuild path first;
add the cloud mesh-capture path second. Broken-region repair (mirror/fill/re-thread).

**Phase 4 — Multi-colour signs (Workflow C)**
Text + shape builder → per-colour bodies → standard 3MF. Then image colour
separation → layered 3MF. Verify round-trip in Anycubic Slicer Next early.

**Phase 5 — Polish**
Design library/history, re-edit saved parts, prompt presets, batch export, small
UX niceties.

---

## 7. Extra functionality worth adding (from the web scan)

Things comparable 2026 tools do that fit your use case:

- **Auto-generated joints** — mortise-and-tenon, ball joints, snap-fits, with FDM
  shrink-aware tolerance calc (à la Hi3D). Great for multi-part functional prints.
- **Parametric threads / bolt & nut library** — real ISO threads generated in code
  so replacement fasteners/caps actually screw in.
- **"Second opinion" generation** — offer both a CadQuery result and a hosted
  text-to-CAD (Zoo / AdamCAD) result, pick the better one.
- **Watertight-by-default guarantee** — never let a non-manifold mesh reach export
  (the single biggest predictor of a good print).
- **Remix an existing STL** — upload a model and ask the AI to modify it
  (add a mount, scale a feature, cut a hole).
- **Print-time / filament estimate** and a rough cost note per job.
- **Reference-object library** — credit card by default, but also coin/A4/ruler
  presets for when no card is handy.
- **Photo-quality coach** — warn on angled/blurry/low-res shots *before* measuring,
  since square-on high-res is what keeps error under a few percent.
- **Design history & versioning** — every generation saved with its prompt + params
  so you can branch and roll back.

---

## 8. Cost & privacy (internal use)

- **Per-use cloud cost only** — no infra bills beyond the laptop. Expect a few
  cents to ~a couple dollars per design depending on LLM tokens and whether the
  organic mesh service is invoked (image→3D services meter credits; the parametric
  path is just LLM tokens and is cheap).
- **Privacy:** photos and prompts leave the machine (cloud APIs). Fine for personal
  parts; note it if you ever photograph something sensitive. A future **local
  fallback** (Workflow B measurement + CadQuery can run fully offline; only mesh
  capture truly needs the cloud) is a clean later upgrade if you get a GPU.
- **Keys** live in `.env`, never committed.

---

## 9. Key risks & mitigations

| Risk | Mitigation |
|---|---|
| Mesh-gen parts aren't dimensionally accurate | Lead with **parametric CAD** for functional work; reserve mesh gen for decorative. |
| Single photo → wrong dimensions (perspective) | Require the **scale card**, coach for square-on shots, show an **error estimate**, let you correct dims by hand. |
| LLM writes CAD code that errors or is non-manifold | Execute in a sandbox, capture errors, auto-retry with the error fed back; always run manifold check + repair. |
| Slicer Next won't read the colours | Emit **standard multi-body 3MF** (one body per colour), verified against Slicer Next early in Phase 4 — *not* Bambu-proprietary paint. |
| Cloud service/API changes | Keep image→3D and text-to-CAD behind a thin adapter interface so a provider can be swapped. |
| CPU-only slowness | All heavy compute is cloud; local steps (CAD exec, OpenCV) are light and fast on CPU. |

---

## 10. Open questions to settle before/into Phase 1

1. Preferred parametric engine: **CadQuery** (Python, gives STEP) vs **OpenSCAD**
   (simpler, huge community, STL-only)? *Recommendation: CadQuery primary.*
2. Which image→3D provider to start with (Meshy / Tripo / Rodin)? *Pick one; the
   adapter makes switching cheap.*
3. Default filament palette for the ACE Pro (drives sign colour separation).
4. Your typical part sizes / printer build volume (for warnings & orientation).

---

## Appendix — Research sources

Text-to-CAD / parametric:
- [Best AI CAD tools 2026 (RapidDirect)](https://www.rapiddirect.com/blog/best-ai-cad-tools-review/)
- [AdamCAD review 2026](https://pasqualepillitteri.it/en/news/3372/adamcad-text-to-cad-ai-review-2026)
- [Text to CAD (Zoo-style generator)](https://text-to-cad.uk/)

Image→3D / STL:
- [Meshy — Image to 3D](https://www.meshy.ai/features/image-to-3d)
- [Hyper3D Rodin](https://hyper3d.ai/)
- [Tripo 3D](https://www.tripo3d.ai/)
- [Best AI tools for 3D printing 2026 (Meshy blog)](https://www.meshy.ai/blog/best-ai-tools-for-3d-printing)
- [Hi3D printable AI models (MakeUseOf)](https://www.makeuseof.com/hi3d-makes-ai-generated-3d-models/)

Measurement from photo (scale reference):
- [Measuring object size with OpenCV (PyImageSearch)](https://pyimagesearch.com/2016/03/28/measuring-size-of-objects-in-an-image-with-opencv/)
- [Get dimensions from a photo — the reference trick](https://techdrawai.com/blog/get-dimensions-from-a-photo)
- [Object measurement with computer vision (Roboflow)](https://blog.roboflow.com/object-measurement-computer-vision/)

Multi-colour signs / Anycubic export:
- [Anycubic Slicer Next (Orca version) wiki](https://wiki.anycubic.com/en/software-and-app/new-page-anycubic-slicer-beta(orca-version))
- [Anycubic ACE Pro multi-colour setup](https://filamino.com/blog/anycubic-ace-pro-multi-color-setup-guide)
- [Flat image to multicolor 3D print (VectoSolve)](https://vectosolve.com/blog/image-to-multicolor-3d-print)
- [First multicolor 3MF (Layerpaint)](https://layerpaint.app/blog/first-multicolor-3mf-paint)
