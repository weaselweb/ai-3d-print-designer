"""Lightweight static guard for LLM-generated CAD code.

This is NOT a real sandbox. It is a single-user, internal tool that executes
Python the model wrote, and that is an inherent code-execution risk. The guard
below blocks the obvious footguns (os/sys/subprocess, file and network access,
dunder escapes) so a careless prompt can't trivially wreck the machine. If you
ever expose this beyond yourself, run the executor in a real sandbox
(subprocess + seccomp/nsjail, or a container) instead of trusting this.
"""
from __future__ import annotations

import ast

ALLOWED_IMPORTS = {"cadquery", "cq", "math", "numpy", "np"}

_BANNED_NAMES = {
    "eval", "exec", "compile", "open", "__import__", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "importlib", "builtins", "breakpoint",
}


class UnsafeCodeError(ValueError):
    pass


def validate_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:  # surfaced back to the model for a retry
        raise UnsafeCodeError(f"Syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    raise UnsafeCodeError(f"Import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORTS:
                raise UnsafeCodeError(f"Import not allowed: from {node.module}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise UnsafeCodeError(f"Dunder attribute access not allowed: {node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in _BANNED_NAMES:
                raise UnsafeCodeError(f"Use of '{node.id}' is not allowed")

    if "build" not in {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }:
        raise UnsafeCodeError("Code must define a top-level function `build(params)`.")
