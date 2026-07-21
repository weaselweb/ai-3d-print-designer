"""Execute parametric CadQuery code and export print files.

The model produces code that defines `build(params) -> cadquery object`. We run
that function with the current parameter values, export STL + STEP, and run a
manifold / watertight check so nothing non-printable reaches the user.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .validate import UnsafeCodeError, validate_code


@dataclass
class MeshReport:
    watertight: bool = False
    volume_mm3: float = 0.0
    bbox_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    triangles: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    stl_path: Path
    step_path: Path | None
    report: MeshReport


class CadExecutionError(RuntimeError):
    pass


_IMPORTABLE = {"cadquery", "math", "numpy"}


def _safe_import(name: str, *args: Any, **kwargs: Any):
    """Restricted __import__ so exec'd code can `import cadquery` but nothing else."""
    import builtins as _bi

    if name.split(".")[0] not in _IMPORTABLE:
        raise ImportError(f"import of {name!r} is not allowed")
    return _bi.__import__(name, *args, **kwargs)


def _make_namespace() -> dict[str, Any]:
    import cadquery as cq  # imported lazily so the app boots without it installed

    # Minimal builtins: enough to build geometry, nothing to touch the system.
    safe_builtins = {
        "__import__": _safe_import,
        "abs": abs, "min": min, "max": max, "round": round, "range": range,
        "len": len, "enumerate": enumerate, "zip": zip, "map": map, "list": list,
        "dict": dict, "tuple": tuple, "set": set, "float": float, "int": int,
        "bool": bool, "str": str, "sum": sum, "sorted": sorted, "print": print,
    }
    return {"__builtins__": safe_builtins, "cq": cq, "cadquery": cq, "math": math}


def run_build(code: str, params: dict[str, Any]) -> Any:
    """Validate, exec, and call build(params). Returns a cadquery object."""
    validate_code(code)
    ns = _make_namespace()
    try:
        exec(compile(code, "<cad>", "exec"), ns)  # noqa: S102 - guarded above
    except UnsafeCodeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CadExecutionError(f"Error while defining model: {exc}") from exc

    build = ns.get("build")
    if not callable(build):
        raise CadExecutionError("Code did not define a callable `build`.")
    try:
        obj = build(dict(params))
    except Exception as exc:  # noqa: BLE001
        raise CadExecutionError(f"build(params) raised: {exc}") from exc
    if obj is None:
        raise CadExecutionError("build(params) returned None.")
    return obj


def export(obj: Any, stem: Path) -> BuildResult:
    """Export a cadquery object to STL + STEP and inspect the mesh."""
    import cadquery as cq

    stl_path = stem.with_suffix(".stl")
    step_path = stem.with_suffix(".step")
    stl_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cq.exporters.export(obj, str(stl_path), exportType="STL")
    except Exception as exc:  # noqa: BLE001
        raise CadExecutionError(f"STL export failed: {exc}") from exc

    step_ok = True
    try:
        cq.exporters.export(obj, str(step_path), exportType="STEP")
    except Exception:  # noqa: BLE001 - STEP is a bonus, never fatal
        step_ok = False

    report = inspect_mesh(stl_path)
    return BuildResult(stl_path=stl_path, step_path=step_path if step_ok else None, report=report)


def inspect_mesh(stl_path: Path) -> MeshReport:
    """Load the STL and report printability basics."""
    report = MeshReport()
    try:
        import trimesh

        mesh = trimesh.load(str(stl_path), force="mesh")
        report.triangles = int(len(mesh.faces))
        report.watertight = bool(mesh.is_watertight)
        report.volume_mm3 = float(abs(mesh.volume))
        ext = mesh.extents if mesh.extents is not None else [0, 0, 0]
        report.bbox_mm = (round(float(ext[0]), 2), round(float(ext[1]), 2), round(float(ext[2]), 2))
        if not report.watertight:
            report.warnings.append(
                "Mesh is not watertight — attempting repair is recommended before slicing."
            )
        if report.triangles == 0:
            report.warnings.append("Mesh has no triangles — the model may be empty.")
    except Exception as exc:  # noqa: BLE001
        report.warnings.append(f"Could not inspect mesh: {exc}")
    return report


def build_and_export(code: str, params: dict[str, Any], stem: Path) -> BuildResult:
    obj = run_build(code, params)
    return export(obj, stem)
