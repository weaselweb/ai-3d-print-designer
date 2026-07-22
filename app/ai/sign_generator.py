"""AI sign text: prompt -> a short phrase, nothing else. Layout, dimensions,
borders, icon, colours, and placement are left to the user via the sign
form -- letting the AI decide those too (an earlier version of this module
did) made freehand layout/colour choices that were often wrong and cost far
more tokens than generating text alone needs.
"""
from __future__ import annotations

from ..config import settings


class SignGenerationError(RuntimeError):
    pass


def generate_phrase(theme: str) -> str:
    if not settings.anthropic_api_key:
        raise SignGenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env to use AI sign text "
            "(the form builder on the home page works without a key)."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
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
