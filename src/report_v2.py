"""Summary table for the v2 (OT09 replication) results, as reported in README.md.

Works on a partial JevK5 test run: every comparison uses only the test records
that JevK5 has finished, and the rules baseline is scored on the same records.

Usage: python src/report_v2.py
"""
import json
from collections import Counter
from pathlib import Path

from score import score_doc, wa

ROOT = Path(__file__).resolve().parent.parent
GT = {m["doc"]: m for m in json.loads((ROOT / "data/docs_v2/ground_truth.json").read_text())}
RES = ROOT / "results" / "v2"


def load(name):
    path = RES / name
    return {r["doc"]: r for r in json.loads(path.read_text())} if path.exists() else {}


def total(preds, docs):
    c = Counter()
    for d in docs:
        c += score_doc(preds[d]["pairs"], GT[d]["ground_truth"])
    return c


def row(label, docs, jev, rul):
    pairs = sum(len(GT[d]["ground_truth"]) for d in docs)
    a, b = total(jev, docs), total(rul, docs)
    print(f"| {label} | {len(docs)} | {pairs} | {wa(a):.1%} | {a['E']}/{a['P']}/{a['H']}/{a['O']}/{a['N']} "
          f"| {wa(b):.1%} | {b['E']}/{b['P']}/{b['H']}/{b['O']}/{b['N']} |")


def main():
    jev = load("pred_jevk5_pilot.json") | load("pred_jevk5_test.json")
    rul = load("pred_rules_pilot.json") | load("pred_rules_test.json")
    pilot = [d for d in GT if GT[d]["split"] == "pilot"]
    test_done = [d for d in GT if GT[d]["split"] == "test" and d in jev]
    n_test = sum(GT[d]["split"] == "test" for d in GT)
    print(f"JevK5 test records finished: {len(test_done)}/{n_test}\n")
    print("| Subset | Records | Pairs | JevK5 WA | JevK5 E/P/H/O/N | Rules WA | Rules E/P/H/O/N |")
    print("|---|---:|---:|---:|---|---:|---|")
    row("Pilot (P1-P9)", pilot, jev, rul)
    row("Test, finished records", test_done, jev, rul)
    row("  - unseen formats (U1-U14)", [d for d in test_done if GT[d]["unseen_format"]], jev, rul)
    row("  - pilot formats (P1-P9)", [d for d in test_done if not GT[d]["unseen_format"]], jev, rul)
    row("**All finished records (OT09-style)**", pilot + test_done, jev, rul)

    print("\nPer format (test, finished records): JevK5 WA / Rules WA")
    forms = sorted({GT[d]["template"] for d in test_done}, key=lambda t: (t[0] == "P", int(t[1:])))
    for t in forms:
        docs = [d for d in test_done if GT[d]["template"] == t]
        print(f"  {t:<4} {wa(total(jev, docs)):6.1%} / {wa(total(rul, docs)):6.1%}  ({len(docs)} records)")


if __name__ == "__main__":
    main()
