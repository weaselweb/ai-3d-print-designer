"""App smoke tests: boot, demo pipeline, download, health — no API key needed."""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_home_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert "AI 3D Print Designer" in r.text


def test_health():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_demo_pipeline_and_download():
    # create demo -> redirect to /design/{id}
    r = client.post("/demo", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    design_id = loc.rsplit("/", 1)[-1]

    assert client.get(loc).status_code == 200

    stl = client.get(f"/design/{design_id}/model.stl")
    assert stl.status_code == 200
    assert len(stl.content) > 0


def test_rebuild_changes_params():
    r = client.post("/demo", follow_redirects=False)
    design_id = r.headers["location"].rsplit("/", 1)[-1]
    r2 = client.post(f"/design/{design_id}/rebuild",
                     data={"length": "120", "width": "40", "height": "20", "fillet": "4"})
    assert r2.status_code == 200
    assert "120" in r2.text  # bbox reflects new length
