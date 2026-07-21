"""Phase 5: printability refinement agent — issue classification + bounded loop.

The loop is exercised with the REAL build+analyze verifier and a fake "model"
(revise_fn), so no API key is needed: a thin plate (blocking wall warning) is
revised into a thick box that passes.
"""
from app.ai.agent import (
    Issue,
    actionable_issues,
    blocking_issues,
    build_and_analyze,
    _run_loop,
)
from app.ai.generator import GeneratedDesign
from app.print_check.analyze import Check, PrintReadiness
from app.print_check.profile import PrinterProfile

THIN = GeneratedDesign(
    name="plate", description="", parameters=[], bodies=[{"name": "body", "color": "#111111"}],
    code="import cadquery as cq\ndef build(p):\n    return cq.Workplane('XY').box(40, 40, 0.5)",
)
THICK = GeneratedDesign(
    name="block", description="", parameters=[], bodies=[{"name": "body", "color": "#111111"}],
    code="import cadquery as cq\ndef build(p):\n    return cq.Workplane('XY').box(20, 20, 20)",
)


def _readiness(*checks):
    return PrintReadiness(checks=list(checks))


def test_issue_classification():
    r = _readiness(
        Check("Watertight", "ok", "closed"),
        Check("Wall thickness", "warn", "0.5 mm too thin"),
        Check("Overhangs", "warn", "needs support"),
    )
    assert {i.name for i in actionable_issues(r)} == {"Wall thickness", "Overhangs"}
    # overhangs are advisory, wall thickness blocks
    assert [i.name for i in blocking_issues(r)] == ["Wall thickness"]


def test_loop_revises_thin_into_thick_and_passes():
    prof = PrinterProfile()
    calls = {"n": 0}

    def revise(design, issues):
        calls["n"] += 1
        return THICK

    outcome = _run_loop(THIN, lambda d: build_and_analyze(d, prof), revise, max_iters=4)
    assert outcome.passed is True
    assert outcome.iterations == 2          # analyse thin -> revise -> analyse thick -> pass
    assert calls["n"] == 1
    assert outcome.design is THICK
    assert outcome.steps[0].action == "revising"
    assert outcome.steps[-1].action == "passed"


def test_loop_gives_up_within_budget():
    prof = PrinterProfile()

    def revise(design, issues):
        return THIN  # never improves

    outcome = _run_loop(THIN, lambda d: build_and_analyze(d, prof), revise, max_iters=3)
    assert outcome.passed is False
    assert outcome.iterations == 3
    assert outcome.steps[-1].action == "budget-exhausted"


def test_already_good_design_passes_first_try():
    prof = PrinterProfile()

    def revise(design, issues):  # should never be called
        raise AssertionError("revise should not run on an already-good design")

    outcome = _run_loop(THICK, lambda d: build_and_analyze(d, prof), revise, max_iters=4)
    assert outcome.passed is True
    assert outcome.iterations == 1
