"""Build a stored design at given parameter values and export files to disk."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cad.executor import BuildResult, build_and_export
from ..config import settings


def current_params(design: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    params = {p["name"]: p["value"] for p in design["parameters"] if "name" in p}
    if overrides:
        for key, val in overrides.items():
            if key in params:
                params[key] = val
    return params


def build_design(design: dict[str, Any], params: dict[str, Any]) -> BuildResult:
    stem = settings.generated_dir / design["id"] / "model"
    return build_and_export(design["code"], params, stem)


def stl_path(design_id: str) -> Path:
    return settings.generated_dir / design_id / "model.stl"


def step_path(design_id: str) -> Path:
    return settings.generated_dir / design_id / "model.step"
