"""FastAPI app: text -> parametric CAD -> preview -> STL/STEP.

Phase 0: parametric demo model, live preview, download (no API key needed).
Phase 1: describe a part in words -> Claude writes CadQuery -> same pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database as db
from .cad.executor import CadExecutionError
from .cad.primitives import DEMO_CODE, DEMO_PARAMETERS
from .cad.validate import UnsafeCodeError
from .config import settings
from .print_check.profile import FIT_PRESETS
from .services import build_service as builder

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
def _build_and_store(design: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    params = builder.current_params(design, overrides)
    built = builder.build_design(design, params)
    # persist any override values back onto the parameter set
    if overrides:
        for p in design["parameters"]:
            if p["name"] in params:
                p["value"] = params[p["name"]]
        db.update_parameters(design["id"], design["parameters"])
    return {
        "report": built.result.report,
        "readiness": built.readiness,
        "has_step": built.result.step_path is not None,
        "has_repaired": built.readiness.repaired,
        "params": params,
    }


def _preview_ctx(design: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "design": design,
        "report": result["report"],
        "readiness": result["readiness"],
        "has_step": result["has_step"],
        "has_repaired": result["has_repaired"],
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
        engine="cadquery", code=gen.code, parameters=gen.parameters,
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
    try:
        result = _build_and_store(design, overrides)
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


@app.get("/design/{design_id}/repaired.stl")
def get_repaired(design_id: str):
    path = builder.repaired_stl_path(design_id)
    if not path.exists():
        raise HTTPException(404, "No repaired STL for this design")
    return FileResponse(path, media_type="model/stl", filename=f"{design_id}-repaired.stl")


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
