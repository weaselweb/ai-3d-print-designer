"""Orchestrates: text prompt -> Claude -> parametric CadQuery -> validated build.

On a failed build we feed the error back to the model once for a self-repair
retry before giving up.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import settings
from ..cad.executor import CadExecutionError, run_build
from ..cad.validate import UnsafeCodeError
from .prompts import REPAIR_PROMPT, reconstruct_system_prompt, system_prompt

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


@dataclass
class GeneratedDesign:
    name: str
    description: str
    parameters: list[dict[str, Any]]
    code: str
    bodies: list[dict[str, Any]]


class GenerationError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Tolerate ```json fences or stray prose around the object.
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
        raise GenerationError(f"Model did not return valid JSON: {exc}") from exc


def _to_design(payload: dict[str, Any]) -> GeneratedDesign:
    try:
        bodies = list(payload.get("bodies") or [{"name": "body", "color": "#3b82f6"}])
        return GeneratedDesign(
            name=str(payload["name"]).strip() or "part",
            description=str(payload.get("description", "")).strip(),
            parameters=list(payload.get("parameters", [])),
            code=str(payload["code"]),
            bodies=bodies,
        )
    except KeyError as exc:
        raise GenerationError(f"Model JSON missing field: {exc}") from exc


def _default_params(design: GeneratedDesign) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in design.parameters if "name" in p and "value" in p}


def _call_claude(messages: list[dict[str, str]], system: str) -> str:
    if not settings.anthropic_api_key:
        raise GenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env to use AI generation "
            "(the demo model on the home page works without a key)."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=system,
        messages=messages,
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def _generate_verified(messages: list[dict[str, Any]], system: str) -> GeneratedDesign:
    """Call the model, then verify the code builds — one self-repair retry on failure."""
    design = _to_design(_extract_json(_call_claude(messages, system)))
    try:
        run_build(design.code, _default_params(design))
        return design
    except (CadExecutionError, UnsafeCodeError) as exc:
        repair = REPAIR_PROMPT.format(error=str(exc), code=design.code)
        messages.append({"role": "user", "content": repair})
        design = _to_design(_extract_json(_call_claude(messages, system)))
        try:
            run_build(design.code, _default_params(design))
        except (CadExecutionError, UnsafeCodeError) as exc2:
            raise GenerationError(f"Model could not produce buildable code: {exc2}") from exc2
        return design


def generate(prompt: str, profile: dict | None = None) -> GeneratedDesign:
    """Text prompt -> verified parametric design."""
    messages = [{"role": "user", "content": prompt}]
    return _generate_verified(messages, system_prompt(profile))


def default_params(design: GeneratedDesign) -> dict[str, Any]:
    return _default_params(design)


def revise_design(
    design: GeneratedDesign, issues: list[str], profile: dict | None = None
) -> GeneratedDesign:
    """Ask the model to fix specific printability problems; verify it still builds."""
    import json as _json

    from .prompts import REFINE_PROMPT

    msg = REFINE_PROMPT.format(
        issues="\n".join(f"- {i}" for i in issues),
        params=_json.dumps(_default_params(design)),
        code=design.code,
    )
    messages = [{"role": "user", "content": msg}]
    return _generate_verified(messages, system_prompt(profile))


def _measurements_text(measurements: list[dict[str, Any]]) -> str:
    if not measurements:
        return "(no explicit measurements provided — infer scale from the photo)"
    return "\n".join(
        f"- {m.get('name', 'dimension')}: {m.get('mm')} mm" for m in measurements
    )


def generate_from_capture(
    description: str,
    measurements: list[dict[str, Any]],
    image_path: Path,
    profile: dict | None = None,
) -> GeneratedDesign:
    """Photo + calibrated measurements -> verified parametric reconstruction."""
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower(), "image/png")
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    text = (
        f"Reconstruct this part as a printable parametric model.\n\n"
        f"What it is / how it should work:\n{description or '(not specified)'}\n\n"
        f"Measured dimensions (authoritative):\n{_measurements_text(measurements)}"
    )
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        {"type": "text", "text": text},
    ]
    messages = [{"role": "user", "content": content}]
    return _generate_verified(messages, reconstruct_system_prompt(profile))
