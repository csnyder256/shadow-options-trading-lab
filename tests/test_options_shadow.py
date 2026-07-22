"""OPTIONS SHADOW (O3): ledger identities + the full process lifecycle with fakes - a scripted
lane fires, the selector runs on a crafted chain, an entry record lands, marks accumulate, a
crafted invalidation forces the exit, and the three-ledger P&L signs come out right. Also:
concurrency cap, same-direction merge, blackout skip, restart rebuild. No network, no sleeps."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from atlas.clock import NY
from atlas.collect.tradier_data import TOption, TQuote
from atlas.hunter.feed import Tick
from atlas.options import shadow as oshadow
from atlas.options.events import EconEvent
from atlas.options.lanes import LaneSignal
from scripts.run_options_shadow import (DEFAULTS, OptionsShadowCore, config_hash,
                                        load_hunt_list, load_shadow_config, tradier_from_yaml)

DAY = "2026-07-14"                                     # a Tuesday
EXP = "2026-07-17"                                     # DTE 3 from DAY
MIDNIGHT = datetime(2026, 7, 14, 0, 0, tzinfo=NY).timestamp()
OCC98 = "XYZ260717C00098000"


def ep(minute: int, sec: float = 0.0) -> float:
    return MIDNIGHT + minute * 60 + sec


def tk(sym: str, minute: int, sec: float, last: float, cum: float = 1000.0) -> Tick:
    b, a = last - 0.01, last + 0.01
    return Tick(symbol=sym, ts_epoch=ep(minute, sec), last=last, bid=b, ask=a,
                spread_bps=(a - b) / last * 1e4, day_cum_volume=cum)


def topt(occ: str, strike: float, bid: float, ask: float, *, typ: str = "call") -> TOption:
    return TOption(symbol=occ, option_type=typ, strike=strike, volume=500.0,
                   open_interest=2000.0, bid=bid, ask=ask, last=0.0, expiration=EXP)


def tq(sym: str, bid: float, ask: float, last: float = 0.0) -> TQuote:
    return TQuote(symbol=sym, last=last or (bid + ask) / 2.0, bid=bid, ask=ask,
                  prevclose=0.0, volume=0.0, average_volume=0.0)


CHAIN = [topt("XYZ260717C00096000", 96.0, 4.30, 4.42),
         topt(OCC98, 98.0, 2.75, 2.85),
         topt("XYZ260717C00100000", 100.0, 1.55, 1.63),
         topt("XYZ260717C00102000", 102.0, 0.72, 0.78)]


class FakeClient:
    def __init__(self, chain=CHAIN, expirations=(EXP,)):
        self.chain = list(chain)
        self.expirations = list(expirations)
        self.quotes: dict = {}
        self.chain_calls: list = []

    def get_quotes(self, symbols):
        return {s.upper(): self.quotes[s.upper()] for s in symbols if s.upper() in self.quotes}

    def get_option_expirations(self, symbol):
        return list(self.expirations)

    def get_option_chain(self, symbol, expiration, greeks=False):
        self.chain_calls.append((symbol, expiration, greeks))
        return [r for r in self.chain if r.expiration == expiration]

    def close(self):
        pass


class FakeFeed:
    def __init__(self):
        self.queue: list[dict] = []
        self.backfills: dict = {}

    def poll(self, symbols):
        return self.queue.pop(0) if self.queue else {}

    def backfill(self, symbol):
        return list(self.backfills.get(symbol, []))


class ScriptLane:
    LANE = "script"

    def __init__(self):
        self.queue: list = []
        self.invalid = False

    def update(self, ctx):
        return self.queue.pop(0) if self.queue else None

    def invalidated(self, pos):
        return self.invalid


def signal(*, lane="script", underlying="XYZ", direction="call", expires=700) -> LaneSignal:
    import math
    return LaneSignal(lane=lane, underlying=underlying, direction=direction, target_move=0.02,
                      p_thesis=0.6, horizon_T=1.0 / 252.0,
                      mu_thesis=math.log(1.02) * 252.0 * (1 if direction == "call" else -1),
                      expires_minute=expires, notes={})


def make_core(tmp_path, *, clock, client=None, events=()):
    cfg = dict(DEFAULTS)
    cfg["watch"] = ["XYZ"]
    ledger = oshadow.ShadowLedger(tmp_path)
    core = OptionsShadowCore(client=client if client is not None else FakeClient(),
                             feed=FakeFeed(), ledger=ledger,
                             clock_fn=lambda: clock["t"], cfg=cfg, log=lambda _m: None,
                             events_list=list(events), profiles={}, lane2_candidates=[],
                             heartbeat_path=tmp_path / "hb.json",
                             session_days={})       # injected: normal-day fallback, zero IO
    return core, ledger


def arm_script_lane(core, clock):
    """Roll the day (first tick) then swap in the scripted lane roster."""
    core.tick()
    lane = ScriptLane()
    core.lanes = [lane]
    core._lane_by_name = {lane.LANE: lane}
    return lane


# --------------------------------------------------------------------------- pure ledger identities
def test_entry_fill_identities():
    f = oshadow.entry_fills(2.75, 2.85)
    assert f["optimistic"] <= f["base"] <= f["worst"]
    assert f == {"worst": 2.85, "base": 2.8175, "optimistic": 2.80}
    # crossed/degenerate quotes clamp instead of inverting the identity
    g = oshadow.entry_fills(2.85, 2.75)
    assert g["optimistic"] <= g["base"] <= g["worst"]
    z = oshadow.entry_fills(0.0, 0.0)
    assert z["worst"] == z["base"] == z["optimistic"] == 0.0


def test_exit_fill_identities():
    f = oshadow.exit_fills(2.60, 2.70)
    assert f["worst"] <= f["base"] <= f["optimistic"]
    assert f == {"worst": 2.60, "base": 2.6325, "optimistic": 2.65}


def _entry_record(position_id="P1", bid=2.75, ask=2.85):
    sig = signal()
    from dataclasses import asdict
    pick = {"occ": OCC98, "underlying": "XYZ", "opt_type": "call", "strike": 98.0,
            "expiry": EXP, "bid": bid, "ask": ask, "S": 100.0, "theta_day": -0.15}
    return oshadow.build_entry_record(ts=ep(587), day=DAY, entry_minute=587,
                                      position_id=position_id, lanes=["script"],
                                      config_hash="abc123", signal=asdict(sig), pick=pick,
                                      runner_up_occs=["XYZ260717C00096000"],
                                      nbbo={"bid": bid, "ask": ask},
                                      risk_flags=["spread_gt_5pct"])


def test_exit_record_three_ledger_pnl_ordering_and_decomposition():
    rec = _entry_record()
    pos = oshadow.position_from_entry(rec)
    assert pos is not None and pos.occ == OCC98 and pos.entry_fills == rec["fills"]
    pos.observe_underlying(100.5)
    pos.observe_underlying(99.8)
    out = oshadow.build_exit_record(ts=ep(600), day=DAY, pos=pos, rule="b_thesis_invalid",
                                    bid=2.60, ask=2.70, solved_iv=0.29, S=99.8,
                                    decision_state={"x": 1}, variant_would_hold=False,
                                    hold_trading_days=13.0 / 390.0)
    led = out["ledgers"]
    assert (led["worst"]["net_pnl_usd"] <= led["base"]["net_pnl_usd"]
            <= led["optimistic"]["net_pnl_usd"])
    assert led["worst"]["net_pnl_usd"] == -25.0                    # buy 2.85, sell 2.60
    assert led["optimistic"]["net_pnl_usd"] == -15.0               # mid-to-mid
    assert led["worst"]["gross_pnl_usd"] == -15.0                  # gross = mid-to-mid everywhere
    # spread paid = entry half-spread + exit half-spread = 0.05 + 0.05 -> $10
    assert abs(out["decomposition"]["spread_paid_usd"] - 10.0) < 1e-9
    assert out["decomposition"]["theta_paid_usd"] < 0              # theta cost is negative P&L
    assert out["underlying_mfe"] == 0.005 and out["underlying_mae"] == -0.002
    assert out["rule"] == "b_thesis_invalid" and out["variant_would_hold"] is False


def test_restart_rebuild_open_positions_for_day(tmp_path):
    led = oshadow.ShadowLedger(tmp_path)
    led.write_entry(_entry_record("P1"))
    led.write_mark(oshadow.build_mark_record(ts=ep(592), position_id="P1", occ=OCC98,
                                             bid=3.0, ask=3.1, solved_iv=0.3, S=100.6,
                                             decision_state={}, action="HOLD", rule="j_hold"))
    open_pos = led.open_positions_for_day(DAY)
    assert len(open_pos) == 1
    pos = open_pos[0]
    assert pos.peak_mid == 3.05 and pos.fav_max > 0                # re-primed from the mark
    assert pos.entry_theta_day == -0.15
    # a merge adds its lane tag on rebuild
    led.write_merge(oshadow.build_merge_record(ts=ep(593), day=DAY, position_id="P1",
                                               lane="lane_b", signal={}))
    assert "lane_b" in led.open_positions_for_day(DAY)[0].lanes
    # after the exit the day has no open positions
    led.write_exit(oshadow.build_exit_record(ts=ep(600), day=DAY, pos=pos, rule="a", bid=2.6,
                                             ask=2.7, solved_iv=0.3, S=99.8, decision_state={},
                                             variant_would_hold=False, hold_trading_days=0.03))
    assert led.open_positions_for_day(DAY) == []


# --------------------------------------------------------------------------- full lifecycle
def test_full_lifecycle_entry_marks_forced_exit(tmp_path):
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    lane = arm_script_lane(core, clock)

    # ---- lane fires on the completed 585 bar -> selector -> entry ----------------------------
    lane.queue.append(signal())
    clock["t"] = ep(586, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 586, 0, 100.0)})
    core.tick()
    entries = led.load_entries(DAY)
    assert len(entries) == 1 and core.entries_today == 1
    ent = entries[0]
    occ = ent["pick"]["occ"]
    eb, ea = ent["nbbo"]["bid"], ent["nbbo"]["ask"]
    assert occ in {r.symbol for r in CHAIN}
    assert 0.40 <= abs(ent["pick"]["delta"]) <= 0.80               # the value-band pick
    assert ent["fills"] == oshadow.entry_fills(eb, ea)
    assert ent["fills"]["optimistic"] <= ent["fills"]["base"] <= ent["fills"]["worst"]
    assert ent["lanes"] == ["script"] and ent["config_hash"] == core.cfg_hash
    assert ent["runner_up_occs"] and occ not in ent["runner_up_occs"]
    # C2/C3 (opts-covariates-v1): regime covariates + runner-up quote snapshot on every entry
    assert ent["covariates"]["vwap_dist"] is not None and "is_friday" in ent["covariates"]
    snap = ent["runner_up_snapshot"]
    assert snap and all(k in snap[0] for k in ("occ", "bid", "ask", "delta", "score"))
    assert [s["occ"] for s in snap] == ent["runner_up_occs"]
    assert len(core.positions) == 1
    assert client.chain_calls[0][2] is True                        # chains fetched greeks=True

    # ---- 5-min cadence: too early -> no mark; due -> HOLD mark + quote-path row --------------
    clock["t"] = ep(588, 0)
    client.quotes[occ] = tq(occ, eb + 0.05, ea + 0.05)
    core.feed.queue.append({"XYZ": tk("XYZ", 588, 0, 100.3)})
    core.tick()
    assert led.load_marks() == []                                  # 2 min < the 5-min cadence
    clock["t"] = ep(591, 5)
    core.feed.queue.append({"XYZ": tk("XYZ", 591, 5, 100.5)})
    core.tick()
    marks = led.load_marks()
    assert len(marks) == 1 and marks[0]["action"] == "HOLD" and marks[0]["occ"] == occ
    assert marks[0]["solved_iv"] > 0 and marks[0]["S"] == 100.5
    qpath = tmp_path / "options_shadow_quotes" / f"{DAY}.jsonl"
    qlines = [json.loads(x) for x in qpath.read_text("utf-8").splitlines()]
    # v3: mark-at-entry row (REPLAY-LAB-3 root fix) + the reval row
    assert len(qlines) == 2 and qlines[0]["ext"].get("entry_row") is True

    # ---- crafted invalidation -> rule (b) needs 2 consecutive committed-close evaluations
    # (audit Wave 2.13: the one-tick hair-trigger decided 2 of 3 lifetime trades) ---------------
    lane.invalid = True
    clock["t"] = ep(597, 0)
    client.quotes[occ] = tq(occ, eb - 0.15, ea - 0.15)             # mid slid 15c below entry mid
    core.feed.queue.append({"XYZ": tk("XYZ", 597, 0, 99.8)})
    core.tick()
    assert led.load_exits(DAY) == [] and len(core.positions) == 1  # streak 1: armed, NOT fired
    clock["t"] = ep(602, 10)
    core.feed.queue.append({"XYZ": tk("XYZ", 602, 10, 99.8)})      # new committed bar -> eval 2
    core.tick()
    exits = led.load_exits(DAY)
    assert len(exits) == 1 and core.positions == {}
    ex = exits[0]
    assert ex["rule"] == "b_thesis_invalid"
    lg = ex["ledgers"]
    assert lg["worst"]["net_pnl_usd"] <= lg["base"]["net_pnl_usd"] <= lg["optimistic"]["net_pnl_usd"]
    spread = round(ea - eb, 4)
    assert lg["optimistic"]["net_pnl_usd"] == -15.0                # mid-to-mid slide
    assert lg["worst"]["net_pnl_usd"] == round(-15.0 - spread * 100.0, 2)   # + round-trip spread
    assert lg["worst"]["gross_pnl_usd"] == -15.0                   # gross = mid-to-mid everywhere
    assert ex["underlying_mfe"] >= 0.005 and ex["underlying_mae"] <= -0.002
    assert ex["state"].get("nbbo_source") == "fresh"               # fill provenance (Wave 0.2)
    qlines = [json.loads(x) for x in qpath.read_text("utf-8").splitlines()]
    # entry_row + 3 reval rows (591/597/602) + the post-exit capture row (REPLAY-LAB-1)
    assert len(qlines) == 5
    assert qlines[-1]["ext"].get("post_exit") is True

    # ---- heartbeat ---------------------------------------------------------------------------
    hb = json.loads((tmp_path / "hb.json").read_text("utf-8"))
    assert hb["mode"] == "shadow" and hb["open_positions"] == 0 and hb["entries_today"] == 1
    assert hb["lanes_armed"] == ["script"] and hb["pid"] > 0
    # schema 2 (2026-07-10): data-plane liveness fields for alert_watch's zombie check
    assert hb["schema"] == 2 and hb["client_present"] is True
    assert hb["last_tick_epoch"] > 0 and hb["last_bar_epoch"] > 0 and hb["last_mark_epoch"] > 0


def test_heartbeat_schema2_degraded_without_client(tmp_path):
    """Token-less launch (heartbeat-only by design): client_present False, epochs stay 0.0 - 
    the fields alert_watch's data-plane check pages on."""
    clock = {"t": ep(585, 30)}
    core, _led = make_core(tmp_path, clock=clock)
    core.client = None
    core.tick()                                   # empty feed queue: no ticks, no bars, no marks
    hb = json.loads((tmp_path / "hb.json").read_text("utf-8"))
    assert hb["schema"] == 2 and hb["client_present"] is False
    assert hb["last_tick_epoch"] == 0.0
    assert hb["last_bar_epoch"] == 0.0 and hb["last_mark_epoch"] == 0.0


