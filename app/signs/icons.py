"""A small library of parametric icon shapes for signs, built from plain
CadQuery primitives (polygons, circles) so they render cleanly and
consistently -- instead of asking the AI to sketch a one-off icon in
freehand CadQuery every time, which is where the wobbly/mirrored results
came from.

Every icon is centred on the origin, sits in the XY plane at z=0..height,
and reads correctly viewed from +Z looking down (the same convention the
sign builder uses for everything else).
"""
from __future__ import annotations

import math

import cadquery as cq


def _polygon(points: list[tuple[float, float]], height: float) -> cq.Workplane:
    wp = cq.Workplane("XY").moveTo(*points[0])
    for x, y in points[1:]:
        wp = wp.lineTo(x, y)
    return wp.close().extrude(height)


def warning_triangle(size: float, height: float) -> cq.Workplane:
    """Outlined triangle with a bold exclamation mark inside."""
    tri_h = size * math.sqrt(3) / 2
    outer = [(-size / 2, -tri_h / 3), (size / 2, -tri_h / 3), (0, 2 * tri_h / 3)]
    inner = [(x * 0.72, y * 0.72 + tri_h * 0.06) for x, y in outer]
    ring = _polygon(outer, height).cut(_polygon(inner, height))

    bar_w, bar_h = size * 0.09, tri_h * 0.32
    bar = cq.Workplane("XY").center(0, tri_h * 0.06).rect(bar_w, bar_h).extrude(height)
    dot = cq.Workplane("XY").center(0, -tri_h * 0.22).circle(bar_w * 0.65).extrude(height)
    return ring.union(bar).union(dot)


def radiation(size: float, height: float) -> cq.Workplane:
    """Classic three-blade radiation trefoil."""
    r_center = size * 0.12
    r_gap = size * 0.22
    r_blade = size * 0.5
    half_angle = 50

    result = cq.Workplane("XY").circle(r_center).extrude(height)
    steps = 12
    for i in range(3):
        a0, a1 = i * 120 - half_angle, i * 120 + half_angle
        pts = [(0.0, 0.0)]
        for s in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * s / steps)
            pts.append((r_blade * math.cos(a), r_blade * math.sin(a)))
        blade = _polygon(pts, height).cut(cq.Workplane("XY").circle(r_gap).extrude(height))
        result = result.union(blade)
    return result


def star(size: float, height: float, points_n: int = 5) -> cq.Workplane:
    r_outer, r_inner = size / 2, size / 2 * 0.38
    pts = []
    for i in range(points_n * 2):
        r = r_outer if i % 2 == 0 else r_inner
        a = math.radians(90 + i * 360 / (points_n * 2))
        pts.append((r * math.cos(a), r * math.sin(a)))
    return _polygon(pts, height)


def arrow(size: float, height: float) -> cq.Workplane:
    """Points up (+Y)."""
    w, h = size, size
    pts = [
        (0, h / 2), (w * 0.35, h * 0.05), (w * 0.15, h * 0.05),
        (w * 0.15, -h / 2), (-w * 0.15, -h / 2), (-w * 0.15, h * 0.05),
        (-w * 0.35, h * 0.05),
    ]
    return _polygon(pts, height)


def exclamation(size: float, height: float) -> cq.Workplane:
    bar_w, bar_h = size * 0.22, size * 0.62
    bar = cq.Workplane("XY").center(0, size * 0.16).rect(bar_w, bar_h).extrude(height)
    dot = cq.Workplane("XY").center(0, -size * 0.34).circle(bar_w * 0.6).extrude(height)
    return bar.union(dot)


def skull(size: float, height: float) -> cq.Workplane:
    """A simple, stylised skull -- cranium + eyes + nose + a few teeth gaps."""
    r = size * 0.42
    cranium = cq.Workplane("XY").circle(r).extrude(height)
    jaw = cq.Workplane("XY").center(0, -r * 0.55).rect(r * 1.3, r * 0.7).extrude(height)
    base = cranium.union(jaw)

    eye_r = r * 0.22
    eyes = (
        cq.Workplane("XY")
        .pushPoints([(-r * 0.42, r * 0.05), (r * 0.42, r * 0.05)])
        .circle(eye_r)
        .extrude(height)
    )
    nose = _polygon(
        [(-eye_r * 0.5, -r * 0.35 + eye_r * 0.6),
         (eye_r * 0.5, -r * 0.35 + eye_r * 0.6),
         (0, -r * 0.35 - eye_r * 0.4)],
        height,
    )
    n_gaps = 3
    xs = [-r * 0.45 + i * (r * 0.9 / (n_gaps - 1)) for i in range(n_gaps)]
    teeth_gaps = (
        cq.Workplane("XY").pushPoints([(x, -r * 0.75) for x in xs])
        .rect(r * 0.18, r * 0.35).extrude(height)
    )
    return base.cut(eyes).cut(nose).cut(teeth_gaps)


ICONS = {
    "radiation": radiation,
    "warning_triangle": warning_triangle,
    "skull": skull,
    "star": star,
    "arrow": arrow,
    "exclamation": exclamation,
}
