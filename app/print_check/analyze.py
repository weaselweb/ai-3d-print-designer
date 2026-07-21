"""Print-readiness analysis for an exported STL.

Runs on every build and reports, against the active printer profile:
  - watertight / manifold (with an auto-repair attempt)
  - overhangs that will need support
  - an estimated minimum wall thickness (inward ray casting)
  - smallest feature vs. nozzle
  - a suggested print orientation that minimises support
Everything is best-effort and defensive: a failed sub-check degrades to an
informational note rather than breaking the build.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from .profile import PrinterProfile

# Cap ray-cast work so analysis stays snappy on CPU-only machines.
_WALL_SAMPLES = 200
_WALL_FACE_CAP = 40000


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail | info
    detail: str


@dataclass
class PrintReadiness:
    checks: list[Check] = field(default_factory=list)
    watertight: bool = False
    support_pct: float = 0.0
    support_needed: bool = False
    min_wall_mm: float | None = None
    min_feature_mm: float = 0.0
    footprint_mm: tuple[float, float] = (0.0, 0.0)
    height_mm: float = 0.0
    recommended_orientation: str = "As modelled"
    orientation_improves: bool = False
    repaired: bool = False
    repaired_path: str | None = None
    profile: dict = field(default_factory=dict)

    @property
    def worst_status(self) -> str:
        order = {"fail": 3, "warn": 2, "info": 1, "ok": 0}
        return max((c.status for c in self.checks), key=lambda s: order.get(s, 0), default="ok")


# --------------------------------------------------------------------------- #
# Sub-checks
# --------------------------------------------------------------------------- #
def try_repair(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, bool]:
    """Attempt a light repair if the mesh isn't watertight. Returns (mesh, changed)."""
    if mesh.is_watertight:
        return mesh, False
    fixed = mesh.copy()
    try:
        fixed.merge_vertices()
        fixed.update_faces(fixed.unique_faces())
        fixed.remove_infinite_values()
        trimesh.repair.fill_holes(fixed)
        trimesh.repair.fix_normals(fixed)
    except Exception:  # noqa: BLE001
        return mesh, False
    return fixed, bool(fixed.is_watertight and not mesh.is_watertight)