def test_concurrency_cap_blocks_fourth_position(tmp_path):
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    lane = arm_script_lane(core, clock)
    for i, sym in enumerate(("AAA", "BBB", "CCC")):                # 3 dummies fill the book
        rec = _entry_record(f"D{i}")
        pos = oshadow.position_from_entry(rec)
        pos.underlying = sym
        core.positions[f"D{i}"] = pos
    lane.queue.append(signal())                                    # 4th, on XYZ
    clock["t"] = ep(586, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 586, 0, 100.0)})
    core.tick()
    assert led.load_entries(DAY) == [] and len(core.positions) == 3
    j = [r for r in oshadow.read_jsonl(led.journal_path)
         if r.get("event") == "signal_concurrency_skip"]
    assert len(j) == 1 and j[0]["open_positions"] == 3


def test_same_underlying_same_direction_merges_lane_tag(tmp_path):
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    lane = arm_script_lane(core, clock)
    lane.queue.append(signal())
    clock["t"] = ep(586, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 586, 0, 100.0)})
    core.tick()
    assert len(core.positions) == 1
    lane.queue.append(signal(lane="index_trend"))                  # 2nd lane, same XYZ call view
    clock["t"] = ep(587, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 587, 0, 100.1)})
    core.tick()
    assert len(core.positions) == 1 and len(led.load_entries(DAY)) == 1
    pos = next(iter(core.positions.values()))
    assert sorted(pos.lanes) == ["index_trend", "script"]
    merges = led.load_merges(DAY)
    assert len(merges) == 1 and merges[0]["lane"] == "index_trend"
    # an OPPOSITE-direction signal does NOT merge (it books its own decision path)
    lane.queue.append(signal(lane="macro", direction="put"))
    clock["t"] = ep(588, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 588, 0, 100.0)})
    core.tick()
    assert len(led.load_merges(DAY)) == 1                          # no second merge record


