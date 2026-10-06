"""LabLedger - per-strategy single-writer ledgers under runtime/strategy_lab/ (thin IO).

Layout (single writer = the lab process; every append via oshadow.append_jsonl → fsync +
torn-tail guard inherited, not reimplemented):

    runtime/strategy_lab/<strategy_id>/entries.jsonl     lab_entry records
    runtime/strategy_lab/<strategy_id>/marks.jsonl       lab_mark records
    runtime/strategy_lab/<strategy_id>/exits.jsonl       lab_exit records
    runtime/strategy_lab/<strategy_id>/journal.jsonl     strategy-scoped journal
    runtime/strategy_lab/quotes/YYYY-MM-DD.jsonl         shared per-leg NBBO stream (replay)
    runtime/strategy_lab/lab_journal.jsonl               process-level journal

Rebuild is FAIL-CLOSED (SHADOW-LEDGER-2 semantics): open_positions() reads exits with
strict=True so an unreadable exits file raises LedgerUnreadable instead of resurrecting
closed combos. Cross-strategy integrity: a row whose strategy_id does not match its
directory is a foreign_strategy_row - the grader gates on it; the writer prevents it here.
"""

from __future__ import annotations

from pathlib import Path

from atlas.options.shadow import LedgerUnreadable, append_jsonl, read_jsonl  # noqa: F401

from .model import ComboPosition, combo_from_entry

LAB_DIRNAME = "strategy_lab"


class StrategyLedger:
    """Handles for ONE strategy's ledger directory."""

    def __init__(self, root: Path, strategy_id: str):
        self.strategy_id = strategy_id
        self.dir = Path(root) / strategy_id
        self.entries_path = self.dir / "entries.jsonl"
        self.marks_path = self.dir / "marks.jsonl"
        self.exits_path = self.dir / "exits.jsonl"
        self.journal_path = self.dir / "journal.jsonl"

    def _check(self, rec: dict) -> None:
        sid = rec.get("strategy_id")
        if sid is not None and sid != self.strategy_id:
            raise ValueError(f"foreign_strategy_row: {sid!r} written into {self.strategy_id!r}")

    def write_entry(self, rec: dict) -> None:
        self._check(rec)
        append_jsonl(self.entries_path, rec)

    def write_mark(self, rec: dict) -> None:
        self._check(rec)
        append_jsonl(self.marks_path, rec)

    def write_exit(self, rec: dict) -> None:
        self._check(rec)
        append_jsonl(self.exits_path, rec)

    def journal(self, rec: dict) -> None:
        append_jsonl(self.journal_path, {"strategy_id": self.strategy_id, **rec})

    def open_positions(self) -> list:
        """Rebuild open combos: entries minus exited position_ids. Fail-CLOSED on unreadable
        ledgers (raises LedgerUnreadable). Malformed entry rows are skipped (never crash).

        Each surviving position is then re-primed from its OWN mark history. A rebuild starts
        from the ENTRY row, and `combo_from_entry` starts the observation state empty - so
        without this the running underlying MFE/MAE and the mark-carried strategy state reset
        at every session boundary, and a multi-day exit record reported only the excursion of
        the session it closed in. This mirrors ShadowLedger._open_positions, which re-primes
        peak/mfe/breach clocks from the same marks. Marks are best-effort (tolerant read), so
        an unreadable marks file degrades the re-prime, never the fail-closed entries/exits.
        """
        exits = read_jsonl(self.exits_path, strict=True)
        entries = read_jsonl(self.entries_path, strict=True)
        exited = {r.get("position_id") for r in exits if r.get("event") == "lab_exit"}
        marks_by_pid: dict = {}
        for mk in read_jsonl(self.marks_path):
            marks_by_pid.setdefault(mk.get("position_id"), []).append(mk)
        out: list[ComboPosition] = []
        for rec in entries:
            if rec.get("event") != "lab_entry" or rec.get("position_id") in exited:
                continue
            pos = combo_from_entry(rec)
            if pos is not None:
                self._reprime_from_marks(pos, marks_by_pid.get(pos.position_id, []))
                out.append(pos)
        return out

    @staticmethod
    def _reprime_from_marks(pos: ComboPosition, marks: list) -> None:
        """Seed a rebuilt position's observation state from its mark history (append-only,
        single writer, oldest-first). Restores the running underlying excursion and the last
        mark clock, and re-applies the strategy state carried through the marks - the fields
        a day-roll rebuild would otherwise zero every session. Mirrors the main shadow's
        rebuild, and is the default `Strategy.rebuild` already assumes."""
        for mk in marks:
            try:
                s = float(mk.get("S") or 0.0)
                ts = float(mk.get("ts_epoch") or 0.0)
            except (TypeError, ValueError):
                continue
            if s > 0:
                pos.observe_underlying(s)
            pos.last_mark_ts = max(pos.last_mark_ts, ts)
        if marks:
            state = marks[-1].get("state")
            if isinstance(state, dict):
                pos.carried = dict(state)

    def marks_for(self, position_id: str) -> list:
        return [r for r in read_jsonl(self.marks_path) if r.get("position_id") == position_id]


class LabLedger:
    """Root wrapper: per-strategy sub-ledgers + shared quotes stream + process journal."""

    def __init__(self, runtime_root: Path | str):
        self.root = Path(runtime_root) / LAB_DIRNAME
        self.quotes_dir = self.root / "quotes"
        self.lab_journal_path = self.root / "lab_journal.jsonl"
        self._strategies: dict[str, StrategyLedger] = {}

    def strategy(self, strategy_id: str) -> StrategyLedger:
        if strategy_id not in self._strategies:
            self._strategies[strategy_id] = StrategyLedger(self.root, strategy_id)
        return self._strategies[strategy_id]

    def write_quote(self, day: str, rec: dict) -> None:
        append_jsonl(self.quotes_dir / f"{day}.jsonl", rec)

    def journal(self, rec: dict) -> None:
        append_jsonl(self.lab_journal_path, rec)

    def known_strategy_dirs(self) -> list:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and p.name not in ("quotes", "_archive"))

    def open_positions_all(self, strategy_ids: list | None = None) -> dict:
        """{strategy_id: [ComboPosition]} across the roster (or all known dirs).
        Propagates LedgerUnreadable - the day-roll must abort, not resurrect."""
        ids = strategy_ids if strategy_ids is not None else self.known_strategy_dirs()
        return {sid: self.strategy(sid).open_positions() for sid in ids}
