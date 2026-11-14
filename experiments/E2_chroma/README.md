# E2 chroma feasibility

Not run: no labelled data yet. Collect with `/ops/spike` (docs/HUMAN_TASKS.md H-05), then:

    .venv\Scripts\python experiments\E2_chroma\analyze.py --sessions data\sessions --lighting office

Writes `results.json` and `report.md` here. GO needs: AUC(bona fide vs screen/replay) >= 0.95, AUC(print) >= 0.90, APCER <= 10 % per species at BPCER 10 %,
chroma status ok for >= 90 % of bona fide sessions for every subject, capture window <= 1.3 s, all leave-one-subject-out. Fewer than 3 subjects returns INSUFFICIENT_DATA.