def test_blackout_skips_signal_and_journals(tmp_path):
    ev_ts = datetime(2026, 7, 14, 9, 50, tzinfo=NY)
    events = [EconEvent("cpi", ev_ts)]
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client, events=events)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    lane = arm_script_lane(core, clock)
    lane.queue.append(signal())
    clock["t"] = ep(586, 0)                                        # 09:46 - inside [-5m, +15m]
    core.feed.queue.append({"XYZ": tk("XYZ", 586, 0, 100.0)})
    core.tick()
    assert led.load_entries(DAY) == [] and core.positions == {}
    j = [r for r in oshadow.read_jsonl(led.journal_path)
         if r.get("event") == "signal_blackout_skip"]
    assert len(j) == 1 and j[0]["blackout"] == "cpi"


def test_expired_and_after_hours_signals_are_journaled_not_traded(tmp_path):
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    lane = arm_script_lane(core, clock)
    lane.queue.append(signal(expires=580))                         # already stale
    clock["t"] = ep(586, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 586, 0, 100.0)})
    core.tick()
    assert led.load_entries(DAY) == []
    kinds = {r.get("event") for r in oshadow.read_jsonl(led.journal_path)}
    assert "signal_expired" in kinds


def test_no_pick_is_journaled_with_rejection_reasons(tmp_path):
    # a chain whose only rows are lotto wings -> selector rejects everything, journal explains
    chain = [topt("XYZ260717C00115000", 115.0, 0.05, 0.06),
             topt("XYZ260717C00120000", 120.0, 0.02, 0.03)]
    client = FakeClient(chain=chain)
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    lane = arm_script_lane(core, clock)
    lane.queue.append(signal())
    clock["t"] = ep(586, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 586, 0, 100.0)})
    core.tick()
    assert led.load_entries(DAY) == []
    j = [r for r in oshadow.read_jsonl(led.journal_path) if r.get("event") == "no_pick"]
    assert len(j) == 1 and j[0]["rejections"]                      # reason histogram present


