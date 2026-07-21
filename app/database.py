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
