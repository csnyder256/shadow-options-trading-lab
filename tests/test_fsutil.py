"""Tests for atlas.fsutil.atomic_replace - the Windows sharing-violation-safe os.replace that fixes the
2026-07-01 WinError-5 crash (an unguarded os.replace of synthetic_stops.json took the live session down)."""
from __future__ import annotations

import os

import pytest

import atlas.fsutil as fsutil


class _WinErr(PermissionError):
    def __init__(self, winerror):
        super().__init__(f"simulated winerror {winerror}")
        self.winerror = winerror


def test_happy_path_replaces(tmp_path):
    src = tmp_path / "a.tmp"; dst = tmp_path / "a.json"
    src.write_text("x", encoding="utf-8")
    fsutil.atomic_replace(src, dst)
    assert dst.read_text(encoding="utf-8") == "x" and not src.exists()


def test_retries_transient_sharing_violation_then_succeeds(tmp_path, monkeypatch):
    real = os.replace
    calls = {"n": 0}

    def flaky(s, d):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _WinErr(32)          # ERROR_SHARING_VIOLATION on the first two attempts
        return real(s, d)

    monkeypatch.setattr(fsutil.os, "replace", flaky)
    monkeypatch.setattr(fsutil.time, "sleep", lambda *_: None)
    src = tmp_path / "b.tmp"; dst = tmp_path / "b.json"
    src.write_text("y", encoding="utf-8")
    fsutil.atomic_replace(src, dst, retries=5)
    assert calls["n"] == 3 and dst.read_text(encoding="utf-8") == "y"


def test_non_sharing_permissionerror_reraises_immediately(tmp_path, monkeypatch):
    slept = {"n": 0}
    monkeypatch.setattr(fsutil.os, "replace", lambda s, d: (_ for _ in ()).throw(_WinErr(13)))
    monkeypatch.setattr(fsutil.time, "sleep", lambda *_: slept.__setitem__("n", slept["n"] + 1))
    with pytest.raises(PermissionError):
        fsutil.atomic_replace(tmp_path / "c.tmp", tmp_path / "c.json", retries=5)
    assert slept["n"] == 0              # winerror 13 is not a sharing race -> never retried


def test_exhausts_retry_budget_then_reraises(tmp_path, monkeypatch):
    monkeypatch.setattr(fsutil.os, "replace", lambda s, d: (_ for _ in ()).throw(_WinErr(5)))
    monkeypatch.setattr(fsutil.time, "sleep", lambda *_: None)
    with pytest.raises(PermissionError):
        fsutil.atomic_replace(tmp_path / "d.tmp", tmp_path / "d.json", retries=3)