# --------------------------------------------------------------------------- 2026-07-09 audit fixes
def test_one_dte_only_picks_next_trading_session_on_friday(tmp_path):
    # lane 1b: strict dte==1 had no match on Fridays (Saturday isn't an expiration) - the lane
    # died with no_chain_rows every Friday. Fix: nearest expiration >= 1 day.
    client = FakeClient(expirations=("2026-07-17", "2026-07-20", "2026-07-22"))
    core, _led = make_core(tmp_path, clock={"t": ep(930)}, client=client)
    sig = LaneSignal(lane="last30", underlying="XYZ", direction="call", target_move=0.002,
                     p_thesis=0.5, horizon_T=25.0 / 390.0 / 252.0, mu_thesis=1.0,
                     expires_minute=935, notes={"one_dte_only": True})
    _rows, exps = core._chain_rows(sig, date(2026, 7, 17))          # Friday
    assert exps == ["2026-07-20"]                                   # Monday, not nothing
    _rows, exps = core._chain_rows(sig, date(2026, 7, 16))          # Thursday
    assert exps == ["2026-07-17"]                                   # classic next-day expiry


def test_lane2_candidates_fetch_average_volume_for_hunt_list_names(tmp_path, monkeypatch):
    # hunt-list names had no average_volume, so the documented RVOL fallback computed 0 and
    # InPlayORB silently stood down on every uncached name (= every fresh catalyst gapper).
    import scripts.run_options_shadow as ros
    client = FakeClient()
    client.quotes["NEWG"] = TQuote(symbol="NEWG", last=10.0, bid=9.9, ask=10.1,
                                   prevclose=9.0, volume=0.0, average_volume=2_000_000.0)
    core, led = make_core(tmp_path, clock={"t": ep(585, 30)}, client=client)
    core._lane2_arg = None                                          # force the hunt-list path
    core._day = DAY
    monkeypatch.setattr(ros, "load_hunt_list", lambda path=ros.HUNT_LIST: ([
        {"symbol": "NEWG", "gap_pct": 8.0, "catalyst": True, "catalyst_kind": None},
        {"symbol": "NOQT", "gap_pct": 5.0, "catalyst": True, "catalyst_kind": None}], DAY))
    monkeypatch.setattr(ros, "_avg_first5_from_cache", lambda _sym: 0.0)
    cands = {c.symbol: c for c in core._lane2_candidates()}
    assert cands["NEWG"].average_volume == 2_000_000.0              # fetched fallback baseline
    j = [r for r in oshadow.read_jsonl(led.journal_path)
         if r.get("event") == "lane2_rvol_baseline_missing"]
    assert [r["symbol"] for r in j] == ["NOQT"]                     # the blind name is visible


