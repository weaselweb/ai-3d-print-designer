"""Write a STANDARD multi-body, multi-colour 3MF.

Anycubic Slicer Next (OrcaSlicer-based) reads the standard 3MF core spec —
`<basematerials>` colours and one `<object>` per body — but NOT Bambu's
proprietary paint format. So we emit exactly that: each colour is a base
material, each part is its own object referencing a material, and the build
lists every object. Opened in Slicer Next, each body is separate and maps to an
ACE Pro filament slot.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import trimesh

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" \
Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""

_MODEL_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


@dataclass
class Body:
    name: str
    mesh: trimesh.Trimesh
    color: str  # "#RRGGBB"


def _norm_color(c: str) -> str:
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) == 6:
        c += "FF"  # add opaque alpha
    return "#" + c.upper()


def _mesh_xml(mesh: trimesh.Trimesh) -> str:
    v = mesh.vertices
    f = mesh.faces
    verts = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in v)
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
    return f"<mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh>"


def build_model_xml(bodies: list[Body]) -> str:
    bases = "".join(
        f'<base name="{b.name}" displaycolor="{_norm_color(b.color)}"/>' for b in bodies
    )
    objects, items = [], []
    for i, b in enumerate(bodies):
        oid = i + 2  # 1 is reserved for the basematerials group
        objects.append(
            f'<object id="{oid}" type="model" pid="1" pindex="{i}" name="{b.name}">'
            f"{_mesh_xml(b.mesh)}</object>"
        )
        items.append(f'<item objectid="{oid}"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{_MODEL_NS}">'
        f'<resources><basematerials id="1">{bases}</basematerials>'
        f'{"".join(objects)}</resources>'
        f'<build>{"".join(items)}</build></model>'
    )


def write_3mf(path: Path, bodies: list[Body]) -> Path:
    if not bodies:
        raise ValueError("A 3MF needs at least one body.")
    path.parent.mkdir(parents=True, exist_ok=True)
    model = build_model_xml(bodies)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", model)
    return path
