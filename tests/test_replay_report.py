import copy
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from atlas.options import exit_engine
from atlas.options.replay import replay_decide_exit
from atlas.options.replay_demo import demo_history
from atlas.options.replay_report import build_report, main, report_csv, report_html, write_report


def demo(**kw):
    return build_report(*demo_history(), label="Fictional XYZ", fictional=True, **kw)


def test_actual_decisions_fees_and_open_coverage():
    r = demo(fee_per_contract=.65)
    winner = next(p for p in r["positions"] if p["position_id"]=="winner")
    assert winner["variants"]["current"]["result"]["rule"]=="overnight_evidence_rule"
    assert winner["variants"]["frozen_v1"]["result"]["rule"]=="d_take_profit"
    assert winner["variants"]["frozen_v1"]["net_after_fees"]==133.7
    assert len(winner["variants"]["frozen_v1"]["trace"])==1
    assert winner["variants"]["frozen_v1"]["exit_ts"] < winner["variants"]["current"]["exit_ts"]
    for p in r["positions"]:
        for v in p["variants"].values():
            if v["status"]!="closed":
                assert v["net_after_fees"] is None and v["exit_ts"] is None
    assert r["summary"]["current"]["open"]==1
    assert r["summary"]["current"]["unreplayable"]==1
    assert r["summary"]["current"]["closed"]==2
    assert len(r["paired_closed_comparisons"])==2
    assert r["summary"]["current"]["realized_net_sum"]==122.4


def test_trace_does_not_change_replay_or_consume_future_marks():
    entries,quotes=demo_history();e=entries[0];path=[q for q in quotes if q["position_id"]==e["position_id"]]
    trace=[]
    old=replay_decide_exit(e,path,engine=exit_engine,params=exit_engine.ExitParams())
    new=replay_decide_exit(e,list(reversed(path)),engine=exit_engine,params=exit_engine.ExitParams(),trace=trace)
    assert old==new
    assert len(trace)==new["marks_replayed"]
    assert trace[-1]["decision"]["action"]=="SELL"
    assert trace[0]["inputs"]["peak_bid"]==2.3
    assert trace[0]["ts_epoch"]<trace[-1]["ts_epoch"]


def test_engine_error_remains_visible_without_exit_or_exception_details():
    entries,quotes=demo_history()
    def fail(*_):
        raise RuntimeError("credential-that-must-not-enter-report")
    engine=SimpleNamespace(PositionView=exit_engine.PositionView,SELL="SELL",decide_exit=fail)
    r=build_report(entries,quotes,label="error",variants=[("fails",engine,exit_engine.ExitParams())])
    assert r["summary"]["fails"]["closed"]==0
    assert r["summary"]["fails"]["engine_errors"]>0
    assert "credential-that-must-not-enter-report" not in json.dumps(r)
    assert next(p for p in r["positions"] if p["position_id"]=="winner")["variants"]["fails"]["status"]=="open"


@pytest.mark.parametrize("change",[
    lambda e,q:e[0].update(contracts=0),
    lambda e,q:e[0].update(contracts=1.5),
    lambda e,q:e[0]["nbbo"].update(bid=10),
    lambda e,q:e[0]["fills"].update(worst=99),
    lambda e,q:e[0]["pick"].update(strike=float("nan")),
    lambda e,q:e[0]["pick"].update(opt_type="stock"),
    lambda e,q:q[0].update(position_id="orphan"),
    lambda e,q:q[0].update(occ="wrong"),
    lambda e,q:q[0].update(ts_epoch=e[0]["ts_epoch"]-1),
    lambda e,q:q.append(copy.deepcopy(q[0])),
    lambda e,q:q[0]["ext"].pop("thesis_valid"),
    lambda e,q:q[0]["ext"].update(thesis_valid="false"),
    lambda e,q:q[0]["ext"].update(minute=1),
    lambda e,q:q[0].update(S=float("inf")),
])
def test_corrupt_or_lookahead_inputs_fail_closed(change):
    e,q=demo_history();change(e,q)
    with pytest.raises(ValueError):
        build_report(e,q,label="invalid")


def test_reproducibility_hashes_and_private_notes_omission():
    e,q=demo_history();a=build_report(e,q,label="recorded")
    assert a==build_report(e,list(q),label="recorded")
    assert len(a["configuration_sha256"])==64
    e[0]["signal"]["notes"]["secret"]="unrelated-private-note"
    b=build_report(e,q,label="recorded")
    assert a["dataset"]["entries_sha256"]!=b["dataset"]["entries_sha256"]
    assert "unrelated-private-note" not in json.dumps(b)
    assert all(len(v)==64 for v in b["source_sha256"].values())


def test_portable_html_escapes_data_and_bundle_checksums(tmp_path):
    r=demo();r["dataset"]["label"]='</script><script>alert(1)</script> __JS__'
    html=report_html(r)
    assert r["dataset"]["label"] not in html
    assert "\\u003c/script\\u003e" in html
    assert "connect-src 'none'" in html
    assert "__JS__" in html  # stays inert data; never replaced with application code
    write_report(r,tmp_path/"report")
    assert {p.name for p in (tmp_path/"report").iterdir()}=={"index.html","report.json","positions.csv","manifest.json"}
    assert json.loads((tmp_path/"report/report.json").read_text())==r
    with pytest.raises(FileExistsError):
        write_report(r,tmp_path/"report")
    rows=list(csv.DictReader(io.StringIO(report_csv(r))))
    assert len(rows)==8 and any(row["net_after_fees"]=="" for row in rows)


def test_cli_demo_and_recorded_jsonl_share_same_engine(tmp_path):
    assert main(["--demo","--output",str(tmp_path/"demo")])==0
    e,q=demo_history()
    ep,qp=tmp_path/"entry.jsonl",tmp_path/"quote.jsonl"
    ep.write_text("".join(json.dumps(x)+"\n" for x in e))
    qp.write_text("".join(json.dumps(x)+"\n" for x in q))
    assert main(["--entries",str(ep),"--quotes",str(qp),"--output",str(tmp_path/"recorded")])==0
    a=json.loads((tmp_path/"demo/report.json").read_text());b=json.loads((tmp_path/"recorded/report.json").read_text())
    assert a["summary"]==b["summary"] and a["positions"]==b["positions"]
    assert a["dataset"]["fictional"] is True and b["dataset"]["fictional"] is False


def test_contract_quantity_scales_realized_dollars_and_fees():
    entries, quotes = demo_history()
    a = build_report(entries, quotes, label="one", fee_per_contract=.65)
    entries[0]["contracts"] = 3
    b = build_report(entries, quotes, label="three", fee_per_contract=.65)
    for name in a["summary"]:
        one = next(p for p in a["positions"] if p["position_id"] == "winner")["variants"][name]
        three = next(p for p in b["positions"] if p["position_id"] == "winner")["variants"][name]
        assert three["net_after_fees"] == round(3 * one["net_after_fees"], 2)
        assert three["result"]["net_worst"] == 3 * one["result"]["net_worst"]
        assert three["trace"] == one["trace"]
    assert b["environment"]["python"] and b["environment"]["numpy"]