def _support_area(mesh: trimesh.Trimesh, profile: PrinterProfile) -> tuple[float, float]:
    """Return (support_area_mm2, support_pct_of_total)."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    total = float(areas.sum()) or 1.0
    nz = normals[:, 2]
    cos_thresh = math.cos(math.radians(profile.overhang_threshold_deg))
    # Downward faces steeper (more horizontal) than the threshold need support.
    support_mask = (-nz) >= cos_thresh
    # Exclude faces resting on the bed.
    zmin = float(mesh.bounds[0][2])
    bed = (nz < -0.99) & (mesh.triangles_center[:, 2] <= zmin + max(profile.layer_height, 0.2))
    support_mask &= ~bed
    area = float(areas[support_mask].sum())
    return area, 100.0 * area / total


def _min_wall(mesh: trimesh.Trimesh, profile: PrinterProfile) -> float | None:
    """Estimate the minimum wall thickness by casting rays inward from faces."""
    n_faces = len(mesh.faces)
    if n_faces == 0 or n_faces > _WALL_FACE_CAP:
        return None
    normals = mesh.face_normals
    centers = mesh.triangles_center
    step = max(1, n_faces // _WALL_SAMPLES)
    idx = np.arange(0, n_faces, step)
    eps = 1e-3
    origins = centers[idx] - normals[idx] * eps
    dirs = -normals[idx]
    try:
        locs, index_ray, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    except Exception:  # noqa: BLE001
        return None
    if len(locs) == 0:
        return None
    dist = np.linalg.norm(locs - origins[index_ray], axis=1)
    dist = dist[dist > 5e-3]  # drop self-intersections
    if len(dist) == 0:
        return None
    return round(float(dist.min()), 3)


_ORIENTATIONS = [
    ("As modelled", None),
    ("Flipped upside-down", ("x", 180)),
    ("On its right (+X) face", ("y", -90)),
    ("On its left (−X) face", ("y", 90)),
    ("On its front (−Y) face", ("x", 90)),
    ("On its back (+Y) face", ("x", -90)),
]


def _suggest_orientation(mesh: trimesh.Trimesh, profile: PrinterProfile) -> tuple[str, float, float]:
    """Return (best_label, best_support_area, current_support_area)."""
    results: list[tuple[str, float]] = []
    for label, rot in _ORIENTATIONS:
        m = mesh if rot is None else mesh.copy()
        if rot is not None:
            axis = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[rot[0]]
            m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(rot[1]), axis))
        area, _ = _support_area(m, profile)
        results.append((label, area))
    current = results[0][1]
    best_label, best_area = min(results, key=lambda r: r[1])
    return best_label, best_area, current


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def analyze(stl_path: Path, profile: PrinterProfile, repaired_out: Path | None = None) -> PrintReadiness:
    r = PrintReadiness(profile=profile.as_dict())
    try:
        mesh = trimesh.load(str(stl_path), force="mesh")
    except Exception as exc:  # noqa: BLE001
        r.checks.append(Check("Mesh", "fail", f"Could not load mesh: {exc}"))
        return r

    # Dimensions
    ext = mesh.extents if mesh.extents is not None else np.zeros(3)
    r.footprint_mm = (round(float(ext[0]), 2), round(float(ext[1]), 2))
    r.height_mm = round(float(ext[2]), 2)
    r.min_feature_mm = round(float(min(ext)), 2) if len(ext) else 0.0

    # Watertight (+ repair)
    r.watertight = bool(mesh.is_watertight)
    if r.watertight:
        r.checks.append(Check("Watertight", "ok", "Closed, manifold mesh — safe to slice."))
    else:
        fixed, changed = try_repair(mesh)
        if changed and repaired_out is not None:
            repaired_out.parent.mkdir(parents=True, exist_ok=True)
            fixed.export(str(repaired_out))
            r.repaired, r.repaired_path = True, repaired_out.name
            mesh = fixed
            r.watertight = True
            r.checks.append(Check("Watertight", "warn",
                                  "Was not watertight — auto-repaired. Download the repaired STL."))
        else:
            r.checks.append(Check("Watertight", "fail",
                                  "Not watertight and auto-repair failed — may not slice cleanly."))

    # Overhangs / support
    try:
        area, pct = _support_area(mesh, profile)
        r.support_pct = round(pct, 1)
        r.support_needed = area > 2.0
        if r.support_needed:
            r.checks.append(Check(
                "Overhangs", "warn",
                f"~{r.support_pct}% of surface overhangs beyond "
                f"{profile.overhang_threshold_deg:.0f}° — enable supports."))
        else:
            r.checks.append(Check("Overhangs", "ok", "No significant overhangs — supports not needed."))
    except Exception as exc:  # noqa: BLE001
        r.checks.append(Check("Overhangs", "info", f"Overhang check skipped: {exc}"))

    # Minimum wall thickness
    r.min_wall_mm = _min_wall(mesh, profile)
    if r.min_wall_mm is None:
        r.checks.append(Check("Wall thickness", "info", "Wall estimate unavailable for this mesh."))
    elif r.min_wall_mm < profile.min_wall:
        r.checks.append(Check(
            "Wall thickness", "warn",
            f"Thinnest wall ≈ {r.min_wall_mm} mm, below the {profile.min_wall} mm minimum "
            f"for a {profile.nozzle_diameter} mm nozzle — may be weak or fail to print."))
    else:
        r.checks.append(Check("Wall thickness", "ok",
                              f"Thinnest wall ≈ {r.min_wall_mm} mm — above the {profile.min_wall} mm minimum."))

    # Smallest feature
    if r.min_feature_mm and r.min_feature_mm < profile.min_feature:
        r.checks.append(Check("Feature size", "warn",
                              f"Smallest dimension {r.min_feature_mm} mm is under one nozzle width "
                              f"({profile.min_feature} mm) — detail may be lost."))

    # Orientation
    try:
        best_label, best_area, current_area = _suggest_orientation(mesh, profile)
        r.recommended_orientation = best_label
        r.orientation_improves = best_area < current_area * 0.9 and (current_area - best_area) > 2.0
        if r.orientation_improves:
            r.checks.append(Check("Orientation", "info",
                                  f"'{best_label}' would cut overhang area (less support). "
                                  "Rotate in your slicer."))
        else:
            r.checks.append(Check("Orientation", "ok", "Current orientation is a good choice for support."))
    except Exception as exc:  # noqa: BLE001
        r.checks.append(Check("Orientation", "info", f"Orientation check skipped: {exc}"))

    return r
