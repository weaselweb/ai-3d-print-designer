"""Build a multi-colour sign as separate coloured bodies (base / text / border /
icon / back). Each element is its own solid so it exports as a separate 3MF
object that maps to one ACE Pro filament slot.

Two styles:
- raised (default): text/border/icon sit extruded ON TOP of a solid plate.
- flat: text/border/icon are cut into a thin "front" layer and filled flush
  with it, for a flush inlay look instead of embossed lettering. A separate,
  uncut "back" slab sits behind that front layer in its own colour, so the
  inlay pattern doesn't show through to the other side.
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
    "text_mirror": True,  # flip if generated text reads backwards -- see the sign page
    "flat": False,
    "front_depth": 1.2,  # flat mode only: how deep the inlay layer is
    "back_color": "#1b3a5b",  # flat mode only: solid colour behind the inlay
    "border": True,
    "border_width": 3.0,
    "border_height": 1.6,
    "holes": False,
    "hole_diameter": 4.0,
    "hole_position": "sides",  # "sides" or "top" -- where the mounting/suction-cup holes sit
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


def _plate_slab(p: dict[str, Any], z0: float, z1: float) -> cq.Workplane:
    """A filleted plate-shaped slab spanning z0..z1, with mounting holes if
    enabled (over-extruded past both ends so it cuts cleanly through thin
    slabs too)."""
    w, h = p["plate_w"], p["plate_h"]
    height = z1 - z0
    plate = cq.Workplane("XY").rect(w, h).extrude(height).translate((0, 0, z0))
    r = min(p["corner_radius"], min(w, h) / 2 - 0.1)
    if r > 0:
        plate = plate.edges("|Z").fillet(r)
    if p.get("holes"):
        d = p["hole_diameter"]
        inset = max(d, p["corner_radius"]) + 2
        if p.get("hole_position") == "top":
            pts = [(-w / 4, h / 2 - inset), (w / 4, h / 2 - inset)]
        else:  # "sides" -- also what a suction cup hook clips through for wall/window hanging
            pts = [(-(w / 2 - inset), 0), (w / 2 - inset, 0)]
        holes = (
            cq.Workplane("XY").pushPoints(pts)
            .circle(d / 2).extrude(height + 2).translate((0, 0, z0 - 1))
        )
        plate = plate.cut(holes)
    return plate


def _base_plate(p: dict[str, Any]) -> cq.Workplane:
    return _plate_slab(p, 0.0, p["plate_thickness"])


def _text_shape(p: dict[str, Any], z0: float, height: float) -> cq.Workplane | None:
    text = str(p["text"]).strip()
    if not text:
        return None
    shape = cq.Workplane("XY").text(text, p["text_size"], height)
    if p.get("text_mirror", True):
        shape = shape.mirror("YZ")
    return shape.translate((0, 0, z0))


def _border_shape(p: dict[str, Any], z0: float, height: float) -> cq.Workplane | None:
    if not p.get("border"):
        return None
    w, h = p["plate_w"], p["plate_h"]
    bw = p["border_width"]
    if w - 2 * bw <= 1 or h - 2 * bw <= 1:
        return None
    shape = cq.Workplane("XY").rect(w, h).rect(w - 2 * bw, h - 2 * bw).extrude(height)
    return shape.translate((0, 0, z0))


def _icon_shape(p: dict[str, Any], z0: float, height: float) -> cq.Workplane | None:
    fn = ICONS.get(str(p.get("icon", "")).strip())
    if fn is None:
        return None
    shape = fn(p["icon_size"], height)
    return shape.translate((p.get("icon_x", 0.0), p.get("icon_y", 0.0), z0))


def build_bodies(params: dict[str, Any]) -> list[Body]:
    p = {**DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
    t = p["plate_thickness"]
    flat = bool(p.get("flat"))

    if flat:
        front_depth = min(p["front_depth"], max(t - 0.8, 0.2))
        back_h = t - front_depth
        text_shape = _text_shape(p, back_h, front_depth)
        border_shape = _border_shape(p, back_h, front_depth)
        icon_shape = _icon_shape(p, back_h, front_depth)

        back = _plate_slab(p, 0.0, back_h)
        front_bg = _plate_slab(p, back_h, t)
        for shape in (text_shape, border_shape, icon_shape):
            if shape is not None:
                front_bg = front_bg.cut(shape)

        bodies: list[Body] = [
            Body("back", _to_mesh(back), p["back_color"]),
            Body("base", _to_mesh(front_bg), p["base_color"]),
        ]
    else:
        text_shape = _text_shape(p, t, p["text_height"])
        border_shape = _border_shape(p, t, p["border_height"])
        icon_shape = _icon_shape(p, t, p["icon_height"])
        bodies = [Body("base", _to_mesh(_base_plate(p)), p["base_color"])]

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