def test_day_roll_keeps_overnight_position_and_flags_expired(tmp_path):
    # positions were rebuilt from TODAY's entries only, orphaning any overnight hold at the
    # day roll (never marked, never exited). Fix: rebuild from ALL unexited entries; entries
    # already past expiry are journaled loudly and excluded.
    client = FakeClient()
    clock = {"t": ep(585) + 86400}                                  # Wed 2026-07-15 09:45
    core, led = make_core(tmp_path, clock=clock, client=client)
    led.write_entry(_entry_record("OVN"))                           # entered Tue, expiry Fri
    core.tick()
    assert "OVN" in core.positions                                  # survives the day roll
    clock2 = {"t": ep(585) + 6 * 86400}                             # Mon 2026-07-20: expired
    core2, led2 = make_core(tmp_path, clock=clock2, client=client)
    core2.tick()
    assert core2.positions == {}
    j = [r for r in oshadow.read_jsonl(led2.journal_path)
         if r.get("event") == "expired_unexited_position"]
    assert len(j) == 1 and j[0]["position_id"] == "OVN"
    # 2026-07-09 refute fix: later day rolls / restarts do NOT re-journal the same position
    clock3 = {"t": ep(585) + 7 * 86400}                             # Tue 2026-07-21
    core3, led3 = make_core(tmp_path, clock=clock3, client=client)
    core3.tick()
    j2 = [r for r in oshadow.read_jsonl(led3.journal_path)
          if r.get("event") == "expired_unexited_position"]
    assert len(j2) == 1                                             # still exactly one row


def test_peak_bid_reprimed_from_marks(tmp_path):
    # v2 (opts-rework-exit-core-v1): the trail latch is REMOVED; what must survive a restart
    # is the d2* cost-basis high-water - the best realizable sell (bid) seen since entry
    led = oshadow.ShadowLedger(tmp_path)
    led.write_entry(_entry_record("T1"))
    led.write_mark(oshadow.build_mark_record(ts=ep(700), position_id="T1", occ=OCC98,
                                             bid=6.0, ask=6.1, solved_iv=0.3, S=104.0,
                                             decision_state={}, action="HOLD", rule="j_hold"))
    led.write_mark(oshadow.build_mark_record(ts=ep(705), position_id="T1", occ=OCC98,
                                             bid=4.2, ask=4.3, solved_iv=0.3, S=102.0,
                                             decision_state={}, action="HOLD", rule="j_hold"))
    pos = led.open_positions_for_day(DAY)[0]
    assert pos.peak_bid == 6.0 and pos.peak_mid == 6.05             # high-waters survive restart
    assert not hasattr(pos, "trailing")                             # the v1 latch is gone


