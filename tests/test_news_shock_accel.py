"""WS5 proof (opts-news-shock-accel-v1): a fresh high-materiality news shock on a HELD underlying
forces an immediate re-mark (bypassing the cadence) via the SAME C5 idiom - it sets last_mark_ts +
journals reval_trigger kind:news_shock, NEVER touching the exit engine - and is deduped per shock
fingerprint. Mirrors test_price_shock_triggers_immediate_reval."""

from __future__ import annotations

import atlas.options.shadow as oshadow
from tests.test_options_shadow import (OCC98, FakeClient, _entry_record, arm_script_lane, ep,
                                       make_core, tk, tq)


class _StubNewsCache:
    """Stands in for NewsFlagsCache: fresh_shock returns a fixed shock row for XYZ."""

    def __init__(self, shock):
        self._shock = shock
        self.updates = 0

    def update(self):
        self.updates += 1

    def fresh_shock(self, sym, now):
        return self._shock if str(sym).upper() == "XYZ" else None


def _news_triggers(led):
    return [r for r in oshadow.read_jsonl(led.journal_path)
            if r.get("event") == "reval_trigger" and r.get("kind") == "news_shock"]


def test_news_shock_forces_reval_and_dedupes(tmp_path):
    clock = {"t": ep(585, 30)}
    client = FakeClient()
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    arm_script_lane(core, clock)                              # rolls the day (sets _close_min)
    core.positions["P1"] = oshadow.position_from_entry(_entry_record("P1"))
    client.quotes[OCC98] = tq(OCC98, 2.75, 2.85)
    core.positions["P1"].last_mark_ts = clock["t"]           # just marked: cadence NOT due

    core._news_cache = _StubNewsCache({"fingerprint": "fpX", "kind": "fda", "materiality": 0.9})
    core._reval_positions(clock["t"])                        # a fresh shock is present

    ns = _news_triggers(led)
    assert ns and ns[0]["position_id"] == "P1"
    assert ns[0]["news_kind"] == "fda" and ns[0]["materiality"] == 0.9
    assert core._news_marked.get("P1") == "fpX"              # deduped by fingerprint
    assert core._news_cache.updates >= 1                     # per-sweep tail refresh happened

    # SAME shock again -> NO new news_shock trigger (deduped)
    if "P1" in core.positions:
        core.positions["P1"].last_mark_ts = clock["t"]
    core._reval_positions(clock["t"])
    assert len(_news_triggers(led)) == 1                     # still exactly one


def test_no_shock_no_trigger(tmp_path):
    clock = {"t": ep(585, 30)}
    client = FakeClient()
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    arm_script_lane(core, clock)
    core.positions["P1"] = oshadow.position_from_entry(_entry_record("P1"))
    client.quotes[OCC98] = tq(OCC98, 2.75, 2.85)
    core._news_cache = _StubNewsCache(None)                  # no fresh shock
    core._reval_positions(clock["t"])
    assert _news_triggers(led) == []                         # nothing forced
