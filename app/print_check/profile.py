"""Printer profile + FDM tolerance/fit presets used by the readiness checks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PrinterProfile:
    nozzle_diameter: float = 0.4
    layer_height: float = 0.2
    overhang_threshold_deg: float = 45.0
    default_clearance: float = 0.2

    @property
    def min_wall(self) -> float:
        """A printable wall is ~2 extrusion widths. Extrusion width ≈ nozzle Ø."""
        return round(2 * self.nozzle_diameter, 3)

    @property
    def min_feature(self) -> float:
        """Smallest reliably printed feature ≈ one nozzle width."""
        return self.nozzle_diameter

    def as_dict(self) -> dict:
        return {
            "nozzle_diameter": self.nozzle_diameter,
            "layer_height": self.layer_height,
            "overhang_threshold_deg": self.overhang_threshold_deg,
            "default_clearance": self.default_clearance,
            "min_wall": self.min_wall,
            "min_feature": self.min_feature,
        }


# Per-side clearance recommendations for FDM at a 0.4 mm nozzle. These are the
# amount to *add to the hole* / *subtract from the pin* per side.
FIT_PRESETS: list[dict] = [
    {"name": "Press / interference", "clearance": 0.00,
     "use": "Permanent, needs force or heat to assemble."},
    {"name": "Snug / friction", "clearance": 0.10,
     "use": "Stays put by hand, e.g. press-in inserts, lids that grip."},
    {"name": "Normal / sliding", "clearance": 0.20,
     "use": "Assembles by hand, moves with light force. Good default."},
    {"name": "Free / loose running", "clearance": 0.35,
     "use": "Rotates/slides freely, e.g. hinges, axles, bearings."},
]