def test_theta_breach_counter_reprimed_from_marks(tmp_path):
    # 2026-07-09 refute fix: rule (g)'s two-consecutive-cycle memory must survive a restart
    # like the trail latch - else every respawn grants a theta-dominated position a grace cycle
    led = oshadow.ShadowLedger(tmp_path)
    led.write_entry(_entry_record("G1"))
    for i, ts_share in enumerate((0.6, 0.4, 0.7, 0.8)):             # trailing run of 2 breaches
        led.write_mark(oshadow.build_mark_record(ts=ep(700 + 5 * i), position_id="G1",
                                                 occ=OCC98, bid=0.4, ask=0.5, solved_iv=0.3,
                                                 S=99.0, decision_state={"theta_share": ts_share},
                                                 action="HOLD", rule="j_hold"))
    pos = led.open_positions_for_day(DAY)[0]
    assert pos.theta_share_breaches == 2                            # consecutive tail, not total


def test_print_window_forces_flat_end_to_end(tmp_path):
    # runner wires minutes_to_next_print from the real calendar: FOMC decision at 14:00, a
    # reval at 13:52 (8 min out) must SELL with rule print_window_flat.
    ev = [EconEvent("fomc", datetime(2026, 7, 14, 14, 0, tzinfo=NY), label="decision")]
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client, events=ev)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    arm_script_lane(core, clock)
    core.positions["PW"] = oshadow.position_from_entry(_entry_record("PW"))
    client.quotes[OCC98] = tq(OCC98, 2.75, 2.85)
    clock["t"] = ep(13 * 60 + 52, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 13 * 60 + 52, 0, 100.0)})
    core.tick()
    exits = led.load_exits(DAY)
    assert len(exits) == 1 and exits[0]["rule"] == "print_window_flat"


def test_price_shock_triggers_immediate_reval(tmp_path):
    # C5 (opts-tweak-reval-triggers-v1): a violent 1-min bar on a HELD underlying marks its
    # positions NOW instead of waiting out the 5-min cadence - observability only
    client = FakeClient()
    clock = {"t": ep(585, 30)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 585, 30, 100.0)})
    arm_script_lane(core, clock)
    core.positions["P1"] = oshadow.position_from_entry(_entry_record("P1"))
    client.quotes[OCC98] = tq(OCC98, 2.75, 2.85)
    for i in range(8):                                     # calm tape builds the baseline
        clock["t"] = ep(587 + i, 0)
        core.feed.queue.append({"XYZ": tk("XYZ", 587 + i, 0, 100.0 + 0.01 * i)})
        core.tick()
    n_marks = len(led.load_marks("P1"))
    core.positions["P1"].last_mark_ts = clock["t"]         # just marked: cadence NOT due
    clock["t"] = ep(595, 0)
    core.feed.queue.append({"XYZ": tk("XYZ", 595, 0, 102.5)})   # +2.4% jump...
    core.tick()
    clock["t"] = ep(596, 0)                                     # ...whose bar completes here
    core.feed.queue.append({"XYZ": tk("XYZ", 596, 0, 102.5)})
    core.tick()
    j = [r for r in oshadow.read_jsonl(led.journal_path) if r.get("event") == "reval_trigger"]
    assert j and j[0]["kind"] == "price_shock" and j[0]["positions"] == ["P1"]
    assert len(led.load_marks("P1")) > n_marks             # marked despite the fresh cadence


# --------------------------------------------------------------------------- late-close mode
SPY_OCC = "SPY260717C00600000"


def _spy_entry_record(pid: str, bid: float = 1.00, ask: float = 1.10):
    from dataclasses import asdict
    sig = signal(underlying="SPY")
    pick = {"occ": SPY_OCC, "underlying": "SPY", "opt_type": "call", "strike": 600.0,
            "expiry": EXP, "bid": bid, "ask": ask, "S": 600.0, "theta_day": -0.15}
    return oshadow.build_entry_record(ts=ep(587), day=DAY, entry_minute=587, position_id=pid,
                                      lanes=["script"], config_hash="abc", signal=asdict(sig),
                                      pick=pick, runner_up_occs=[],
                                      nbbo={"bid": bid, "ask": ask}, risk_flags=[])


def test_after_hours_marks_frozen_S_and_60s_cadence(tmp_path):
    client = FakeClient()
    clock = {"t": ep(962)}                                 # 16:02 - after the equity close
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.tick()                                            # day armed; tick gate skips polls
    core.positions["S1"] = oshadow.position_from_entry(_spy_entry_record("S1"))
    core._last_ticks["SPY"] = tk("SPY", 959, 0, 600.5)     # the last in-session print
    client.quotes[SPY_OCC] = tq(SPY_OCC, 1.00, 1.10)
    clock["t"] = ep(962, 30)
    core.tick()
    marks = led.load_marks("S1")
    assert len(marks) == 1
    assert marks[0]["S"] == 600.5                          # frozen at the pre-close tick
    assert marks[0]["state"]["after_hours"] is True and marks[0]["rule"] == "ah_hold"
    clock["t"] = ep(963, 0)                                # +30s: under the 60s ah cadence
    core.tick()
    assert len(led.load_marks("S1")) == 1
    clock["t"] = ep(963, 45)                               # +75s: due again
    core.tick()
    assert len(led.load_marks("S1")) == 2


