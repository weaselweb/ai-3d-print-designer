"""Phase 0 demo model: a parametric rounded box.

Uses the exact same `build(params)` contract the AI produces in Phase 1, so the
end-to-end pipeline (execute -> export -> preview -> download) is proven with no
API key required.
"""
from __future__ import annotations

DEMO_CODE = '''\
import cadquery as cq


def build(params):
    length = params["length"]
    width = params["width"]
    height = params["height"]
    fillet = params["fillet"]
    result = cq.Workplane("XY").box(length, width, height)
    if fillet > 0:
        result = result.edges("|Z").fillet(min(fillet, min(length, width) / 2 - 0.1))
    return result
'''

DEMO_PARAMETERS = [
    {"name": "length", "label": "Length (mm)", "value": 60, "min": 10, "max": 200, "step": 1},
    {"name": "width", "label": "Width (mm)", "value": 40, "min": 10, "max": 200, "step": 1},
    {"name": "height", "label": "Height (mm)", "value": 20, "min": 2, "max": 100, "step": 1},
    {"name": "fillet", "label": "Corner radius (mm)", "value": 4, "min": 0, "max": 20, "step": 0.5},
]
