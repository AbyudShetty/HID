"""E2 chroma-feasibility statistics (plan section 9.6). Pure functions, tested on synthetic tables in
backend/tests/test_e2_stats.py.

Honest-statistics choices (documented, not hidden):
  * AUC confidence intervals use a CLUSTER bootstrap over subjects (sessions of one person are not independent).
  * Scores are leave-one-subject-out (LOSO): every session is scored by a model that never saw that person.
  * Sessions whose chroma status is not ok are not scored; they count against the usable-session criterion (d).
  * Missing feature values inside ok sessions drop the feature column; nothing is imputed.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Descriptive/diagnostic values that are not model features (plan 9.5 keeps lag_err_ms, drops lag_ms).
EXCLUDE = {"lag_ms", "noise", "interval_std_ms", "max_gap_ms", "fps", "neutral_drift", "max_segment_drift", "ambient_level", "motion_frac"}
SCREEN_FAMILIES = {"screen_photo", "video_replay"}
MIN_SUBJECTS = 3


def auc(pos, neg) -> float | None:
    """P(score_pos > score_neg) + 0.5 * P(tie). pos = bona fide."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    diff = pos[:, None] - neg[None, :]
    return float(((diff > 0).sum() + 0.5 * (diff == 0).sum()) / diff.size)


def cluster_bootstrap_auc(scores, labels, subjects, n_boot: int = 2000, seed: int = 0):
    """95 percent CI for AUC, resampling SUBJECTS with replacement. None if too few subjects or classes."""
    scores, labels, subjects = np.asarray(scores, float), np.asarray(labels, int), np.asarray(subjects)
    uniq = np.unique(subjects)
    if len(uniq) < MIN_SUBJECTS:
        return None
    rng = np.random.default_rng(seed)
    by = {u: np.where(subjects == u)[0] for u in uniq}
    vals = []
    for _ in range(n_boot):
        idx = np.concatenate([by[u] for u in rng.choice(uniq, len(uniq))])
        a = auc(scores[idx][labels[idx] == 1], scores[idx][labels[idx] == 0])
        if a is not None:
            vals.append(a)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if len(vals) > 50 else None


def usable_columns(rows: list[dict], names: list[str]) -> list[str]:
    return [n for n in names if all(isinstance(r["features"].get(n), (int, float)) for r in rows)]


def loso_scores(X: np.ndarray, y: np.ndarray, subjects: np.ndarray, C: float = 1.0) -> np.ndarray:
    """Leave-one-subject-out decision values (higher = more bona fide). NaN where a training fold lacks a class."""
    out = np.full(len(y), np.nan)
    for s in np.unique(subjects):
        test = subjects == s
        train = ~test
        if len(np.unique(y[train])) < 2:
            continue
        sc = StandardScaler().fit(X[train])
        clf = LogisticRegression(C=C, class_weight="balanced", max_iter=2000).fit(sc.transform(X[train]), y[train])
        out[test] = clf.decision_function(sc.transform(X[test]))
    return out


def operating_point(scores_bona, bpcer_max: float = 0.10) -> float:
    """Largest threshold whose BPCER (bona fide scored below it) is at most bpcer_max. A session passes if score >= thr."""
    s = np.sort(np.asarray(scores_bona, float))
    k = int(np.floor(bpcer_max * len(s)))
    return float(s[k]) if k < len(s) else float(s[-1])


def apcer_by_species(scores, species, thr: float) -> dict[str, dict]:
    out = {}
    for sp in sorted(set(species)):
        v = np.asarray([x for x, y in zip(scores, species, strict=True) if y == sp], float)
        out[sp] = {"n": int(len(v)), "apcer": float((v >= thr).mean()), "accepted": int((v >= thr).sum())}
    return out


def evaluate_go(m: dict) -> dict:
    """Plan 9.6 E2 decision. Keys of m: auc_screen, auc_print, apcer_species (max over tested species), ok_rate,
    ok_rate_min_subject, capture_ms, n_subjects, optional dim_only (passes only in dim light)."""
    if m.get("n_subjects", 0) < MIN_SUBJECTS or m.get("auc_screen") is None:
        return {"outcome": "INSUFFICIENT_DATA", "criteria": {}, "why": f"needs >= {MIN_SUBJECTS} subjects with bona fide and screen/replay sessions"}
    a = m["auc_screen"] >= 0.95
    b = m.get("auc_print") is not None and m["auc_print"] >= 0.90
    c = m.get("apcer_species") is not None and m["apcer_species"] <= 0.10
    d = m["ok_rate"] >= 0.90 and m["ok_rate_min_subject"] >= 0.90
    e = m["capture_ms"] <= 1300
    crit = {"a_auc_screen_ge_0.95": a, "b_auc_print_ge_0.90": b, "c_apcer_le_10pct_every_species": c,
            "d_ok_status_ge_90pct_every_subject": d, "e_window_le_1300ms": e}
    if m["auc_screen"] < 0.85 or not d:
        outcome = "NO-GO"
    elif all(crit.values()) and not m.get("dim_only"):
        outcome = "GO"
    elif a and (not b or m.get("dim_only")):
        outcome = "PARTIAL-GO"
    else:
        outcome = "INCONCLUSIVE"  # e.g. 0.85 <= AUC(screen) < 0.95, or capture window / APCER misses: neither GO nor NO-GO
    return {"outcome": outcome, "criteria": crit}
