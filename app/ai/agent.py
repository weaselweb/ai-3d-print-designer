"""Printability refinement agent.

A bounded loop that uses the print-readiness analyzer as a verifier: build the
design, analyse it, and if it has *blocking* printability problems, hand the
specific issues back to the model to fix — repeat until it passes or the step
budget runs out. This turns the analyzer from a passive report into a control
signal, without letting the model spin unbounded.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..cad.executor import build_and_export
from ..print_check.analyze import PrintReadiness, analyze
from ..print_check.profile import PrinterProfile
from .generator import GeneratedDesign, default_params, revise_design

# Structural problems the agent must resolve; overhang/orientation are advisory
# (supports are an acceptable answer) so they never block, only inform.
BLOCKING = {"Watertight", "Wall thickness", "Feature size"}

MAX_ITERS = 4


@dataclass
class Issue:
    name: str
    severity: str  # warn | fail
    detail: str


@dataclass
class AgentStep:
    iteration: int
    action: str          # analysed | revising | passed | budget-exhausted
    issues: list[str] = field(default_factory=list)


@dataclass
class AgentOutcome:
    design: GeneratedDesign
    steps: list[AgentStep] = field(default_factory=list)
    passed: bool = False
    iterations: int = 0

    def log(self) -> list[dict]:
        return [{"iteration": s.iteration, "action": s.action, "issues": s.issues} for s in self.steps]


def actionable_issues(readiness: PrintReadiness) -> list[Issue]:
    return [Issue(c.name, c.status, c.detail) for c in readiness.checks if c.status in ("warn", "fail")]


def blocking_issues(readiness: PrintReadiness) -> list[Issue]:
    return [i for i in actionable_issues(readiness) if i.name in BLOCKING]


def build_and_analyze(design: GeneratedDesign, profile: PrinterProfile) -> PrintReadiness:
    """Build the design in a scratch dir and analyse it (no persistence)."""
    params = default_params(design)
    colors = {b["name"]: b.get("color") for b in design.bodies if "name" in b}
    scratch = Path(tempfile.mkdtemp()) / "model"
    result = build_and_export(design.code, params, scratch, colors)
    return analyze(result.stl_path, profile, repaired_out=scratch.parent / "rep.stl")


def _run_loop(
    design: GeneratedDesign,
    analyze_fn: Callable[[GeneratedDesign], PrintReadiness],
    revise_fn: Callable[[GeneratedDesign, list[Issue]], GeneratedDesign],
    max_iters: int = MAX_ITERS,
) -> AgentOutcome:
    outcome = AgentOutcome(design=design)
    for it in range(1, max_iters + 1):
        outcome.iterations = it
        readiness = analyze_fn(design)
        blocking = blocking_issues(readiness)
        if not blocking:
            remaining = [i.detail for i in actionable_issues(readiness)]
            outcome.steps.append(AgentStep(it, "passed", remaining))
            outcome.design, outcome.passed = design, True
            return outcome
        if it == max_iters:
            outcome.steps.append(AgentStep(it, "budget-exhausted", [i.detail for i in blocking]))
            outcome.design = design
            return outcome
        outcome.steps.append(AgentStep(it, "revising", [i.detail for i in blocking]))
        design = revise_fn(design, blocking)
    outcome.design = design
    return outcome


def refine_for_printability(
    initial: GeneratedDesign, profile: dict, max_iters: int = MAX_ITERS
) -> AgentOutcome:
    prof = PrinterProfile(
        nozzle_diameter=profile["nozzle_diameter"],
        layer_height=profile["layer_height"],
        overhang_threshold_deg=profile["overhang_threshold_deg"],
        default_clearance=profile["default_clearance"],
    )
    return _run_loop(
        initial,
        lambda d: build_and_analyze(d, prof),
        lambda d, issues: revise_design(d, [i.detail for i in issues], profile),
        max_iters,
    )
