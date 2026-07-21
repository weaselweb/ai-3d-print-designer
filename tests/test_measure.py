"""Phase 3: scale math, reference library, and the capture routes (no API key)."""
import base64
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.measure import references, scale  # noqa: E402

client = TestClient(app)

# 1x1 transparent PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_scale_calibration_and_measure():
    # An 85.6 mm reference spanning 856 px -> 0.1 mm/px.
    mpp = scale.mm_per_px(85.6, (0, 0), (856, 0))
    assert mpp == pytest.approx(0.1)
    # A 300 px segment is then 30 mm.
    assert scale.measure_mm((0, 0), (0, 300), mpp) == pytest.approx(30.0)


def test_scale_rejects_bad_input():
    with pytest.raises(ValueError):
        scale.mm_per_px(0, (0, 0), (10, 0))
    with pytest.raises(ValueError):
        scale.mm_per_px(50, (5, 5), (5, 5))


def test_reference_library():
    assert references.default_reference()["id"] == "card_id1"
    assert references.by_id("coin_us_quarter")["mm"] == 24.26
    assert references.by_id("nope") is None
    # every entry has the fields the UI needs
    for r in references.REFERENCE_OBJECTS:
        assert {"id", "label", "mm", "measure", "group"} <= set(r)


def test_capture_upload_and_measure_page():
    r = client.post("/capture/upload",
                    files={"photo": ("part.png", _PNG, "image/png")},
                    follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    cid = loc.rsplit("/", 1)[-1]

    page = client.get(loc)
    assert page.status_code == 200
    assert "Reference object" in page.text
    assert "ID-1 card" in page.text  # library rendered

    assert client.get(f"/capture/{cid}/image").status_code == 200


def test_capture_upload_rejects_non_image():
    r = client.post("/capture/upload",
                    files={"photo": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_build_without_key_reports_error():
    r = client.post("/capture/upload",
                    files={"photo": ("part.png", _PNG, "image/png")},
                    follow_redirects=False)
    cid = r.headers["location"].rsplit("/", 1)[-1]
    resp = client.post(f"/capture/{cid}/build",
                       json={"reference_label": "ID-1 card", "reference_mm": 85.6,
                             "mm_per_px": 0.1, "measurements": [{"name": "len", "mm": 40}],
                             "description": "a bracket"})
    assert resp.status_code == 400
    assert "ANTHROPIC_API_KEY" in resp.json()["error"]
