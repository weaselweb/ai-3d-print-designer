"""Every design is multicolour-ready: multi-body build -> per-body STLs + 3MF."""
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from app.cad.executor import build_and_export

_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"

MULTI_CODE = """
import cadquery as cq
def build(params):
    base = cq.Workplane("XY").box(40, 20, 3)
    label = cq.Workplane("XY").workplane(offset=1.5).box(10, 5, 1)
    return {"base": base, "label": label}
"""

SINGLE_CODE = """
import cadquery as cq
def build(params):
    return cq.Workplane("XY").box(20, 20, 20)
"""


def test_multibody_exports_bodies_and_3mf(tmp_path: Path):
    result = build_and_export(MULTI_CODE, {}, tmp_path / "m",
                              colors={"base": "#111111", "label": "#ff0000"})
    assert len(result.bodies) == 2
    assert result.threemf_path.exists()
    for b in result.bodies:
        assert b.stl_path.exists()
    colors = {b.name: b.color for b in result.bodies}
    assert colors["label"] == "#ff0000"

    with zipfile.ZipFile(result.threemf_path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    assert len(root.findall(f".//{_NS}object")) == 2
    assert len(root.findall(f".//{_NS}base")) == 2


def test_single_body_still_gets_a_3mf(tmp_path: Path):
    # A single-colour part is just the one-body case — still a 3MF.
    result = build_and_export(SINGLE_CODE, {}, tmp_path / "s")
    assert len(result.bodies) == 1
    assert result.threemf_path.exists()
    assert result.bodies[0].color  # palette default applied


def test_missing_colors_use_palette(tmp_path: Path):
    result = build_and_export(MULTI_CODE, {}, tmp_path / "p")
    assert all(b.color.startswith("#") for b in result.bodies)
    assert result.bodies[0].color != result.bodies[1].color
