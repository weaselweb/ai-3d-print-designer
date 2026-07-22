"""Sign icons, rendered from Font Awesome 6 Free (Solid) glyphs via CadQuery's
text() -- real, professionally-drawn pictograms instead of hand-sketched
polygons. Installed into the image at
/usr/share/fonts/opentype/fontawesome/fa6-solid.otf (see Dockerfile).

Codepoints are taken from Font Awesome 6's own icon metadata (via
https://github.com/pyapp-kit/fonticon-fontawesome6), not guessed.
"""
from __future__ import annotations

import cadquery as cq

_FA6_SOLID = "/usr/share/fonts/opentype/fontawesome/fa6-solid.otf"

_GLYPHS = {
    "radiation": chr(0xF7B9),
    "skull": chr(0xF54C),
    "warning_triangle": chr(0xF071),  # triangle-exclamation
    "star": chr(0xF005),
    "arrow": chr(0xF062),  # arrow-up
    "exclamation": chr(0xF06A),  # circle-exclamation
}


def _fa6_icon(glyph: str):
    def build(size: float, height: float, mirror: bool = True) -> cq.Workplane:
        shape = cq.Workplane("XY").text(
            glyph, size, height, fontPath=_FA6_SOLID, halign="center", valign="center",
        )
        return shape.mirror("YZ") if mirror else shape

    return build


ICONS = {name: _fa6_icon(glyph) for name, glyph in _GLYPHS.items()}
