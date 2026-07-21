"""Phase 4: sign geometry, standard 3MF writer, and the sign routes (no API key)."""
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.signs.builder import DEFAULTS, build_bodies  # noqa: E402
from app.signs.threemf import Body, build_model_xml, write_3mf  # noqa: E402

client = TestClient(app)
_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


def test_build_bodies_makes_separate_coloured_parts():
    bodies = build_bodies(DEFAULTS)
    names = [b.name for b in bodies]
    assert names == ["base", "text", "border"]  # default has all three
    assert len({b.color for b in bodies}) == 3
    for b in bodies:
        assert len(b.mesh.faces) > 0


def test_empty_text_drops_the_text_body():
    bodies = build_bodies({**DEFAULTS, "text": "   ", "border": False})
    assert [b.name for b in bodies] == ["base"]


def test_model_xml_has_materials_and_objects():
    bodies = build_bodies(DEFAULTS)
    xml = build_model_xml(bodies)
    root = ET.fromstring(xml)
    materials = root.findall(f".//{_NS}basematerials/{_NS}base")
    objects = root.findall(f".//{_NS}object")
    items = root.findall(f".//{_NS}build/{_NS}item")
    assert len(materials) == len(bodies)
    assert len(objects) == len(bodies)
    assert len(items) == len(bodies)
    # colours are #RRGGBBAA
    assert all(len(m.get("displaycolor")) == 9 for m in materials)


def test_write_3mf_is_a_valid_package(tmp_path: Path):
    bodies = build_bodies({**DEFAULTS, "text": "AB"})
    out = write_3mf(tmp_path / "sign.3mf", bodies)
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "[Content_Types].xml" in names
        assert "_rels/.rels" in names
        assert "3D/3dmodel.model" in names
        ET.fromstring(z.read("3D/3dmodel.model"))  # well-formed XML


def test_sign_routes_end_to_end():
    r = client.post("/signs/new", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    sign_id = loc.rsplit("/", 1)[-1]

    assert client.get(loc).status_code == 200

    tmf = client.get(f"/signs/{sign_id}/sign.3mf")
    assert tmf.status_code == 200 and len(tmf.content) > 0

    body0 = client.get(f"/signs/{sign_id}/body/0.stl")
    assert body0.status_code == 200 and len(body0.content) > 0

    # rebuild with new text/colours returns the preview partial
    rb = client.post(f"/signs/{sign_id}/rebuild",
                     data={"text": "YARD", "plate_w": "120", "plate_h": "50",
                           "plate_thickness": "3", "corner_radius": "4", "text_size": "18",
                           "text_height": "1.6", "border": "on", "border_width": "3",
                           "border_height": "1.6", "hole_diameter": "4",
                           "base_color": "#222222", "text_color": "#ffcc00", "border_color": "#ffffff"})
    assert rb.status_code == 200
    assert "3MF" in rb.text
