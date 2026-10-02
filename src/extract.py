"""Extract (visit date, body weight) pairs with two methods.

rules  - baseline in the spirit of OT09's rule-based algorithm: assign each
         weight to the nearest preceding date, with keyword filters written
         by looking at the pilot templates (T1-T3) only.
jevk5  - two typed decisions per weight candidate, both answered by the
         local JevK5 model: (1) yes/no "is this a body weight measured at a
         visit?" and, if yes, (2) "which of these dates was it measured on?"
         (with a NONE option). The output can only be a listed date or nothing.
         The gate was added after the first pilot run, where the date question
         alone assigned weight changes ("-8 lb") to visit dates.

Usage: python src/extract.py {rules|jevk5} {pilot|test|all}
"""
import json
import re
import sys
import time
from pathlib import Path

from candidates import find_dates, find_weights, pdf_to_text

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "docs"
RESULTS = ROOT / "results" / "v1"

# --- rule-based baseline -------------------------------------------------
# Words seen in the pilot templates that mark a number as not a measured weight,
# or a date as not a visit date.
SKIP_WEIGHT = re.compile(r"\b(change|goal|target|ideal|previous|gain(?:ed)?|los[st])\b", re.I)
SKIP_DATE = re.compile(r"\b(DOB|born|birth|printed|drawn|next|letter dated|admitted|discharged)\b", re.I)


def rules(text):
    dates, pairs = find_dates(text), []
    for w in find_weights(text):
        before = text[max(0, w.start - 40):w.start]
        if w.signed or SKIP_WEIGHT.search(before):
            continue
        usable = [d for d in dates if not SKIP_DATE.search(text[max(0, d.start - 25):d.start])]
        prior = [d for d in usable if d.start < w.start]
        pick = prior[-1] if prior else (usable[0] if usable else None)
        if pick:
            pairs.append({"date": pick.iso, "weight": w.value, "unit": w.unit})
    return pairs, []


# --- JevK5 decision model ------------------------------------------------
MAX_DATES = 15  # 16 letters minus the NONE option
CRITERION = (
    "This is a patient's medical record. Target value: the body weight \"{raw}\" in the line "
    "\"{line}\". On which date was this body weight measured for the patient? Pick the date of the "
    "visit at which the weight was taken. Choose NONE if the target value is not a body weight "
    "measured for this patient (for example a weight change, a weight difference or a goal weight)."
)
NONE_DESC = "the target value is not a measured body weight, or none of the listed dates applies"
GATE = (
    "This is a patient's medical record. Target value: \"{raw}\" in the line \"{line}\". "
    "Is the target value a body weight of the patient that was measured at a visit? Answer no if it "
    "is a weight change or weight difference (for example \"-5 lb\" or \"+2.8 lb\" since the last visit) "
    "or a goal or target weight."
)
GATE_OPTIONS = {"yes": "the target value is a body weight measured at a visit",
                "no": "the target value is a weight change, a weight difference, or a goal or target weight"}


def jevk5(text, model):
    dates, pairs, log = find_dates(text), [], []
    for w in find_weights(text):
        t0 = time.time()
        gate = model.decide(text, GATE.format(raw=w.raw.strip(), line=w.line), GATE_OPTIONS)
        if gate["yes"] < 0.5:
            log.append({"weight": w.raw.strip(), "line": w.line, "gate_yes": round(gate["yes"], 4),
                        "choice": "NONE (gate)", "p": round(gate["no"], 4),
                        "seconds": round(time.time() - t0, 2)})
            continue
        uniq = {}
        for d in sorted(dates, key=lambda d: abs(d.start - w.start)):
            uniq.setdefault(d.iso, d)
            if len(uniq) == MAX_DATES:
                break
        chosen = sorted(uniq.values(), key=lambda d: d.start)  # document order
        options = {d.iso: f"date written as \"{d.raw}\" in the line \"{d.line}\"" for d in chosen}
        options["NONE"] = NONE_DESC
        probs = model.decide(text, CRITERION.format(raw=w.raw.strip(), line=w.line), options)
        best = max(probs, key=probs.get)
        log.append({"weight": w.raw.strip(), "line": w.line, "gate_yes": round(gate["yes"], 4),
                    "choice": best, "p": round(probs[best], 4), "seconds": round(time.time() - t0, 2)})
        if best != "NONE":
            pairs.append({"date": best, "weight": w.value, "unit": w.unit})
    return pairs, log


def dedupe(pairs):
    seen, out = set(), []
    for p in pairs:
        key = (p["date"], p["weight"], p["unit"])
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def main():
    method, split = sys.argv[1], sys.argv[2]
    manifest = json.loads((DOCS / "ground_truth.json").read_text())
    docs = [m for m in manifest if split == "all" or m["split"] == split]
    model = None
    if method == "jevk5":
        from jevk5_client import JevK5
        model = JevK5()
    RESULTS.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS / f"pred_{method}_{split}.json"
    done = {r["doc"]: r for r in json.loads(out_path.read_text())} if out_path.exists() else {}
    for i, m in enumerate(docs, 1):
        if m["doc"] in done:
            continue
        text = pdf_to_text(DOCS / m["pdf"])
        t0 = time.time()
        pairs, log = rules(text) if method == "rules" else jevk5(text, model)
        done[m["doc"]] = {"doc": m["doc"], "pairs": dedupe(pairs), "decisions": log,
                          "seconds": round(time.time() - t0, 2)}
        out_path.write_text(json.dumps(list(done.values()), indent=1))
        print(f"[{i}/{len(docs)}] {m['doc']}: {len(done[m['doc']]['pairs'])} pairs, "
              f"{done[m['doc']]['seconds']} s", flush=True)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
