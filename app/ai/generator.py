"""Orchestrates: text prompt -> Claude -> parametric CadQuery -> validated build.

On a failed build we feed the error back to the model once for a self-repair
retry before giving up.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..config import settings
from ..cad.executor import CadExecutionError, run_build
from ..cad.validate import UnsafeCodeError
from .prompts import REPAIR_PROMPT, SYSTEM_PROMPT


@dataclass
class GeneratedDesign:
    name: str
    description: str
    parameters: list[dict[str, Any]]
    code: str


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
        return GeneratedDesign(
            name=str(payload["name"]).strip() or "part",
            description=str(payload.get("description", "")).strip(),
            parameters=list(payload.get("parameters", [])),
            code=str(payload["code"]),
        )
    except KeyError as exc:
        raise GenerationError(f"Model JSON missing field: {exc}") from exc


def _default_params(design: GeneratedDesign) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in design.parameters if "name" in p and "value" in p}


def _call_claude(messages: list[dict[str, str]]) -> str:
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
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def generate(prompt: str) -> GeneratedDesign:
    """Generate a parametric design and verify it actually builds (one retry)."""
    messages = [{"role": "user", "content": prompt}]
    design = _to_design(_extract_json(_call_claude(messages)))

    try:
        run_build(design.code, _default_params(design))
        return design
    except (CadExecutionError, UnsafeCodeError) as exc:
        # Self-repair: hand the error back to the model once.
        repair = REPAIR_PROMPT.format(error=str(exc), code=design.code)
        messages.append({"role": "user", "content": repair})
        design = _to_design(_extract_json(_call_claude(messages)))
        try:
            run_build(design.code, _default_params(design))
        except (CadExecutionError, UnsafeCodeError) as exc2:
            raise GenerationError(f"Model could not produce buildable code: {exc2}") from exc2
        return design
