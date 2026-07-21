"""Print-readiness checks: overhang detection, thin walls, profile, fit presets."""
from pathlib import Path

import trimesh

from app.cad.executor import build_and_export
from app.cad.primitives import DEMO_CODE, DEMO_PARAMETERS
from app.print_check.analyze import analyze
from app.print_check.profile import FIT_PRESETS, PrinterProfile


def _profile() -> PrinterProfile:
    return PrinterProfile()  # 0.4 nozzle -> 0.8 min wall


def test_profile_derived_values():
    p = _profile()
    assert p.min_wall == 0.8
    assert p.min_feature == 0.4
    assert len(FIT_PRESETS) >= 4


def test_flat_box_needs_no_support(tmp_path: Path):
    params = {p["name"]: p["value"] for p in DEMO_PARAMETERS}
    result = build_and_export(DEMO_CODE, params, tmp_path / "box")
    r = analyze(result.stl_path, _profile())
    assert r.watertight is True
    assert r.support_needed is False
    assert any(c.name == "Overhangs" and c.status == "ok" for c in r.checks)


def test_overhang_shape_needs_support(tmp_path: Path):
    # A "mushroom": a wide cap on a thin post -> the cap underside overhangs.
    post = trimesh.creation.box(extents=[6, 6, 20]); post.apply_translation([0, 0, 10])
    cap = trimesh.creation.box(extents=[30, 30, 4]); cap.apply_translation([0, 0, 22])
    shape = trimesh.boolean.union([post, cap])
    stl = tmp_path / "mushroom.stl"
    shape.export(str(stl))

    r = analyze(stl, _profile())
    assert r.support_needed is True
    assert r.support_pct > 0
    assert any(c.name == "Overhangs" and c.status == "warn" for c in r.checks)


def test_thin_wall_is_flagged(tmp_path: Path):
    plate = trimesh.creation.box(extents=[40, 40, 0.5])  # 0.5 mm < 0.8 mm min wall
    stl = tmp_path / "plate.stl"
    plate.export(str(stl))

    r = analyze(stl, _profile())
    assert r.min_wall_mm is not None and r.min_wall_mm < 0.8
    assert any(c.name == "Wall thickness" and c.status == "warn" for c in r.checks)
