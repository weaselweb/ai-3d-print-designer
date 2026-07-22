"""Build a multi-colour sign as separate coloured bodies (base / text / border /
icon). Each element is its own solid so it exports as a separate 3MF object
that maps to one ACE Pro filament slot.

Two styles:
- raised (default): text/border/icon sit extruded ON TOP of a solid plate.
- flat: the plate has the text/border/icon shapes cut out of it, and those
  same shapes fill the gaps at full plate thickness -- a flush, single-height
  inlay look instead of embossed lettering.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import cadquery as cq
import trimesh

from .icons import ICONS
from .threemf import Body

DEFAULTS: dict[str, Any] = {
    "text": "HELLO",
    "plate_w": 100.0,
    "plate_h": 40.0,
    "plate_thickness": 3.0,
    "corner_radius": 4.0,
    "text_size": 16.0,
    "text_height": 1.6,
    "flat": False,
    "border": True,
    "border_width": 3.0,
    "border_height": 1.6,
    "holes": False,
    "hole_diameter": 4.0,
    "icon": "",
    "icon_size": 20.0,
    "icon_height": 1.6,
    "icon_x": 0.0,
    "icon_y": 10.0,
    "base_color": "#1b3a5b",
    "text_color": "#f4d35e",
    "border_color": "#e0e0e0",
    "icon_color": "#f4d35e",
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


def _text_shape(p: dict[str, Any]) -> cq.Workplane | None:
    text = str(p["text"]).strip()
    if not text:
        return None
    t = p["plate_thickness"]
    flat = bool(p.get("flat"))
    shape = cq.Workplane("XY").text(text, p["text_size"], t if flat else p["text_height"]).mirror("YZ")
    return shape if flat else shape.translate((0, 0, t))


def _border_shape(p: dict[str, Any]) -> cq.Workplane | None:
    if not p.get("border"):
        return None
    w, h, t = p["plate_w"], p["plate_h"], p["plate_thickness"]
    bw = p["border_width"]
    if w - 2 * bw <= 1 or h - 2 * bw <= 1:
        return None
    flat = bool(p.get("flat"))
    shape = cq.Workplane("XY").rect(w, h).rect(w - 2 * bw, h - 2 * bw).extrude(t if flat else p["border_height"])
    return shape if flat else shape.translate((0, 0, t))


def _icon_shape(p: dict[str, Any]) -> cq.Workplane | None:
    fn = ICONS.get(str(p.get("icon", "")).strip())
    if fn is None:
        return None
    t = p["plate_thickness"]
    flat = bool(p.get("flat"))
    shape = fn(p["icon_size"], t if flat else p["icon_height"])
    shape = shape.translate((p.get("icon_x", 0.0), p.get("icon_y", 0.0), 0 if flat else t))
    return shape


def build_bodies(params: dict[str, Any]) -> list[Body]:
    p = {**DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
    flat = bool(p.get("flat"))

    plate = _base_plate(p)
    text_shape = _text_shape(p)
    border_shape = _border_shape(p)
    icon_shape = _icon_shape(p)

    if flat:
        for shape in (text_shape, border_shape, icon_shape):
            if shape is not None:
                plate = plate.cut(shape)

    bodies: list[Body] = [Body("base", _to_mesh(plate), p["base_color"])]

    if text_shape is not None:
        mesh = _to_mesh(text_shape)
        if len(mesh.faces) > 0:
            bodies.append(Body("text", mesh, p["text_color"]))
    if border_shape is not None:
        bodies.append(Body("border", _to_mesh(border_shape), p["border_color"]))
    if icon_shape is not None:
        mesh = _to_mesh(icon_shape)
        if len(mesh.faces) > 0:
            bodies.append(Body("icon", mesh, p["icon_color"]))

    return bodies
