"""Curated library of scale-reference objects with exact known dimensions.

The user picks one of these (or enters a custom object) and clicks its two
endpoints in the photo; that known length calibrates mm-per-pixel. A ruler or
calipers gives the best accuracy; the ID-1 card is the most convenient default
because it is standardised, flat, rigid, and has crisp straight edges.
"""
from __future__ import annotations

# `mm` is the length of the dimension named in `measure`, which the user clicks.
REFERENCE_OBJECTS: list[dict] = [
    {"id": "card_id1", "label": "ID-1 card (credit / bank / licence)", "mm": 85.60,
     "measure": "long edge", "group": "Cards", "default": True},
    {"id": "card_id1_short", "label": "ID-1 card — short edge", "mm": 53.98,
     "measure": "short edge", "group": "Cards"},

    {"id": "coin_us_quarter", "label": "US quarter", "mm": 24.26, "measure": "diameter", "group": "Coins"},
    {"id": "coin_us_penny", "label": "US penny (cent)", "mm": 19.05, "measure": "diameter", "group": "Coins"},
    {"id": "coin_us_nickel", "label": "US nickel", "mm": 21.21, "measure": "diameter", "group": "Coins"},
    {"id": "coin_us_dime", "label": "US dime", "mm": 17.91, "measure": "diameter", "group": "Coins"},
    {"id": "coin_eur_2", "label": "€2 coin", "mm": 25.75, "measure": "diameter", "group": "Coins"},
    {"id": "coin_eur_1", "label": "€1 coin", "mm": 23.25, "measure": "diameter", "group": "Coins"},
    {"id": "coin_gbp_2", "label": "£2 coin", "mm": 28.40, "measure": "diameter", "group": "Coins"},
    {"id": "coin_gbp_1", "label": "£1 coin", "mm": 23.43, "measure": "diameter", "group": "Coins"},

    {"id": "paper_a4_w", "label": "A4 paper — short side", "mm": 210.0, "measure": "width", "group": "Paper"},
    {"id": "paper_a4_h", "label": "A4 paper — long side", "mm": 297.0, "measure": "height", "group": "Paper"},
    {"id": "paper_letter_w", "label": "US Letter — short side", "mm": 215.9, "measure": "width", "group": "Paper"},

    {"id": "battery_aa_len", "label": "AA battery — length", "mm": 50.5, "measure": "length", "group": "Other"},
    {"id": "battery_aa_dia", "label": "AA battery — diameter", "mm": 14.5, "measure": "diameter", "group": "Other"},
    {"id": "lego_stud4", "label": "LEGO 4-stud pitch", "mm": 32.0, "measure": "4-stud span", "group": "Other"},

    {"id": "ruler_custom", "label": "Ruler / calipers (enter length)", "mm": 0.0,
     "measure": "chosen span", "group": "Best accuracy", "custom": True},
    {"id": "custom", "label": "Custom object (enter length)", "mm": 0.0,
     "measure": "known dimension", "group": "Custom", "custom": True},
]


def by_id(ref_id: str) -> dict | None:
    return next((r for r in REFERENCE_OBJECTS if r["id"] == ref_id), None)


def default_reference() -> dict:
    return next((r for r in REFERENCE_OBJECTS if r.get("default")), REFERENCE_OBJECTS[0])
