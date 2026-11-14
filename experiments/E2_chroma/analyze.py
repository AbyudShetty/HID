"""E2 analysis over recorded labelled bundles (plan section 9.6). Uses the PRODUCTION instrument and feature code.

    .venv\\Scripts\\python.exe experiments\\E2_chroma\\analyze.py --sessions data\\sessions [--lighting office]

Per session: SCRFD + region means + chroma features (cached in data/features/). Then: per-feature univariate AUC, leave-one-subject-out
logistic regression, subject-cluster bootstrap CIs, the BPCER <= 10 percent operating point, APCER per species, usable-session rates,
and the GO / PARTIAL-GO / NO-GO decision of the plan. Writes experiments/E2_chroma/results.json and report.md.

NOT implemented here (reported as such, never silently skipped): window truncation ablation, JPEG-vs-PNG comparison, palette P1 vs P2
split beyond the per-palette session counts. With fewer than 3 subjects the outcome is INSUFFICIENT_DATA by design.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.challenge.sequence import ChallengeConfig  # noqa: E402
from app.config import Settings, load_policy  # noqa: E402
from app.model_registry import verify_models  # noqa: E402
from app.pipeline.bundle_io import BundleError, build_bundle, read_entries  # noqa: E402
from app.pipeline.chroma_instrument import ChromaInstrument  # noqa: E402
from eval.e2_stats import (  # noqa: E402
    EXCLUDE,
    SCREEN_FAMILIES,
    apcer_by_species,
    auc,
    cluster_bootstrap_auc,
    evaluate_go,
    loso_scores,
    operating_point,
    usable_columns,
)


def load_rows(sessions: Path, cache: Path, instrument: ChromaInstrument, cfg: ChallengeConfig) -> tuple[list[dict], list[str]]:
    rows, problems = [], []
    cache.mkdir(parents=True, exist_ok=True)
    for d in sorted(p for p in sessions.iterdir() if p.is_dir()):
        cf = cache / f"{d.name}.json"
        try:
            entries = read_entries(d)
            bundle = build_bundle(entries)
        except BundleError as exc:
            problems.append(f"{d.name}: {exc}")
            continue
        if bundle.label is None:
            problems.append(f"{d.name}: no label.json (skipped)")
            continue
        if cf.exists():
            res = json.loads(cf.read_text(encoding="utf-8"))
        else:
            res = instrument.analyze(bundle, entries, cfg)
            res.pop("observations", None)  # keep the cache small; features are what E2 needs
            cf.write_text(json.dumps(res), encoding="utf-8")
        lab = bundle.label
        rows.append({
            "session": d.name, "subject": lab.subject_id, "cls": lab.cls, "family": lab.pai_family, "species": lab.pai_species,
            "lighting": lab.lighting, "palette": bundle.meta.palette_id, "status": res["status"], "features": res["features"],
            "capture_ms": bundle.challenge.timing.capture_end_ms if bundle.challenge.timing else None,
        })
    return rows, problems


def analyse(rows: list[dict], names: list[str] | None = None) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    subjects = sorted({r["subject"] for r in rows})
    bona_all = [r for r in rows if r["cls"] == "bona_fide"]
    out: dict = {"n_sessions": len(rows), "n_ok": len(ok), "subjects": len(subjects), "palette_counts": Counter(r["palette"] for r in rows),
                 "by_class": Counter(r["cls"] for r in rows), "by_species": Counter(r["species"] for r in rows if r["cls"] == "attack")}
    out["ok_rate"] = len(ok) / len(rows) if rows else 0.0
    per_subject = defaultdict(lambda: [0, 0])
    for r in bona_all:
        per_subject[r["subject"]][0] += r["status"] == "ok"
        per_subject[r["subject"]][1] += 1
    out["ok_rate_bona_fide_by_subject"] = {s: a / b for s, (a, b) in per_subject.items()}
    out["ok_rate_bona_fide"] = (sum(a for a, _ in per_subject.values()) / max(1, sum(b for _, b in per_subject.values())))
    out["ok_rate_min_subject"] = min(out["ok_rate_bona_fide_by_subject"].values(), default=0.0)

    all_names = sorted({k for r in ok for k in r["features"] if k not in EXCLUDE})
    cols = usable_columns(ok, names or all_names)
    out["features_used"], out["features_dropped_missing"] = cols, sorted(set(all_names) - set(cols))
    if len({r["cls"] for r in ok}) < 2 or not cols:
        out["note"] = "need ok sessions of both classes and at least one defined feature"
        out["go"] = evaluate_go({"n_subjects": len(subjects), "auc_screen": None})
        return out

    X = np.array([[r["features"][c] for c in cols] for r in ok], float)
    y = np.array([1 if r["cls"] == "bona_fide" else 0 for r in ok])
    subj = np.array([r["subject"] for r in ok])
    scores = loso_scores(X, y, subj)
    out["univariate_auc_vs_all_attacks"] = {c: auc(X[y == 1, i], X[y == 0, i]) for i, c in enumerate(cols)}

    def pair_auc(match) -> dict | None:
        idx = [i for i, r in enumerate(ok) if r["cls"] == "bona_fide" or match(r)]
        sc, lb, sj = scores[idx], y[idx], subj[idx]
        keep = ~np.isnan(sc)
        if not (lb[keep] == 0).any() or not (lb[keep] == 1).any():
            return None
        a = auc(sc[keep][lb[keep] == 1], sc[keep][lb[keep] == 0])
        return {"auc": a, "ci95_cluster_bootstrap": cluster_bootstrap_auc(sc[keep], lb[keep], sj[keep]), "n_attack": int((lb[keep] == 0).sum()), "n_bona_fide": int((lb[keep] == 1).sum())}

    out["auc_screen"] = pair_auc(lambda r: r["family"] in SCREEN_FAMILIES)
    out["auc_print"] = pair_auc(lambda r: r["family"] == "print")
    out["auc_mask"] = pair_auc(lambda r: r["family"] == "mask")
    bona_scores = scores[y == 1]
    bona_scores = bona_scores[~np.isnan(bona_scores)]
    thr = operating_point(bona_scores, 0.10) if len(bona_scores) else None
    out["operating_point_threshold"] = thr
    att = [(s, r["species"]) for s, r in zip(scores, ok, strict=True) if r["cls"] == "attack" and not np.isnan(s)]
    out["apcer_by_species_at_bpcer10"] = apcer_by_species([a for a, _ in att], [b for _, b in att], thr) if thr is not None and att else {}
    worst = max((v["apcer"] for v in out["apcer_by_species_at_bpcer10"].values()), default=None)

    caps = [r["capture_ms"] for r in rows if r["capture_ms"]]
    metrics = {"auc_screen": out["auc_screen"] and out["auc_screen"]["auc"], "auc_print": out["auc_print"] and out["auc_print"]["auc"], "apcer_species": worst,
               "ok_rate": out["ok_rate_bona_fide"], "ok_rate_min_subject": out["ok_rate_min_subject"], "capture_ms": max(caps) if caps else 1e9,
               "n_subjects": len(subjects)}
    out["go_inputs"], out["go"] = metrics, evaluate_go(metrics)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=str(ROOT / "data" / "sessions"))
    ap.add_argument("--lighting", default=None, help="restrict to one lighting condition (plan: GO is judged in office lighting)")
    ap.add_argument("--out", default=str(Path(__file__).parent))
    args = ap.parse_args()
    sessions = Path(args.sessions)
    if not sessions.is_dir() or not any(sessions.iterdir()):
        print(f"no recorded sessions in {sessions}. E2 needs labelled data from real people and attacks (docs/HUMAN_TASKS.md H-05); nothing to analyse.")
        return 3
    settings = Settings(_env_file=None)
    policy = load_policy(settings.policy_path)
    inst = ChromaInstrument(settings, verify_models(settings.models_dir), policy)
    cfg = ChallengeConfig.from_policy(policy.setting_section("challenge"))
    rows, problems = load_rows(sessions, ROOT / "data" / "features", inst, cfg)
    if args.lighting:
        rows = [r for r in rows if r["lighting"] == args.lighting]
    res = analyse(rows)
    res["problems"], res["lighting_filter"] = problems, args.lighting
    res["not_implemented"] = ["window truncation ablation", "JPEG vs PNG comparison", "palette P1 vs P2 AUC split"]
    out = Path(args.out)
    (out / "results.json").write_text(json.dumps(res, indent=2, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)), encoding="utf-8")
    go = res["go"]
    lines = ["# E2 chroma feasibility: results", "", f"Outcome: **{go['outcome']}**", "", f"Sessions {res['n_sessions']} ({res['n_ok']} chroma-ok), subjects {res['subjects']}, lighting filter {args.lighting or 'none'}.", "",
             "Criteria: " + json.dumps(go.get("criteria", {})), "", "See results.json for AUCs (cluster-bootstrap 95% CIs), APCER per species and usable-session rates. Small n gives wide CIs; do not over-read.",
             "", "Not implemented: " + ", ".join(res["not_implemented"])]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": go["outcome"], "criteria": go.get("criteria"), "n_sessions": res["n_sessions"], "subjects": res["subjects"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
