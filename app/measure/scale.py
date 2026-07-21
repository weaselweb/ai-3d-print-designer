"""Pure scale/measurement math for the reference-object workflow."""
from __future__ import annotations

import math

Point = tuple[float, float]


def pixel_distance(p1: Point, p2: Point) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def mm_per_px(reference_mm: float, p1: Point, p2: Point) -> float:
    """Calibrate scale from a reference of known length clicked at p1..p2."""
    if reference_mm <= 0:
        raise ValueError("Reference length must be greater than 0 mm.")
    px = pixel_distance(p1, p2)
    if px <= 0:
        raise ValueError("The two reference points must be different.")
    return reference_mm / px


def measure_mm(p1: Point, p2: Point, mm_per_px_value: float) -> float:
    """Real-world length of a clicked segment, in mm."""
    return round(pixel_distance(p1, p2) * mm_per_px_value, 2)


def accuracy_hint(reference_px: float, image_diag_px: float) -> str:
    """Rough guidance: a bigger reference relative to the frame = less error."""
    if image_diag_px <= 0 or reference_px <= 0:
        return "unknown"
    frac = reference_px / image_diag_px
    if frac < 0.15:
        return "low — the reference is small in frame; move it closer or crop tighter"
    if frac < 0.30:
        return "ok — usable, but a larger reference improves accuracy"
    return "good"
