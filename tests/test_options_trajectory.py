"""trajectory.py (opts-rework-exit-core-v1): the live drift estimator + the evidence-gated
shrinkage blend (CALIBRATION-class heuristic - label corrected 2026-07-10; see trajectory.py's
LABEL CORRECTION note) - causality, no-view failure modes, window selection, sign conventions."""

from __future__ import annotations

from atlas.options.trajectory import UnderlyingState, mu_blend, mu_blend_shrink, underlying_state


def _series(start_min: int, closes: list[float]) -> tuple[list[int], list[float]]:
    return list(range(start_min, start_min + len(closes))), closes


def test_no_view_on_thin_history_and_bad_inputs():
    m, c = _series(600, [100.0, 100.1])
    assert underlying_state(m, c, iv=0.3).mu_hat is None            # < max(3, k//2) bars
    assert underlying_state([], [], iv=0.3).mu_hat is None
    m, c = _series(600, [100.0] * 25)
    assert underlying_state(m, c, iv=0.0).mu_hat is None            # degenerate IV sentinel
    assert underlying_state(m, c, iv=1e-4).mu_hat is None
    # audit 2026-07-16 Wave 2.15 (TRAJECTORY-3): ONE bad endpoint print is medianed away - 
    # the estimator keeps its view instead of dying on a single anomalous tick
    bad_one = underlying_state(m, c[:-1] + [0.0], iv=0.3)
    assert bad_one.mu_hat == 0.0 and bad_one.t_stat == 0.0          # flat series, robust endpoint
    # ...but a genuinely broken tail (median of the last 3 non-positive) still fails to no-view
    bad_all = underlying_state(m, c[:-3] + [0.0, 0.0, 0.0], iv=0.3)
    assert bad_all.mu_hat is None and bad_all.t_stat == 0.0


def test_drift_sign_and_magnitude():
    # +1% over 20 minutes, iv 0.30: mu_hat = ln(1.01)/T_K, t = ln(1.01)/(iv*sqrt(T_K))
    closes = [100.0 + 0.05 * i for i in range(21)]
    m, c = _series(600, closes)
    st = underlying_state(m, c, iv=0.30, window_min=20)
    assert st.mu_hat is not None and st.mu_hat > 0
    assert st.t_stat > 1.0                                          # a real 20-min trend is >1 sigma
    down = underlying_state(m, list(reversed(closes)), iv=0.30, window_min=20)
    assert down.mu_hat < 0 and down.t_stat < -1.0
    flat = underlying_state(m, [100.0] * 21, iv=0.30, window_min=20)
    assert flat.mu_hat == 0.0 and flat.t_stat == 0.0 and flat.er == 0.0


def test_window_excludes_older_bars():
    # a violent morning far outside the window must not leak into the estimate
    early = [90.0 + i for i in range(10)]                           # huge old move (09:30-09:39)
    late = [100.0] * 21                                             # dead-flat trailing 20 min
    mins = list(range(570, 580)) + list(range(700, 721))
    st = underlying_state(mins, early + late, iv=0.30, window_min=20)
    assert st.mu_hat == 0.0 and st.n_bars == 21


def test_er_bounded_and_monotone_path_dependence():
    m, c = _series(600, [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0,
                         104.5, 105.0])
    st = underlying_state(m, c, iv=0.30, window_min=10)
    assert 0.99 <= st.er <= 1.0                                     # perfectly efficient trend
    zig = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.5]
    st2 = underlying_state(m, zig, iv=0.30, window_min=10)
    assert st2.er < 0.2                                             # chop: tiny net, long path


def test_mu_blend_unit_information_posterior():
    assert mu_blend(None, 99.0, 2.5) == 2.5                         # no view -> prior untouched
    assert abs(mu_blend(-6.0, 1.0, 2.0) - (-2.0)) < 1e-12           # t=1 -> 50/50
    assert abs(mu_blend(-6.0, 2.0, 2.0) - (-4.4)) < 1e-12           # t=2 -> 80/20
    assert abs(mu_blend(10.0, 0.0, -3.0) - (-3.0)) < 1e-12          # t=0 -> prior only
    # symmetric in |t|: adverse and favorable evidence weigh identically
    assert abs(mu_blend(4.0, -2.0, 0.0) - mu_blend(4.0, 2.0, 0.0)) < 1e-12


def test_mu_blend_shrink_variance_scaled():
    """audit 2026-07-16 Wave 2.15 (TRAJECTORY-1, 4/4 refuters): the LIVE blend is the
    normal-normal posterior mean w = tau^2/(tau^2 + SE^2), SE = |mu_hat/t| - a 20-min noise
    drift (SE ~ 14/yr) can no longer take 50% weight against an O(1) thesis scale."""
    assert mu_blend_shrink(None, 99.0, 2.5, tau=1.0) == 2.5          # no view -> prior untouched
    assert mu_blend_shrink(10.0, 0.0, -3.0, tau=1.0) == -3.0         # zero evidence -> prior
    assert mu_blend_shrink(10.0, 1.0, -3.0, tau=0.0) == -3.0         # degenerate tau -> prior
    # mu_hat=-6, t=-1 -> SE=6; tau=6 -> w = 36/72 = 0.5 -> blend of -6 and prior 2 = -2
    assert abs(mu_blend_shrink(-6.0, -1.0, 2.0, tau=6.0) - (-2.0)) < 1e-12
    # same estimate against a SMALL thesis scale (tau=1): w = 1/37 -> barely moves the prior
    out = mu_blend_shrink(-6.0, -1.0, 2.0, tau=1.0)
    assert abs(out - (2.0 + (1.0 / 37.0) * (-8.0))) < 1e-12 and out > 1.7
    # the noise-clock case the audit proved: SE ~ 14 vs tau ~ 1 -> w ~ 0.005 (was 0.5 at t=1)
    w_eff = (1.0 / (1.0 + 14.0 ** 2))
    got = mu_blend_shrink(14.0, 1.0, 1.0, tau=1.0)
    assert abs(got - (w_eff * 14.0 + (1 - w_eff) * 1.0)) < 1e-12 and got < 1.08
