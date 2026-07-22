"""Build a multi-colour sign as separate coloured bodies (base / text / border).

Each element is its own solid so it exports as a separate 3MF object that maps
to one ACE Pro filament slot.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import cadquery as cq
import trimesh

from .threemf import Body

DEFAULTS: dict[str, Any] = {
    "text": "HELLO",
    "plate_w": 100.0,
    "plate_h": 40.0,
    "plate_thickness": 3.0,
    "corner_radius": 4.0,
    "text_size": 16.0,
    "text_height": 1.6,
    "border": True,
    "border_width": 3.0,
    "border_height": 1.6,
    "holes": False,
    "hole_diameter": 4.0,
    "base_color": "#1b3a5b",
    "text_color": "#f4d35e",
    "border_color": "#e0e0e0",
}


def _to_mesh(obj: cq.Workplane) -> trimesh.Trimesh:
    path = tempfile.mktemp(suffix=".stl")
    try:
        cq.exporters.export(obj, path, exportType="STL")
        return trimesh.load(path, force="mesh")
    finally:
        if os.path.exists(path):
            os.remove(path)


def _base_plate(p: dict[str, Any]) -> cq.Workplane:
    w, h, t = p["plate_w"], p["plate_h"], p["plate_thickness"]
    plate = cq.Workplane("XY").rect(w, h).extrude(t)  # bottom at z=0
    r = min(p["corner_radius"], min(w, h) / 2 - 0.1)
    if r > 0:
        plate = plate.edges("|Z").fillet(r)
    if p.get("holes"):
        d = p["hole_diameter"]
        x = w / 2 - max(d, p["corner_radius"]) - 2
        holes = (
            cq.Workplane("XY").pushPoints([(-x, 0), (x, 0)])
            .circle(d / 2).extrude(t + 2).translate((0, 0, -1))
        )
        plate = plate.cut(holes)
    return plate


def build_bodies(params: dict[str, Any]) -> list[Body]:
    p = {**DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
    bodies: list[Body] = []

    bodies.append(Body("base", _to_mesh(_base_plate(p)), p["base_color"]))

    text = str(p["text"]).strip()
    if text:
        txt = (cq.Workplane("XY").workplane(offset=p["plate_thickness"])
               .text(text, p["text_size"], p["text_height"])
               .mirror("YZ"))
        mesh = _to_mesh(txt)
        if len(mesh.faces) > 0:
            bodies.append(Body("text", mesh, p["text_color"]))

    if p.get("border"):
        w, h, t = p["plate_w"], p["plate_h"], p["plate_thickness"]
        bw, bh = p["border_width"], p["border_height"]
        if w - 2 * bw > 1 and h - 2 * bw > 1:
            frame = (cq.Workplane("XY").workplane(offset=t)
                     .rect(w, h).rect(w - 2 * bw, h - 2 * bw).extrude(bh))
            bodies.append(Body("border", _to_mesh(frame), p["border_color"]))

    return bodies
