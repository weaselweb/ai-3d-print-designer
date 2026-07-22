"""Meshy text-to-3D: prompt -> printable mesh, for organic/figurine shapes that
parametric CadQuery can't sculpt (see PLAN.md's "mesh engine for organic jobs").

We only use "preview" mode and skip the texture "refine" pass — FDM printing
can't use colour texture anyway, and skipping it halves the wait and the
credits spent.
"""
from __future__ import annotations

import time

import httpx

from ..config import settings

BASE_URL = "https://api.meshy.ai/openapi/v2/text-to-3d"
_POLL_INTERVAL_S = 4.0


class MeshyError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.meshy_api_key:
        raise MeshyError(
            "MESHY_API_KEY is not set. Add it to .env to generate organic figures."
        )
    return {"Authorization": f"Bearer {settings.meshy_api_key}"}


def generate_stl(prompt: str, timeout_s: float = 300.0) -> bytes:
    """Submit a text-to-3D preview task, poll until done, return STL bytes."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            BASE_URL,
            headers=_headers(),
            json={
                "mode": "preview",
                "prompt": prompt,
                "target_formats": ["stl"],
                "origin_at": "bottom",
                "should_remesh": True,
                "target_polycount": 50000,
            },
        )
        if resp.status_code == 402:
            raise MeshyError("Meshy account has insufficient credits.")
        resp.raise_for_status()
        task_id = resp.json()["result"]

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(_POLL_INTERVAL_S)
            poll = client.get(f"{BASE_URL}/{task_id}", headers=_headers())
            poll.raise_for_status()
            data = poll.json()
            status = data.get("status")
            if status == "SUCCEEDED":
                stl_url = data["model_urls"]["stl"]
                mesh_resp = client.get(stl_url, timeout=60.0)
                mesh_resp.raise_for_status()
                return mesh_resp.content
            if status in ("FAILED", "CANCELED"):
                msg = (data.get("task_error") or {}).get("message") or "Meshy generation failed."
                raise MeshyError(msg)
        raise MeshyError("Timed out waiting for Meshy to finish generating the mesh.")
