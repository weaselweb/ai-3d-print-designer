"""AI sign design: prompt -> structured parameters for the deterministic sign
builder (app/signs/builder.py), instead of freehand CadQuery. Freehand
per-generation text/icon code was unreliable (mirrored text, rough icon
sketches); this engine is deterministic, tested, and already correctly
oriented -- the AI just picks values for it.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from ..signs.builder import DEFAULTS
from ..signs.icons import ICONS

_ICON_NAMES = ", ".join(sorted(ICONS))

SYSTEM_PROMPT = f"""\
You design multi-colour, 3D-printable signs. You always return a single JSON
object and nothing else, matching this exact schema (all fields optional --
omit any you want left at their default):

{{
  "text": "<sign text, keep it short>",
  "plate_w": <mm>, "plate_h": <mm>, "plate_thickness": <mm>, "corner_radius": <mm>,
  "text_size": <mm>, "text_height": <mm>,
  "flat": <true for a flush single-height inlay look, false (default) for raised/embossed text>,
  "border": <true/false>, "border_width": <mm>, "border_height": <mm>,
  "holes": <true/false, mounting holes>, "hole_diameter": <mm>,
  "icon": "<one of: {_ICON_NAMES}, or \\"\\" for none>",
  "icon_size": <mm>, "icon_x": <mm from centre>, "icon_y": <mm from centre>,
  "base_color": "#RRGGBB", "text_color": "#RRGGBB", "border_color": "#RRGGBB",
  "icon_color": "#RRGGBB"
}}

Rules:
- "icon" MUST be one of the exact names listed above, or empty. Never invent a
  new icon name -- pick the closest match, or leave it empty.
- Position the icon (icon_x/icon_y) so it doesn't overlap the text -- e.g. an
  icon above the text (positive icon_y) with text nearer the plate centre.
- Size the plate to comfortably fit the text at a readable size.
- Pick colours that suit the sign's tone (e.g. yellow/black for a warning
  sign, playful colours for a joke sign).
"""


class SignGenerationError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SignGenerationError(f"Model did not return valid JSON: {exc}") from exc


def generate_sign_params(prompt: str) -> dict[str, Any]:
    if not settings.anthropic_api_key:
        raise SignGenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env to use AI sign generation "
            "(the form builder on the home page works without a key)."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    payload = _extract_json(text)

    icon = str(payload.get("icon", "")).strip()
    if icon and icon not in ICONS:
        icon = ""
    params = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in payload and payload[key] is not None:
            params[key] = payload[key]
    params["icon"] = icon
    return params
