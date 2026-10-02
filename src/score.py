"""Score predictions with the weighted accuracy from ACVIM 2026 abstract OT09.

WA = 3E / (3E + 3P + 3H + 2O + 1N)

Per document, predictions are matched one-to-one to ground-truth pairs:
  E  exact match         date and weight (value + unit) both equal a GT pair
  P  partial match       only one of date / weight equals a still-unmatched GT pair
  H  hallucination       a predicted pair that matches no GT pair on either field
  O  omission            a GT pair left unmatched
  N  non-compliance      an output that is not a valid (ISO date, number, unit) triple

Usage: python src/score.py [--gt data/docs_v2/ground_truth.json] results/pred_jevk5_test.json [more ...]
"""
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def compliant(p):
    try:
        dt.date.fromisoformat(p["date"])
        return isinstance(p["weight"], (int, float)) and p["unit"] in ("lb", "kg")
    except (KeyError, TypeError, ValueError):
        return False


def same_w(p, g):
    return p["unit"] == g["unit"] and abs(p["weight"] - g["weight"]) < 1e-6


def score_doc(preds, gt):
    c = Counter()
    good = []
    for p in preds:
        if compliant(p):
            good.append(p)
        else:
            c["N"] += 1
    open_gt = list(gt)
    rest = []
    for p in good:
        hit = next((g for g in open_gt if g["date"] == p["date"] and same_w(p, g)), None)
        if hit:
            c["E"] += 1
            open_gt.remove(hit)
        else:
            rest.append(p)
    for p in rest:
        hit = next((g for g in open_gt if same_w(p, g)), None) or \
              next((g for g in open_gt if g["date"] == p["date"]), None)
        if hit:
            c["P"] += 1
            open_gt.remove(hit)
        else:
            c["H"] += 1
    c["O"] += len(open_gt)
    return c


def wa(c):
    den = 3 * c["E"] + 3 * c["P"] + 3 * c["H"] + 2 * c["O"] + c["N"]
    return 3 * c["E"] / den if den else 0.0


def report(pred_file, gt_file=ROOT / "data/docs/ground_truth.json"):
    manifest = {m["doc"]: m for m in json.loads(Path(gt_file).read_text())}
    preds = json.loads(Path(pred_file).read_text())
    total, by_tpl = Counter(), {}
    for r in preds:
        m = manifest[r["doc"]]
        c = score_doc(r["pairs"], m["ground_truth"])
        total += c
        by_tpl.setdefault(m["template"], Counter()).update(c)
    n_gt = sum(len(manifest[r["doc"]]["ground_truth"]) for r in preds)
    print(f"\n== {pred_file}  ({len(preds)} docs, {n_gt} ground-truth pairs)")
    print(f"{'':6}{'E':>5}{'P':>5}{'H':>5}{'O':>5}{'N':>5}{'WA':>8}")
    for t in sorted(by_tpl):
        c = by_tpl[t]
        print(f"{t:6}{c['E']:>5}{c['P']:>5}{c['H']:>5}{c['O']:>5}{c['N']:>5}{wa(c):>8.1%}")
    print(f"{'ALL':6}{total['E']:>5}{total['P']:>5}{total['H']:>5}{total['O']:>5}{total['N']:>5}{wa(total):>8.1%}")
    return total


if __name__ == "__main__":
    args = sys.argv[1:]
    gt = ROOT / "data/docs/ground_truth.json"
    if args and args[0] == "--gt":
        gt, args = Path(args[1]), args[2:]
    for f in args:
        report(f, gt)
