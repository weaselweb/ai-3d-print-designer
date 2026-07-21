"""Build a sign's files: a standard multi-colour 3MF plus per-body STLs for the
coloured web preview."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import settings
from .builder import build_bodies
from .threemf import write_3mf


@dataclass
class SignManifest:
    bodies: list[dict] = field(default_factory=list)  # {index, name, color, stl_url}
    threemf_url: str = ""
    dims_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    color_count: int = 0


def _dir(sign_id: str) -> Path:
    return settings.generated_dir / "signs" / sign_id


def threemf_path(sign_id: str) -> Path:
    return _dir(sign_id) / "sign.3mf"


def body_stl_path(sign_id: str, index: int) -> Path:
    return _dir(sign_id) / f"body_{index}.stl"


def build_sign(sign_id: str, params: dict[str, Any]) -> SignManifest:
    bodies = build_bodies(params)
    out = _dir(sign_id)
    out.mkdir(parents=True, exist_ok=True)

    write_3mf(threemf_path(sign_id), bodies)

    manifest = SignManifest(threemf_url=f"/signs/{sign_id}/sign.3mf", color_count=len(bodies))
    import trimesh

    combined = trimesh.util.concatenate([b.mesh for b in bodies]) if bodies else None
    if combined is not None:
        ext = combined.extents
        manifest.dims_mm = (round(float(ext[0]), 1), round(float(ext[1]), 1), round(float(ext[2]), 1))

    for i, b in enumerate(bodies):
        b.mesh.export(str(body_stl_path(sign_id, i)))
        manifest.bodies.append(
            {"index": i, "name": b.name, "color": b.color, "stl_url": f"/signs/{sign_id}/body/{i}.stl"}
        )
    return manifest
