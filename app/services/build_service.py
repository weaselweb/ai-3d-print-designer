"""Build a stored design at given parameter values and export files to disk,
then run the print-readiness analysis against the active printer profile."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..cad.executor import BuildResult, build_and_export
from ..config import settings
from ..print_check.analyze import PrintReadiness, analyze
from ..print_check.profile import PrinterProfile


def active_profile() -> PrinterProfile:
    return PrinterProfile(
        nozzle_diameter=settings.nozzle_diameter,
        layer_height=settings.layer_height,
        overhang_threshold_deg=settings.overhang_threshold_deg,
        default_clearance=settings.default_clearance,
    )


@dataclass
class BuiltDesign:
    result: BuildResult
    readiness: PrintReadiness
    params: dict[str, Any]


def current_params(design: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    params = {p["name"]: p["value"] for p in design["parameters"] if "name" in p}
    if overrides:
        for key, val in overrides.items():
            if key in params:
                params[key] = val
    return params


def body_colors(design: dict[str, Any], overrides: dict[str, str] | None = None) -> dict[str, str]:
    colors = {b["name"]: b.get("color") for b in design.get("bodies", []) if "name" in b}
    if overrides:
        colors.update({k: v for k, v in overrides.items() if v})
    return colors


def build_design(
    design: dict[str, Any],
    params: dict[str, Any],
    profile: PrinterProfile | None = None,
    colors: dict[str, str] | None = None,
) -> BuiltDesign:
    profile = profile or active_profile()
    stem = settings.generated_dir / design["id"] / "model"
    result = build_and_export(design["code"], params, stem, colors)
    readiness = analyze(result.stl_path, profile, repaired_out=stem.parent / "model_repaired.stl")
    return BuiltDesign(result=result, readiness=readiness, params=params)


def stl_path(design_id: str) -> Path:
    return settings.generated_dir / design_id / "model.stl"


def step_path(design_id: str) -> Path:
    return settings.generated_dir / design_id / "model.step"


def threemf_path(design_id: str) -> Path:
    return settings.generated_dir / design_id / "model.3mf"


def body_stl_path(design_id: str, index: int) -> Path:
    return settings.generated_dir / design_id / f"body_{index}.stl"


def repaired_stl_path(design_id: str) -> Path:
    return settings.generated_dir / design_id / "model_repaired.stl"
