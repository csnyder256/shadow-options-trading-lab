"""CATALYST MEMORY (opts-catmem-store-v1, 2026-07-11) - store schema, tag validation, recall.

The compounding "story memory": one row per catalyst name-day, joining WHAT happened (headline,
LLM-tagged kind) to the deterministic features (gap/vol/range from the in-play screen) and the
code-computed OUTCOME (forward returns from the daily price cache). The JSONL is the moat;
the SQLite index is a rebuildable cache (the iv_archive pattern).

Layout (under runtime/memory/):
    catalyst_stories.jsonl     append-only truth - one JSON row per SYM|date
    catalyst_memory.db         sqlite index, rebuilt from the JSONL by the builder
    catalyst_tags_llm.jsonl    the local-model tagging job's output (joined by key)

Discipline:
* Numbers are CODE-COMPUTED (forward returns, features); LLMs only tag kind/name_specific/
  direction_hint (charter law 2). Tag admission is drop-never-repair against the EXACT crew
  enum (CATALYST_KINDS) so the recall join works with tomorrow's hunt-list rows forever.
* recall() self-downgrades below min_cell and SAYS SO - no invented probabilities for thin
  cells. v1 conditions on (kind, gap_direction) only (power analysis, opts-catmem-store-v1).
* Censored rows (not enough future bars yet) are kept and flagged, never dropped - they heal
  as the daily cache accrues (survivorship honesty).

Stage 0 of the promotion ladder: nothing on the decision path reads this. Briefing (stage 1)
and kind_hist_* covariates (stage 2) land under their own registrations.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from atlas.config_loader import FRAMEWORK_ROOT
from atlas.crew.consensus import CATALYST_KINDS

MEM_DIR = FRAMEWORK_ROOT / "runtime" / "memory"
STORIES_PATH = MEM_DIR / "catalyst_stories.jsonl"
DB_PATH = MEM_DIR / "catalyst_memory.db"

DIRECTIONS = frozenset({"pos", "neg", "neutral"})
MIN_CELL_DEFAULT = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    key TEXT PRIMARY KEY, symbol TEXT NOT NULL, date TEXT NOT NULL,
    catalyst_kind TEXT, name_specific INTEGER, direction_hint TEXT,
    gap_direction TEXT, headline TEXT, n_news INTEGER,
    gap_pct REAL, vol_mult REAL, range_pct REAL, dollar_vol20 REAL, rank INTEGER,
    delisted INTEGER, gap_hold_d0 REAL, ret_1d REAL, ret_2d REAL, ret_5d REAL,
    censored INTEGER, tag_agree INTEGER, ingest TEXT
);
CREATE INDEX IF NOT EXISTS idx_kind_dir ON stories (catalyst_kind, gap_direction, name_specific);
"""


def validate_tag(item: Any) -> dict | None:
    """Drop-never-repair admission of one LLM tag row: kind ∈ crew enum, bools coerced,
    direction ∈ {pos,neg,neutral}. None = dropped (a tag we can't read strictly is no tag)."""
    if not isinstance(item, dict):
        return None
    kind = str(item.get("kind") or "").strip().lower()
    direction = str(item.get("direction_hint") or "neutral").strip().lower()
    if kind not in CATALYST_KINDS or direction not in DIRECTIONS:
        return None
    return {"kind": kind, "name_specific": bool(item.get("name_specific")),
            "direction_hint": direction}


def rebuild_index(stories_path: Path = STORIES_PATH, db_path: Path = DB_PATH) -> int:
    """Regenerate the SQLite index from the JSONL truth. Returns row count."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_SCHEMA)
        con.execute("DELETE FROM stories")
        n = 0
        with stories_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                fwd = r.get("fwd") or {}
                con.execute(
                    "INSERT OR REPLACE INTO stories VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r.get("key"), r.get("symbol"), r.get("date"), r.get("catalyst_kind"),
                     1 if r.get("name_specific") else 0, r.get("direction_hint"),
                     r.get("gap_direction"), r.get("headline"), r.get("n_news"),
                     r.get("gap_pct"), r.get("vol_mult"), r.get("range_pct"),
                     r.get("dollar_vol20"), r.get("rank"), 1 if r.get("delisted") else 0,
                     fwd.get("gap_hold_d0"), fwd.get("ret_1d"), fwd.get("ret_2d"),
                     fwd.get("ret_5d"), 1 if fwd.get("censored") else 0,
                     1 if (r.get("tag_source") or {}).get("agree") else 0,
                     r.get("ingest")))
                n += 1
        con.commit()
        return n
    finally:
        con.close()


def _stats(values: list[float]) -> dict | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)

    def pct(p: float) -> float:
        return round(vals[min(n - 1, int(p * n))], 4)

    return {"median": pct(0.5), "p25": pct(0.25), "p75": pct(0.75)}


def recall(kind: str, direction: str | None = None, *, min_cell: int = MIN_CELL_DEFAULT,
           db_path: Path = DB_PATH) -> dict:
    """Historical forward-move distribution for a catalyst cell. Deterministic, pure reads.
    `direction` = gap direction ('pos'/'neg', the deterministic axis). Cells thinner than
    `min_cell` transparently downgrade - first to kind-level (both directions), then to
    all name-specific stories - and REPORT the downgrade. name_specific=1 always."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        tries = [("kind|dir" if direction else "kind",
                  "catalyst_kind = ? AND gap_direction = ?" if direction else "catalyst_kind = ?",
                  (kind, direction) if direction else (kind,)),
                 ("kind", "catalyst_kind = ?", (kind,)),
                 ("all", "1=1", ())]
        downgraded_to = None
        for label, where, params in tries:
            rows = con.execute(
                f"SELECT gap_hold_d0, ret_1d, ret_2d, ret_5d, censored FROM stories "
                f"WHERE name_specific = 1 AND {where}", params).fetchall()
            usable = [r for r in rows if not r["censored"] or r["ret_2d"] is not None]
            if len(usable) >= min_cell:
                r2 = [r["ret_2d"] for r in usable if r["ret_2d"] is not None]
                pos2 = sum(1 for v in r2 if v > 0)
                gh = [r["gap_hold_d0"] for r in usable if r["gap_hold_d0"] is not None]
                fade = sum(1 for v in gh if v < 0)
                return {"n": len(usable), "cell": label,
                        "downgraded_to": downgraded_to,
                        "fwd_1d": _stats([r["ret_1d"] for r in usable]),
                        "fwd_2d": _stats(r2), "fwd_5d": _stats([r["ret_5d"] for r in usable]),
                        "p_pos_2d": round(pos2 / len(r2), 3) if r2 else None,
                        "gap_fade_rate": round(fade / len(gh), 3) if gh else None,
                        "n_censored": sum(1 for r in rows if r["censored"])}
            downgraded_to = "kind" if label != "kind" else "all"
        return {"n": 0, "cell": "all", "downgraded_to": "empty", "fwd_1d": None,
                "fwd_2d": None, "fwd_5d": None, "p_pos_2d": None, "gap_fade_rate": None,
                "n_censored": 0}
    finally:
        con.close()
