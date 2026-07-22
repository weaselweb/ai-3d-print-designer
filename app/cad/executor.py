"""Execute parametric CadQuery code and export print files.

The model defines `build(params)` that returns EITHER a single cadquery object
or a dict mapping a body name to a cadquery object. Each body is a separate
colour. We run it, tessellate each body, then export:
  - a combined STL (preview / single-colour use)
  - a combined STEP (B-rep, when possible)
  - a standard multi-body **3MF** — every design is multicolour-ready, so this
    is always produced (a single-colour part is just one body).
A watertight / manifold check runs on the combined mesh.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..signs.threemf import Body, write_3mf
from .validate import UnsafeCodeError, validate_code

# Default palette for bodies the model didn't colour explicitly.
DEFAULT_PALETTE = ["#3b82f6", "#f4d35e", "#e0e0e0", "#ef4444", "#10b981", "#a855f7", "#f97316"]


@dataclass
class MeshReport:
    watertight: bool = False
    volume_mm3: float = 0.0
    bbox_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    triangles: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class BodyInfo:
    index: int
    name: str
    color: str
    stl_path: Path


@dataclass
class BuildResult:
    stl_path: Path
    step_path: Path | None
    threemf_path: Path
    report: MeshReport
    bodies: list[BodyInfo] = field(default_factory=list)


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

    safe_builtins = {
        "__import__": _safe_import,
        "abs": abs, "min": min, "max": max, "round": round, "range": range,
        "len": len, "enumerate": enumerate, "zip": zip, "map": map, "list": list,
        "dict": dict, "tuple": tuple, "set": set, "float": float, "int": int,
        "bool": bool, "str": str, "sum": sum, "sorted": sorted, "print": print,
    }
    return {"__builtins__": safe_builtins, "cq": cq, "cadquery": cq, "math": math}


def run_build(code: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate, exec, and call build(params). Returns an ordered {name: object} dict."""
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

    if isinstance(obj, dict):
        bodies = {str(k): v for k, v in obj.items() if v is not None}
        if not bodies:
            raise CadExecutionError("build(params) returned an empty body dict.")
        return bodies
    return {"body": obj}


def _to_mesh(obj: Any):
    import tempfile
    import os

    import cadquery as cq
    import trimesh

    path = tempfile.mktemp(suffix=".stl")
    try:
        cq.exporters.export(obj, path, exportType="STL")
        if not os.path.exists(path):
            raise CadExecutionError(
                "CadQuery produced no STL output for this body — the geometry is "
                "likely empty or invalid (e.g. self-intersecting)."
            )
        return trimesh.load(path, force="mesh")
    finally:
        if os.path.exists(path):
            os.remove(path)


def _combined_step(objs: dict[str, Any], step_path: Path) -> bool:
    import cadquery as cq

    shapes: list[Any] = []
    for o in objs.values():
        if hasattr(o, "vals"):
            shapes += [s for s in o.vals() if s is not None]
        else:
            shapes.append(o)
    try:
        cq.exporters.export(cq.Compound.makeCompound(shapes), str(step_path), exportType="STEP")
        return True
    except Exception:  # noqa: BLE001 - STEP is a bonus, never fatal
        return False


def export_design(
    objs: dict[str, Any], stem: Path, colors: dict[str, str] | None = None
) -> BuildResult:
    """Tessellate each body, then write per-body STLs, a combined STL/STEP, and a 3MF."""
    import trimesh

    colors = colors or {}
    stem.parent.mkdir(parents=True, exist_ok=True)

    body_infos: list[BodyInfo] = []
    threemf_bodies: list[Body] = []
    meshes = []
    for i, (name, obj) in enumerate(objs.items()):
        mesh = _to_mesh(obj)
        color = colors.get(name) or DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)]
        body_stl = stem.parent / f"body_{i}.stl"
        try:
            mesh.export(str(body_stl))
        except Exception as exc:  # noqa: BLE001
            raise CadExecutionError(f"Body '{name}' export failed: {exc}") from exc
        meshes.append(mesh)
        threemf_bodies.append(Body(name, mesh, color))
        body_infos.append(BodyInfo(index=i, name=name, color=color, stl_path=body_stl))

    # Combined STL for preview / single-colour download
    stl_path = stem.with_suffix(".stl")
    combined = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    combined.export(str(stl_path))

    # Always emit a multicolour-ready 3MF
    threemf_path = stem.with_suffix(".3mf")
    write_3mf(threemf_path, threemf_bodies)

    # STEP compound (optional)
    step_path = stem.with_suffix(".step")
    step_ok = _combined_step(objs, step_path)

    report = inspect_mesh(stl_path)
    return BuildResult(
        stl_path=stl_path,
        step_path=step_path if step_ok else None,
        threemf_path=threemf_path,
        report=report,
        bodies=body_infos,
    )


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


def build_and_export(
    code: str, params: dict[str, Any], stem: Path, colors: dict[str, str] | None = None
) -> BuildResult:
    objs = run_build(code, params)
    return export_design(objs, stem, colors)
