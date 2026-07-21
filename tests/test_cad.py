"""Engine tests: the demo model builds, exports, and is watertight; guard works."""
from pathlib import Path

import pytest

from app.cad.executor import CadExecutionError, build_and_export
from app.cad.primitives import DEMO_CODE, DEMO_PARAMETERS
from app.cad.validate import UnsafeCodeError, validate_code


def _default_params():
    return {p["name"]: p["value"] for p in DEMO_PARAMETERS}


def test_demo_builds_and_is_watertight(tmp_path: Path):
    result = build_and_export(DEMO_CODE, _default_params(), tmp_path / "model")
    assert result.stl_path.exists()
    assert result.step_path is not None and result.step_path.exists()
    assert result.report.watertight is True
    assert result.report.triangles > 0
    # 60 x 40 x 20 box
    assert result.report.bbox_mm[0] == pytest.approx(60, abs=0.5)
    assert result.report.bbox_mm[2] == pytest.approx(20, abs=0.5)


def test_params_change_geometry(tmp_path: Path):
    params = _default_params()
    params["length"] = 120
    result = build_and_export(DEMO_CODE, params, tmp_path / "m2")
    assert result.report.bbox_mm[0] == pytest.approx(120, abs=0.5)


def test_validator_blocks_imports():
    with pytest.raises(UnsafeCodeError):
        validate_code("import os\ndef build(params):\n    return None")


def test_validator_requires_build():
    with pytest.raises(UnsafeCodeError):
        validate_code("import cadquery as cq\nx = 1")


def test_bad_code_raises_execution_error(tmp_path: Path):
    code = "import cadquery as cq\ndef build(params):\n    return cq.Workplane('XY').boxx(1,1,1)"
    with pytest.raises(CadExecutionError):
        build_and_export(code, {}, tmp_path / "bad")