def test_post_close_forced_flat_for_single_names(tmp_path):
    client = FakeClient()
    clock = {"t": ep(961)}
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.tick()
    core.positions["X1"] = oshadow.position_from_entry(_entry_record("X1"))   # XYZ single name
    clock["t"] = ep(961, 30)
    core.tick()
    exits = led.load_exits(DAY)
    assert len(exits) == 1 and exits[0]["rule"] == "post_close_forced_flat"
    j = [r for r in oshadow.read_jsonl(led.journal_path)
         if r.get("event") == "late_close_quote_degraded"]
    assert j == []                                          # chain fallback quote was live
    # an occ with no quote anywhere degrades to the entry NBBO - loudly
    rec = _entry_record("X2")
    rec["pick"]["occ"] = "ZZZ260717C00100000"
    pos = oshadow.position_from_entry(rec)
    pos.underlying = "ZZZ"
    core.positions["X2"] = pos
    clock["t"] = ep(962, 30)
    core.tick()
    exits = led.load_exits(DAY)
    assert len(exits) == 2 and {e["rule"] for e in exits} == {"post_close_forced_flat"}
    j = [r for r in oshadow.read_jsonl(led.journal_path)
         if r.get("event") == "late_close_quote_degraded"]
    assert len(j) == 1 and j[0]["fallback"] == "entry_nbbo"


def test_lanes_receive_nothing_after_the_close(tmp_path):
    client = FakeClient()
    clock = {"t": ep(958)}                                 # 15:58 - still in-session
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 958, 0, 100.0)})
    lane = arm_script_lane(core, clock)
    lane.queue.append(signal())
    clock["t"] = ep(961)                                   # 16:01 - the tick gate holds
    core.feed.queue.append({"XYZ": tk("XYZ", 960, 59, 100.0)})
    core.tick()
    assert core.feed.queue                                 # poll never ran post-close
    assert lane.queue                                      # lane.update never saw a bar
    assert led.load_entries(DAY) == []


def test_premarket_bars_never_reach_lanes(tmp_path):
    # refute fix 2026-07-10: the launcher starts the shadow ~08:30 ET; premarket bars were
    # burning IndexTrendLane's one-per-side latch and priming session_open off a premarket
    # print - pre-open bars must never reach lanes or the session context
    client = FakeClient()
    clock = {"t": ep(510)}                                  # 08:30 premarket
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.feed.queue.append({"XYZ": tk("XYZ", 510, 0, 99.0)})
    lane = arm_script_lane(core, clock)
    lane.queue.append(signal())
    clock["t"] = ep(512, 0)                                 # completes the 510 premarket bar
    core.feed.queue.append({"XYZ": tk("XYZ", 512, 0, 99.5)})
    core.tick()
    assert lane.queue                                       # premarket bar never hit the lane
    assert "XYZ" not in core._session_open                  # session_open not primed premarket
    clock["t"] = ep(570, 30)                                # 09:30:30 - first RTH tick
    core.feed.queue.append({"XYZ": tk("XYZ", 570, 30, 100.0)})
    core.tick()
    clock["t"] = ep(571, 30)                                # completes the 09:30 bar
    core.feed.queue.append({"XYZ": tk("XYZ", 571, 30, 100.2)})
    core.tick()
    assert not lane.queue                                   # the RTH bar reached the lane
    assert core._session_open.get("XYZ") == 100.0           # primed from the 09:30 open


def test_single_name_overnight_grantee_not_force_flatted(tmp_path):
    # refute fix 2026-07-10: a plausible overnight grantee (DTE>=3 + named catalyst tomorrow
    # + not Friday) is NOT post_close_forced_flat - the ladder re-checks with real delta and
    # grants the ride (deep ITM here), which then carries via the cross-day rebuild
    ev = [EconEvent("cpi", datetime(2026, 7, 15, 8, 30, tzinfo=NY))]   # tomorrow's print
    client = FakeClient()
    clock = {"t": ep(961)}
    core, led = make_core(tmp_path, clock=clock, client=client, events=ev)
    core.tick()
    core.positions["OG"] = oshadow.position_from_entry(_entry_record("OG"))  # XYZ, DTE 3
    core._last_ticks["XYZ"] = tk("XYZ", 959, 0, 110.0)      # deep ITM vs strike 98
    client.quotes[OCC98] = tq(OCC98, 12.0, 12.2)
    clock["t"] = ep(961, 30)
    core.tick()
    assert led.load_exits(DAY) == []                        # NOT forced flat
    marks = led.load_marks("OG")
    assert marks and marks[-1]["rule"] == "overnight_grant_hold"
    # without the catalyst, the anomaly path still forces exactly as before
    core2, led2 = make_core(tmp_path / "noev", clock={"t": ep(961)}, client=client)
    core2.tick()
    core2.positions["NG"] = oshadow.position_from_entry(_entry_record("NG"))
    core2.tick()
    exits2 = led2.load_exits(DAY)
    assert len(exits2) == 1 and exits2[0]["rule"] == "post_close_forced_flat"


