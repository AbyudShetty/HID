"""E2 statistics on synthetic tables with KNOWN structure (not liveness evidence)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.e2_stats import (  # noqa: E402
    apcer_by_species,
    auc,
    cluster_bootstrap_auc,
    evaluate_go,
    loso_scores,
    operating_point,
    usable_columns,
)


def table(separation, n_subj=5, per=12, seed=0):
    rng = np.random.default_rng(seed)
    X, y, subj = [], [], []
    for s in range(n_subj):
        for label in (1, 0):
            for _ in range(per):
                X.append(rng.normal(separation * label, 1.0, 3))
                y.append(label)
                subj.append(f"S{s}")
    return np.array(X), np.array(y), np.array(subj)


def test_auc_known_values():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1, 1], [1, 1]) == 0.5
    assert auc([], [1]) is None


def test_separable_data_gives_high_loso_auc_and_inseparable_gives_chance():
    X, y, s = table(3.0)
    sc = loso_scores(X, y, s)
    assert auc(sc[y == 1], sc[y == 0]) > 0.95
    X0, y0, s0 = table(0.0)
    sc0 = loso_scores(X0, y0, s0)
    assert 0.35 < auc(sc0[y0 == 1], sc0[y0 == 0]) < 0.65


def test_loso_scores_every_session_with_a_model_that_never_saw_that_subject():
    X, y, s = table(2.0, n_subj=4)
    base = loso_scores(X, y, s)
    assert not np.isnan(base).any()
    X2 = X.copy()
    X2[s == "S0"] += 100.0  # corrupt only S0
    changed = loso_scores(X2, y, s)
    # other subjects are scored by models that DID train on S0, so their scores move
    assert not np.allclose(changed[s == "S1"], base[s == "S1"])
    # a subject's own labels must NOT influence that subject's scores (the model never saw them)
    y_flipped = y.copy()
    y_flipped[s == "S0"] = 1 - y_flipped[s == "S0"]
    assert np.allclose(loso_scores(X, y_flipped, s)[s == "S0"], base[s == "S0"])


def test_cluster_bootstrap_ci_brackets_the_estimate_and_is_wider_with_fewer_subjects():
    X, y, s = table(1.5, n_subj=8)
    sc = loso_scores(X, y, s)
    est = auc(sc[y == 1], sc[y == 0])
    lo, hi = cluster_bootstrap_auc(sc, y, s, n_boot=500)
    assert lo <= est <= hi
    X3, y3, s3 = table(1.5, n_subj=3)
    sc3 = loso_scores(X3, y3, s3)
    lo3, hi3 = cluster_bootstrap_auc(sc3, y3, s3, n_boot=500)
    assert (hi3 - lo3) > (hi - lo)
    assert cluster_bootstrap_auc([1, 2], [1, 0], ["a", "a"]) is None  # fewer than 3 subjects


def test_operating_point_controls_bpcer_and_apcer_is_per_species():
    bona = np.linspace(0, 1, 100)
    thr = operating_point(bona, 0.10)
    assert (bona < thr).mean() <= 0.10 + 1e-9
    out = apcer_by_species([0.95, 0.2, 0.3, 0.99], ["a", "a", "b", "b"], 0.9)
    assert out["a"] == {"n": 2, "apcer": 0.5, "accepted": 1}
    assert out["b"]["apcer"] == 0.5


def test_usable_columns_drops_features_with_any_missing_value():
    rows = [{"features": {"x": 1.0, "y": None}}, {"features": {"x": 2.0, "y": 3.0}}]
    assert usable_columns(rows, ["x", "y", "z"]) == ["x"]


BASE = dict(auc_screen=0.97, auc_print=0.93, apcer_species=0.05, ok_rate=0.95, ok_rate_min_subject=0.92, capture_ms=1220, n_subjects=5)


def test_go_partial_nogo_and_insufficient_follow_the_plan_rules():
    assert evaluate_go(BASE)["outcome"] == "GO"
    assert evaluate_go({**BASE, "auc_print": 0.8})["outcome"] == "PARTIAL-GO"
    assert evaluate_go({**BASE, "dim_only": True})["outcome"] == "PARTIAL-GO"
    assert evaluate_go({**BASE, "auc_screen": 0.80})["outcome"] == "NO-GO"
    assert evaluate_go({**BASE, "ok_rate": 0.7})["outcome"] == "NO-GO"
    assert evaluate_go({**BASE, "auc_screen": 0.90})["outcome"] == "INCONCLUSIVE"
    assert evaluate_go({**BASE, "capture_ms": 1400})["outcome"] != "GO"
    assert evaluate_go({**BASE, "n_subjects": 2})["outcome"] == "INSUFFICIENT_DATA"
    assert evaluate_go({**BASE, "auc_screen": None})["outcome"] == "INSUFFICIENT_DATA"
    with pytest.raises(KeyError):
        evaluate_go({"n_subjects": 5, "auc_screen": 0.99})


def _load_analyze():
    import importlib.util

    spec = importlib.util.spec_from_file_location("e2_analyze", Path(__file__).resolve().parents[2] / "experiments" / "E2_chroma" / "analyze.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows(separation, n_subj=5, per=8, ok_rate=1.0, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_subj):
        for cls, fam, sp in (("bona_fide", "none", "none"), ("attack", "screen_photo", "screen_phone_oled"), ("attack", "print", "print_matte_a4")):
            for _ in range(per):
                shift = separation if cls == "bona_fide" else 0.0
                rows.append({
                    "session": f"{s}-{cls}-{sp}-{len(rows)}", "subject": f"S{s}", "cls": cls, "family": fam, "species": sp, "lighting": "office",
                    "palette": "P1", "status": "ok" if rng.random() < ok_rate else "unavailable", "capture_ms": 1220,
                    "features": {"gain_face": float(rng.normal(shift, 1)), "falloff_bg": float(rng.normal(shift, 1)), "fit_r2": float(rng.normal(0, 1))},
                })
    return rows


def test_analysis_end_to_end_on_synthetic_rows_reaches_go_when_separable():
    res = _load_analyze().analyse(_rows(4.0))
    assert res["go"]["outcome"] == "GO", res["go"]
    assert res["auc_screen"]["auc"] > 0.95 and res["auc_screen"]["ci95_cluster_bootstrap"] is not None
    assert set(res["apcer_by_species_at_bpcer10"]) == {"screen_phone_oled", "print_matte_a4"}
    assert res["features_used"] == ["falloff_bg", "fit_r2", "gain_face"]


def test_analysis_reports_no_go_when_nothing_separates_and_insufficient_with_two_subjects():
    assert _load_analyze().analyse(_rows(0.0))["go"]["outcome"] in {"NO-GO", "INCONCLUSIVE"}
    assert _load_analyze().analyse(_rows(4.0, n_subj=2))["go"]["outcome"] == "INSUFFICIENT_DATA"


def test_unusable_sessions_count_against_the_usable_rate_not_the_auc():
    res = _load_analyze().analyse(_rows(4.0, ok_rate=0.6))
    assert res["ok_rate_bona_fide"] < 0.9 and res["go"]["outcome"] == "NO-GO"
