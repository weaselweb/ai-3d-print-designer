"""AI sign generation, two tiers:

- generate_phrase: prompt -> just a short phrase. Cheap, used for "reroll
  text, keep design".
- generate_sign_design: prompt -> a full design (text, size, colours, icon,
  border/holes/flat toggles). Costs more tokens but lets the AI actually lay
  out the sign instead of you setting every field by hand. Every field it
  returns is validated/clamped before use -- the model's JSON is never
  trusted blindly.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings


class SignGenerationError(RuntimeError):
    pass


def _client():
    if not settings.anthropic_api_key:
        raise SignGenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env to use AI sign generation "
            "(the form builder on the sign page works without a key)."
        )
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def generate_phrase(theme: str) -> str:
    resp = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=60,
        system=(
            "Write ONE short, funny sign phrase in the theme/style of the user's "
            "message. Return ONLY the phrase text -- no quotes, no preamble, "
            "nothing else."
        ),
        messages=[{"role": "user", "content": theme}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text").strip().strip('"')
    if not text:
        raise SignGenerationError("Model returned an empty phrase.")
    return text


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _hex(value: Any, default: str) -> str:
    return value if isinstance(value, str) and _HEX_RE.match(value) else default


def _coerce_design(raw: dict[str, Any], icon_names: list[str]) -> dict[str, Any]:
    """Only known fields survive, each clamped to a sane range -- the model's
    JSON drives layout/colour choices but never raw dimensions/paths."""
    out: dict[str, Any] = {}
    text = str(raw.get("text") or "").strip()
    out["text"] = text[:40] if text else "HELLO"
    out["plate_w"] = _clamp(raw.get("plate_w"), 40, 250, 100.0)
    out["plate_h"] = _clamp(raw.get("plate_h"), 30, 200, 40.0)
    out["text_size"] = _clamp(raw.get("text_size"), 6, out["plate_h"] * 0.8, 16.0)
    out["border"] = bool(raw.get("border"))
    out["holes"] = bool(raw.get("holes"))
    out["hole_position"] = raw.get("hole_position") if raw.get("hole_position") in ("sides", "top") else "sides"
    out["flat"] = bool(raw.get("flat"))
    icon = str(raw.get("icon") or "").strip()
    out["icon"] = icon if icon in icon_names else ""
    out["base_color"] = _hex(raw.get("base_color"), "#1b3a5b")
    out["text_color"] = _hex(raw.get("text_color"), "#f4d35e")
    out["border_color"] = _hex(raw.get("border_color"), "#e0e0e0")
    out["icon_color"] = _hex(raw.get("icon_color"), "#f4d35e")
    out["back_color"] = _hex(raw.get("back_color"), "#1b3a5b")
    return out


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise SignGenerationError("Model response did not contain JSON.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise SignGenerationError(f"Model returned invalid JSON: {exc}") from exc


def generate_sign_design(theme: str, icon_names: list[str]) -> dict[str, Any]:
    system = (
        "You design a small multi-colour 3D-printed sign. Given the user's theme/request, "
        "respond with ONLY a JSON object (no markdown, no prose) with these fields:\n"
        '  "text": short sign phrase (<=40 chars)\n'
        '  "plate_w": plate width in mm, number 40-250\n'
        '  "plate_h": plate height in mm, number 30-200\n'
        '  "text_size": text height in mm, a bit less than plate_h\n'
        '  "border": true/false, whether to add a frame border\n'
        '  "holes": true/false, whether to add mounting/suction-cup holes\n'
        '  "hole_position": "sides" or "top"\n'
        '  "flat": true/false -- true for a flush inlay look, false for raised/embossed text\n'
        f'  "icon": one of {json.dumps(icon_names)}, or "" for none\n'
        '  "base_color", "text_color", "border_color", "icon_color", "back_color": '
        '"#rrggbb" hex strings that suit the theme\n'
        "Pick colours and an icon that actually fit the theme (e.g. a caution/radiation sign "
        "should look hazard-styled, a welcome sign should look friendly)."
    )
    resp = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": theme}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    raw = _extract_json(text)
    return _coerce_design(raw, icon_names)