def test_restart_after_close_recovers_and_flattens(tmp_path):
    led0 = oshadow.ShadowLedger(tmp_path)
    led0.write_entry(_spy_entry_record("SPY1"))
    led0.write_entry(_entry_record("XYZ1"))
    client = FakeClient()
    client.quotes[SPY_OCC] = tq(SPY_OCC, 1.00, 1.10)
    clock = {"t": ep(965)}                                 # 16:05 - fresh process post-close
    core, led = make_core(tmp_path, clock=clock, client=client)
    core.tick()
    assert [e["rule"] for e in led.load_exits(DAY)] == ["post_close_forced_flat"]  # XYZ anomaly
    assert "SPY1" in core.positions                        # SPY rides the late-close window
    assert len(led.load_marks("SPY1")) == 1                # S-free ah mark (no backfill: S=0)
    clock["t"] = ep(971)                                   # 16:11 - past the close+10 cap
    core.tick()
    assert {e["rule"] for e in led.load_exits(DAY)} == {"post_close_forced_flat",
                                                        "late_close_flat"}
    assert core.positions == {}


# --------------------------------------------------------------------------- runner utilities
def test_load_shadow_config_defaults_and_hash_stability():
    cfg = load_shadow_config()
    for k in DEFAULTS:
        assert k in cfg
    assert config_hash(cfg) == config_hash(dict(cfg))
    assert config_hash(cfg) != config_hash({**cfg, "max_concurrent": 99})


def test_tradier_from_yaml_tolerates_bom_and_nested_shape(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_bytes(b"\xef\xbb\xbf# comment\ntradier:\n  token: abc123\n  env: production\n")
    c = tradier_from_yaml(p)
    assert c is not None
    c.close()
    p2 = tmp_path / "t2.yaml"
    p2.write_text("token: xyz789\n", encoding="utf-8")
    c2 = tradier_from_yaml(p2)
    assert c2 is not None
    c2.close()
    p3 = tmp_path / "t3.yaml"
    p3.write_text("tradier:\n  env: production\n", encoding="utf-8")
    assert tradier_from_yaml(p3) is None                           # no token -> None, no raise
    assert tradier_from_yaml(tmp_path / "absent.yaml") is None


def test_load_hunt_list_tolerant_shapes(tmp_path):
    p = tmp_path / "hunt_list.json"
    p.write_text(json.dumps({"symbols": [{"symbol": "abcd", "gap_pct": 7.5},
                                         "efgh", {"nosym": 1}]}), encoding="utf-8")
    rows, sd = load_hunt_list(p)
    assert sd is None                                       # no session_date in this shape
    assert rows == [{"symbol": "ABCD", "gap_pct": 7.5, "catalyst": True, "catalyst_kind": None},
                    {"symbol": "EFGH", "gap_pct": 0.0, "catalyst": True, "catalyst_kind": None}]
    # the research crew's ACTUAL output shape (2026-07-09 fix): {"candidates": [...]} +
    # session_date, which the caller uses for the freshness contract (audit RUNNER-4)
    crew = tmp_path / "crew.json"
    crew.write_text(json.dumps({"schema": 1, "session_date": "2026-07-14", "candidates": [
        {"symbol": "NEWG", "catalyst_kind": "fda", "summary": "x", "confidence": 0.8}]}),
        encoding="utf-8")
    # catalyst_kind is now RETAINED (opts-catalyst-kind-covariate-v1) - the bool `catalyst` (lane-2
    # gating) is preserved alongside it; the kind was previously dropped by the lossy loader
    crew_rows, crew_sd = load_hunt_list(crew)
    assert crew_sd == "2026-07-14"
    assert crew_rows == [{"symbol": "NEWG", "gap_pct": 0.0, "catalyst": True,
                          "catalyst_kind": "fda"}]
    assert load_hunt_list(tmp_path / "absent.json") == ([], None)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_hunt_list(bad) == ([], None)
    # refute fix 2026-07-10: one malformed row (machine-authored file) never disarms the day
    badrow = tmp_path / "badrow.json"
    badrow.write_text(json.dumps({"candidates": [{"symbol": "DAL", "gap_pct": "n/a"},
                                                 {"symbol": "OK"}]}), encoding="utf-8")
    assert load_hunt_list(badrow)[0] == [{"symbol": "OK", "gap_pct": 0.0, "catalyst": True,
                                          "catalyst_kind": None}]
