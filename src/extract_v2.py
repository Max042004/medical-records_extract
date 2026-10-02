"""v2 extraction (OT09 replication). Everything here was written against the
nine pilot formats P1-P9 only; the test formats U1-U14 were not used.

Changes from v1, all decided before the v2 test run:
  rules  - skip lists extended with words from the new pilot formats; a date on
           the same line as the weight wins (nearest by characters), otherwise
           the nearest preceding usable date.
  jevk5  - same two typed decisions (gate, then date). The target is now marked
           with [[ ]] inside its line, so repeated identical values in one line
           (the v1 T4 failure) are no longer ambiguous. Option text is trimmed
           around each date to keep prompts short.

Usage: python src/extract_v2.py {rules|jevk5} {pilot|test|all}
"""
import json
import re
import sys
import time
from pathlib import Path

from candidates import find_dates, find_weights, pdf_to_text
from extract import MAX_DATES, NONE_DESC, dedupe

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "docs_v2"
RESULTS = ROOT / "results" / "v2"

# --- rule-based baseline (pilot-derived) ---------------------------------
SKIP_WEIGHT = re.compile(r"\b(change|goal|target|ideal|previous|gain(?:ed)?|los[st])\b", re.I)
SKIP_DATE = re.compile(
    r"\b(DOB|born|birth|printed|drawn|next|letter dated|admitted|discharged|admission|discharge|"
    r"follow-up|statement|payment|collected|reported|start|stop|entered|exported|tetanus|"
    r"appointment|review completed|previous)\b", re.I)


def _before_on_line(text, pos, n):
    return text[max(text.rfind("\n", 0, pos) + 1, pos - n):pos]


# Encounter segmentation: a line that starts with a usable date, optionally after a header
# label seen in the pilot ("Date of service:", "Visit date:", "CLINIC VISIT"), opens a segment.
HEADER_LABEL = re.compile(r"^\s*(?:(?:date of service|visit date|clinic visit)\s*:?\s*)?$", re.I)


def segment_heads(text, usable):
    heads = {}
    for d in usable:
        if HEADER_LABEL.match(text[text.rfind("\n", 0, d.start) + 1:d.start]):
            heads.setdefault(d.line_no, d)
    return heads


def rules(text):
    dates, pairs = find_dates(text), []
    usable = [d for d in dates if not SKIP_DATE.search(_before_on_line(text, d.start, 30))]
    heads = segment_heads(text, usable)
    for w in find_weights(text):
        if w.signed or SKIP_WEIGHT.search(text[max(0, w.start - 40):w.start]):
            continue
        same = [d for d in usable if d.line_no == w.line_no]
        above = [ln for ln in heads if ln < w.line_no]
        prior = [d for d in usable if d.start < w.start]
        if same:  # 1. a date on the weight's own line
            pick = min(same, key=lambda d: min(abs(d.start - w.end), abs(w.start - d.end)))
        elif above:  # 2. the date heading the encounter segment the weight sits in
            pick = heads[max(above)]
        elif prior:  # 3. nearest preceding date
            pick = prior[-1]
        else:
            pick = usable[0] if usable else None
        if pick:
            pairs.append({"date": pick.iso, "weight": w.value, "unit": w.unit})
    return pairs, []


# --- JevK5 decision model ------------------------------------------------
# Questions name the value only ("On which date was 74.4 kg measured?"); the record is passed
# unmodified. A value that appears n times in the record is asked once, and its n occurrences take
# the n highest-ranked options in order (1st occurrence -> top option, 2nd -> second, ...).
# Pilot runs 1-2 asked "measured at a visit?" / "a measured body weight?"; the value-only gate then
# rejected P8's "Outpatient weight trend" list. Compared on pilot gate questions only: this wording
# made 0 errors on the 87 pilot values (the previous one made 4, all P8).
GATE = (
    "This is a patient's medical record. Target value: {val}. Does the record give {val} as the "
    "patient's own body weight on some date (for example in vital signs, a visit note or a list of weights)? "
    "Answer no if {val} appears only as a weight change or weight difference (for example \"-5 lb\" or "
    "\"+2.8 lb\" since the last visit) or as a goal or target weight."
)
GATE_OPTIONS = {"yes": "the record gives the target value as the patient's body weight on some date",
                "no": "the target value appears only as a weight change, a weight difference, or a goal or target weight"}
CRITERION = (
    "This is a patient's medical record. On which date was the body weight {val} measured for the "
    "patient? Pick the date of the visit at which the weight was taken. Choose NONE if {val} is not a "
    "body weight measured for this patient (for example a weight change, a weight difference or a goal weight)."
)


def around(line, needle, width=50):
    i = line.find(needle)
    if i < 0 or len(line) <= 2 * width + len(needle):
        return line
    lo, hi = max(0, i - width), i + len(needle) + width
    return ("..." if lo else "") + line[lo:hi] + ("..." if hi < len(line) else "")


def jevk5(text, model):
    dates, pairs, log = find_dates(text), [], []
    groups = {}  # same written value -> its occurrences, in document order
    for w in find_weights(text):
        groups.setdefault((w.signed and w.raw.strip()[0], w.value, w.unit), []).append(w)
    for (sign, value, unit), occ in groups.items():
        t0 = time.time()
        val = f"{sign or ''}{value:g} {unit}"
        gate = model.decide(text, GATE.format(val=val), GATE_OPTIONS)
        entry = {"weight": val, "occurrences": len(occ), "gate_yes": round(gate["yes"], 4)}
        if gate["yes"] < 0.5:
            log.append(entry | {"choices": ["NONE (gate)"] * len(occ), "seconds": round(time.time() - t0, 2)})
            continue
        uniq = {}
        for d in sorted(dates, key=lambda d: min(abs(d.start - w.start) for w in occ)):
            uniq.setdefault(d.iso, d)
            if len(uniq) == MAX_DATES:
                break
        chosen = sorted(uniq.values(), key=lambda d: d.start)
        options = {d.iso: f"date written as \"{d.raw}\" in the line \"{around(d.line, d.raw)}\"" for d in chosen}
        options["NONE"] = NONE_DESC
        probs = model.decide(text, CRITERION.format(val=val), options)
        ranked = sorted(probs, key=probs.get, reverse=True)[:len(occ)]
        log.append(entry | {"choices": ranked, "p": [round(probs[k], 4) for k in ranked],
                            "seconds": round(time.time() - t0, 2)})
        pairs += [{"date": k, "weight": value, "unit": unit} for k in ranked if k != "NONE"]
    return pairs, log


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
