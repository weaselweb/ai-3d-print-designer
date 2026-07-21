"""SQLite schema and helpers.

A *design* stores the parametric CAD source plus its parameter set, so a design
is re-generatable and editable later — not just an opaque mesh.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS designs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL DEFAULT '',
    engine      TEXT NOT NULL DEFAULT 'cadquery',
    code        TEXT NOT NULL,
    parameters  TEXT NOT NULL DEFAULT '[]',   -- JSON list of param definitions
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id         TEXT PRIMARY KEY,
    design_id  TEXT NOT NULL,
    kind       TEXT NOT NULL,                 -- stl | step | preview | upload
    path       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (design_id) REFERENCES designs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS captures (
    id               TEXT PRIMARY KEY,
    photo_path       TEXT NOT NULL,
    reference_label  TEXT NOT NULL DEFAULT '',
    reference_mm     REAL NOT NULL DEFAULT 0,
    mm_per_px        REAL NOT NULL DEFAULT 0,
    measurements     TEXT NOT NULL DEFAULT '[]',  -- JSON: [{name, mm, p1, p2}]
    description      TEXT NOT NULL DEFAULT '',
    design_id        TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signs (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL DEFAULT '',
    params      TEXT NOT NULL DEFAULT '{}',   -- JSON: dims + colours + toggles
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_design(
    *,
    design_id: str | None,
    name: str,
    description: str,
    prompt: str,
    engine: str,
    code: str,
    parameters: list[dict[str, Any]],
) -> str:
    now = _now()
    params_json = json.dumps(parameters)
    with connect() as conn:
        if design_id and conn.execute("SELECT 1 FROM designs WHERE id=?", (design_id,)).fetchone():
            conn.execute(
                """UPDATE designs SET name=?, description=?, prompt=?, engine=?, code=?,
                   parameters=?, updated_at=? WHERE id=?""",
                (name, description, prompt, engine, code, params_json, now, design_id),
            )
            return design_id
        design_id = design_id or new_id()
        conn.execute(
            """INSERT INTO designs (id, name, description, prompt, engine, code, parameters,
               created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (design_id, name, description, prompt, engine, code, params_json, now, now),
        )
        return design_id


def get_design(design_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM designs WHERE id=?", (design_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["parameters"] = json.loads(data["parameters"])
    return data


def list_designs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, description, created_at, updated_at FROM designs "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_parameters(design_id: str, parameters: list[dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE designs SET parameters=?, updated_at=? WHERE id=?",
            (json.dumps(parameters), _now(), design_id),
        )


# --------------------------------------------------------------------------- #
# Captures (photo -> measurement -> reconstruction)
# --------------------------------------------------------------------------- #
def create_capture(photo_path: str, capture_id: str | None = None) -> str:
    capture_id = capture_id or new_id()
    now = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO captures (id, photo_path, created_at, updated_at) VALUES (?,?,?,?)",
            (capture_id, photo_path, now, now),
        )
    return capture_id


def get_capture(capture_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["measurements"] = json.loads(data["measurements"])
    return data


def save_capture_measurements(
    capture_id: str,
    *,
    reference_label: str,
    reference_mm: float,
    mm_per_px: float,
    measurements: list[dict[str, Any]],
    description: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE captures SET reference_label=?, reference_mm=?, mm_per_px=?,
               measurements=?, description=?, updated_at=? WHERE id=?""",
            (reference_label, reference_mm, mm_per_px, json.dumps(measurements),
             description, _now(), capture_id),
        )


def attach_design_to_capture(capture_id: str, design_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE captures SET design_id=?, updated_at=? WHERE id=?",
            (design_id, _now(), capture_id),
        )


# --------------------------------------------------------------------------- #
# Signs (multi-colour)
# --------------------------------------------------------------------------- #
def save_sign(sign_id: str | None, text: str, params: dict[str, Any]) -> str:
    now = _now()
    params_json = json.dumps(params)
    with connect() as conn:
        if sign_id and conn.execute("SELECT 1 FROM signs WHERE id=?", (sign_id,)).fetchone():
            conn.execute(
                "UPDATE signs SET text=?, params=?, updated_at=? WHERE id=?",
                (text, params_json, now, sign_id),
            )
            return sign_id
        sign_id = sign_id or new_id()
        conn.execute(
            "INSERT INTO signs (id, text, params, created_at, updated_at) VALUES (?,?,?,?,?)",
            (sign_id, text, params_json, now, now),
        )
        return sign_id


def get_sign(sign_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM signs WHERE id=?", (sign_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["params"] = json.loads(data["params"])
    return data
