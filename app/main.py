"""FastAPI app: text -> parametric CAD -> preview -> STL/STEP.

Phase 0: parametric demo model, live preview, download (no API key needed).
Phase 1: describe a part in words -> Claude writes CadQuery -> same pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database as db
from .cad.executor import CadExecutionError
from .cad.primitives import DEMO_CODE, DEMO_PARAMETERS
from .cad.validate import UnsafeCodeError
from .config import settings
from .measure.references import REFERENCE_OBJECTS
from .print_check.profile import FIT_PRESETS
from .services import build_service as builder
from .signs import service as sign_service
from .signs.builder import DEFAULTS as SIGN_DEFAULTS

_IMAGE_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="AI 3D Print Designer")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Initialise on import so the app is ready under uvicorn and the test client alike.
settings.ensure_dirs()
db.init_db()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _build_and_store(
    design: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    color_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    params = builder.current_params(design, overrides)
    colors = builder.body_colors(design, color_overrides)
    built = builder.build_design(design, params, colors=colors)

    if overrides:  # persist dimensional changes
        for p in design["parameters"]:
            if p["name"] in params:
                p["value"] = params[p["name"]]
        db.update_parameters(design["id"], design["parameters"])

    # Sync body metadata (names + resolved colours) so the pickers + 3MF stay in step.
    result_bodies = [{"name": b.name, "color": b.color} for b in built.result.bodies]
    if result_bodies != design.get("bodies"):
        db.update_bodies(design["id"], result_bodies)
        design["bodies"] = result_bodies

    manifest = [
        {"index": b.index, "name": b.name, "color": b.color,
         "stl_url": f"/design/{design['id']}/body/{b.index}.stl"}
        for b in built.result.bodies
    ]
    return {
        "report": built.result.report,
        "readiness": built.readiness,
        "has_step": built.result.step_path is not None,
        "has_repaired": built.readiness.repaired,
        "bodies": manifest,
        "params": params,
    }


def _preview_ctx(design: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "design": design,
        "report": result["report"],
        "readiness": result["readiness"],
        "has_step": result["has_step"],
        "has_repaired": result["has_repaired"],
        "bodies": result["bodies"],
    }


def _coerce(raw: str) -> float:
    return int(raw) if raw.strip().lstrip("-").isdigit() else float(raw)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"designs": db.list_designs(), "has_key": bool(settings.anthropic_api_key)},
    )


@app.post("/demo")
def create_demo():
    """Seed a parametric demo design (no AI) and open it."""
    design_id = db.save_design(
        design_id=None,
        name="demo-rounded-box",
        description="Parametric rounded box — the Phase 0 pipeline demo.",
        prompt="",
        engine="cadquery",
        code=DEMO_CODE,
        parameters=[dict(p) for p in DEMO_PARAMETERS],
    )
    design = db.get_design(design_id)
    _build_and_store(design)
    return HTMLResponse(status_code=303, headers={"Location": f"/design/{design_id}"})


@app.post("/generate", response_class=HTMLResponse)
def generate(request: Request, prompt: str = Form(...)):
    from .ai.generator import GenerationError, generate as ai_generate

    try:
        gen = ai_generate(prompt, profile=builder.active_profile().as_dict())
    except GenerationError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"designs": db.list_designs(),
             "has_key": bool(settings.anthropic_api_key), "error": str(exc)},
            status_code=400,
        )
    design_id = db.save_design(
        design_id=None, name=gen.name, description=gen.description, prompt=prompt,
        engine="cadquery", code=gen.code, parameters=gen.parameters, bodies=gen.bodies,
    )
    design = db.get_design(design_id)
    _build_and_store(design)
    return HTMLResponse(status_code=303, headers={"Location": f"/design/{design_id}"})


@app.get("/design/{design_id}", response_class=HTMLResponse)
def design_page(request: Request, design_id: str):
    design = db.get_design(design_id)
    if not design:
        raise HTTPException(404, "Design not found")
    result = _build_and_store(design)
    ctx = _preview_ctx(design, result)
    ctx.update({"profile": builder.active_profile().as_dict(), "fit_presets": FIT_PRESETS})
    return templates.TemplateResponse(request, "design.html", ctx)


@app.post("/design/{design_id}/rebuild", response_class=HTMLResponse)
async def rebuild(request: Request, design_id: str):
    design = db.get_design(design_id)
    if not design:
        raise HTTPException(404, "Design not found")
    form = await request.form()
    overrides: dict[str, Any] = {}
    for p in design["parameters"]:
        name = p["name"]
        if name in form:
            try:
                overrides[name] = _coerce(str(form[name]))
            except ValueError:
                pass
    color_overrides: dict[str, str] = {}
    for b in design.get("bodies", []):
        key = f"color_{b['name']}"
        if form.get(key):
            color_overrides[b["name"]] = str(form[key])
    try:
        result = _build_and_store(design, overrides, color_overrides)
    except (CadExecutionError, UnsafeCodeError) as exc:
        return HTMLResponse(f'<div class="alert alert-danger mb-0">Build failed: {exc}</div>',
                            status_code=400)
    design = db.get_design(design_id)  # refresh persisted values
    return templates.TemplateResponse(request, "_preview.html", _preview_ctx(design, result))


# --------------------------------------------------------------------------- #
# File downloads
# --------------------------------------------------------------------------- #
@app.get("/design/{design_id}/model.stl")
def get_stl(design_id: str):
    path = builder.stl_path(design_id)
    if not path.exists():
        raise HTTPException(404, "STL not built yet")
    return FileResponse(path, media_type="model/stl", filename=f"{design_id}.stl")


@app.get("/design/{design_id}/model.step")
def get_step(design_id: str):
    path = builder.step_path(design_id)
    if not path.exists():
        raise HTTPException(404, "STEP not available")
    return FileResponse(path, media_type="application/step", filename=f"{design_id}.step")


@app.get("/design/{design_id}/model.3mf")
def get_design_3mf(design_id: str):
    path = builder.threemf_path(design_id)
    if not path.exists():
        raise HTTPException(404, "3MF not built yet")
    return FileResponse(path, media_type="model/3mf", filename=f"{design_id}.3mf")


@app.get("/design/{design_id}/body/{index}.stl")
def get_design_body(design_id: str, index: int):
    path = builder.body_stl_path(design_id, index)
    if not path.exists():
        raise HTTPException(404, "Body not found")
    return FileResponse(path, media_type="model/stl", filename=f"{design_id}-{index}.stl")


@app.get("/design/{design_id}/repaired.stl")
def get_repaired(design_id: str):
    path = builder.repaired_stl_path(design_id)
    if not path.exists():
        raise HTTPException(404, "No repaired STL for this design")
    return FileResponse(path, media_type="model/stl", filename=f"{design_id}-repaired.stl")


# --------------------------------------------------------------------------- #
# Phase 3: photo -> measure (with a reference object) -> reconstruct
# --------------------------------------------------------------------------- #
@app.post("/capture/upload")
async def capture_upload(photo: UploadFile = File(...)):
    ext = _IMAGE_EXTS.get(photo.content_type or "")
    if not ext:
        raise HTTPException(400, "Please upload a PNG, JPEG, or WebP image.")
    capture_id = db.new_id()
    dest = settings.uploads_dir / f"{capture_id}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await photo.read())
    db.create_capture(str(dest), capture_id=capture_id)
    return HTMLResponse(status_code=303, headers={"Location": f"/capture/{capture_id}"})


@app.get("/capture/{capture_id}", response_class=HTMLResponse)
def capture_page(request: Request, capture_id: str):
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")
    return templates.TemplateResponse(
        request, "measure.html",
        {"capture": capture, "references": REFERENCE_OBJECTS},
    )


@app.get("/capture/{capture_id}/image")
def capture_image(capture_id: str):
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")
    path = Path(capture["photo_path"])
    if not path.exists():
        raise HTTPException(404, "Image missing")
    return FileResponse(path)


@app.post("/capture/{capture_id}/build")
async def capture_build(request: Request, capture_id: str):
    capture = db.get_capture(capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")
    payload = await request.json()
    measurements = payload.get("measurements", [])
    db.save_capture_measurements(
        capture_id,
        reference_label=str(payload.get("reference_label", "")),
        reference_mm=float(payload.get("reference_mm", 0) or 0),
        mm_per_px=float(payload.get("mm_per_px", 0) or 0),
        measurements=measurements,
        description=str(payload.get("description", "")),
    )
    from .ai.generator import GenerationError, generate_from_capture

    try:
        gen = generate_from_capture(
            description=str(payload.get("description", "")),
            measurements=measurements,
            image_path=Path(capture["photo_path"]),
            profile=builder.active_profile().as_dict(),
        )
    except GenerationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    design_id = db.save_design(
        design_id=None, name=gen.name, description=gen.description,
        prompt=f"[reconstructed from photo] {payload.get('description', '')}",
        engine="cadquery", code=gen.code, parameters=gen.parameters, bodies=gen.bodies,
    )
    db.attach_design_to_capture(capture_id, design_id)
    _build_and_store(db.get_design(design_id))
    return JSONResponse({"design_url": f"/design/{design_id}"})


# --------------------------------------------------------------------------- #
# Phase 4: multi-colour signs -> standard 3MF for Slicer Next / ACE Pro
# --------------------------------------------------------------------------- #
_SIGN_NUM = ("plate_w", "plate_h", "plate_thickness", "corner_radius", "text_size",
             "text_height", "border_width", "border_height", "hole_diameter")
_SIGN_COLORS = ("base_color", "text_color", "border_color")


def _parse_sign_form(form: Any, base: dict[str, Any]) -> dict[str, Any]:
    p = dict(base)
    p["text"] = str(form.get("text", ""))
    for k in _SIGN_NUM:
        if k in form:
            try:
                p[k] = float(form[k])
            except ValueError:
                pass
    for k in _SIGN_COLORS:
        if form.get(k):
            p[k] = str(form[k])
    p["border"] = form.get("border") is not None  # unchecked checkbox is absent
    p["holes"] = form.get("holes") is not None
    return p


@app.post("/signs/new")
def sign_new():
    params = dict(SIGN_DEFAULTS)
    sign_id = db.save_sign(None, params["text"], params)
    sign_service.build_sign(sign_id, params)
    return HTMLResponse(status_code=303, headers={"Location": f"/signs/{sign_id}"})


@app.post("/signs/generate", response_class=HTMLResponse)
def sign_generate(request: Request, prompt: str = Form(...)):
    """AI sign: describe it -> Claude builds a multi-colour sign as a design."""
    from .ai.generator import GenerationError, generate as ai_generate

    framed = (
        "Design a multi-colour, 3D-printable SIGN or nameplate as a flat plate that "
        "prints face-up. Use separate coloured bodies for the base plate, the raised "
        "text/lettering, and any border or graphic elements. Request:\n" + prompt
    )
    try:
        gen = ai_generate(framed, profile=builder.active_profile().as_dict())
    except GenerationError as exc:
        return templates.TemplateResponse(
            request, "index.html",
            {"designs": db.list_designs(), "has_key": bool(settings.anthropic_api_key),
             "error": str(exc)}, status_code=400,
        )
    design_id = db.save_design(
        design_id=None, name=gen.name, description=gen.description, prompt=f"[sign] {prompt}",
        engine="cadquery", code=gen.code, parameters=gen.parameters, bodies=gen.bodies,
    )
    _build_and_store(db.get_design(design_id))
    return HTMLResponse(status_code=303, headers={"Location": f"/design/{design_id}"})


@app.get("/signs/{sign_id}", response_class=HTMLResponse)
def sign_page(request: Request, sign_id: str):
    sign = db.get_sign(sign_id)
    if not sign:
        raise HTTPException(404, "Sign not found")
    manifest = sign_service.build_sign(sign_id, sign["params"])
    return templates.TemplateResponse(
        request, "signs.html", {"sign": sign, "manifest": manifest, "defaults": SIGN_DEFAULTS},
    )


@app.post("/signs/{sign_id}/rebuild", response_class=HTMLResponse)
async def sign_rebuild(request: Request, sign_id: str):
    sign = db.get_sign(sign_id)
    if not sign:
        raise HTTPException(404, "Sign not found")
    form = await request.form()
    params = _parse_sign_form(form, sign["params"])
    db.save_sign(sign_id, params["text"], params)
    try:
        manifest = sign_service.build_sign(sign_id, params)
    except Exception as exc:  # noqa: BLE001 - surface geometry errors to the user
        return HTMLResponse(f'<div class="alert alert-danger mb-0">Build failed: {exc}</div>',
                            status_code=400)
    return templates.TemplateResponse(
        request, "_sign_preview.html", {"sign_id": sign_id, "manifest": manifest},
    )


@app.get("/signs/{sign_id}/sign.3mf")
def get_sign_3mf(sign_id: str):
    path = sign_service.threemf_path(sign_id)
    if not path.exists():
        raise HTTPException(404, "3MF not built yet")
    return FileResponse(path, media_type="model/3mf", filename=f"{sign_id}.3mf")


@app.get("/signs/{sign_id}/body/{index}.stl")
def get_sign_body(sign_id: str, index: int):
    path = sign_service.body_stl_path(sign_id, index)
    if not path.exists():
        raise HTTPException(404, "Body not found")
    return FileResponse(path, media_type="model/stl", filename=f"{sign_id}-{index}.stl")


# --------------------------------------------------------------------------- #
# Printer profile
# --------------------------------------------------------------------------- #
@app.post("/profile")
async def update_profile(request: Request, design_id: str = Form(...)):
    """Update the in-memory printer profile and re-open the design."""
    form = await request.form()
    for field in ("nozzle_diameter", "layer_height", "overhang_threshold_deg", "default_clearance"):
        if field in form:
            try:
                setattr(settings, field, float(form[field]))
            except ValueError:
                pass
    return HTMLResponse(status_code=303, headers={"Location": f"/design/{design_id}"})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
