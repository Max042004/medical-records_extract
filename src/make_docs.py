"""Render heterogeneous medical-record PDFs from MIMIC-IV Demo OMR data.

Ground truth = the real (de-identified, date-shifted) outpatient weights in
MIMIC-IV Demo `omr`. Each PDF mixes those weights with distractor dates
(DOB, admissions, lab draws, imaging, printed/next-visit dates) and
distractor numbers (BMI in kg/m2, weight change, goal weight), mimicking
the Dog Aging Project problem: heterogeneous PDF layouts where the right
date is not always the nearest one.

Split (mirrors the ACVIM OT09 design): pilot = 9 docs in templates T1-T3,
test = 50 docs in T1-T5, so T4 and T5 are formats never seen in the pilot.
"""
import csv
import datetime as dt
import gzip
import json
import random
from collections import defaultdict
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "mimic-iv-demo"
OUT = ROOT / "data" / "docs"
SEED = 20261001
LB_TO_KG = 0.45359237

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def d(s):
    return dt.date.fromisoformat(s[:10])


def fmt(date, style):
    if style == "mdy":
        return f"{date.month:02d}/{date.day:02d}/{date.year}"
    if style == "iso":
        return date.isoformat()
    if style == "long":
        return f"{MONTHS[date.month - 1]} {date.day}, {date.year}"
    if style == "dmon":
        return f"{date.day:02d}-{MONTHS[date.month - 1][:3]}-{date.year}"
    raise ValueError(style)


def fmt_num(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def read_csv(name):
    with gzip.open(RAW / f"{name}.csv.gz", "rt") as f:
        return list(csv.DictReader(f))


def load():
    weights, bps, bmis, heights = (defaultdict(dict) for _ in range(4))
    for r in read_csv("omr"):
        sid, day, name, val = r["subject_id"], d(r["chartdate"]), r["result_name"], r["result_value"]
        target = {"Weight (Lbs)": weights, "Blood Pressure": bps,
                  "BMI (kg/m2)": bmis, "Height (Inches)": heights}.get(name)
        if target is not None and r["seq_num"] == "1" and day not in target[sid]:
            target[sid][day] = val
    patients = {r["subject_id"]: r for r in read_csv("patients")}
    adms = defaultdict(list)
    for r in read_csv("admissions"):
        adms[r["subject_id"]].append((d(r["admittime"]), d(r["dischtime"])))
    return weights, bps, bmis, heights, patients, adms


class PDF:
    """Minimal line-based PDF writer; pdftotext -layout recovers the layout."""

    def __init__(self, path, font="Helvetica", size=10):
        self.c = canvas.Canvas(str(path), pagesize=letter)
        self.font, self.size = font, size
        self.y = 740

    def line(self, text="", x=54, font=None, size=None):
        if self.y < 60:
            self.c.showPage()
            self.y = 740
        self.c.setFont(font or self.font, size or self.size)
        self.c.drawString(x, self.y, text)
        self.y -= (size or self.size) + 5

    def row(self, cells, xs, font=None):
        if self.y < 60:
            self.c.showPage()
            self.y = 740
        self.c.setFont(font or self.font, self.size)
        for text, x in zip(cells, xs):
            self.c.drawString(x, self.y, text)
        self.y -= self.size + 5

    def save(self):
        self.c.save()


def patient_info(rng, pt):
    birth_year = int(pt["anchor_year"]) - int(pt["anchor_age"])
    dob = dt.date(birth_year, rng.randint(1, 12), rng.randint(1, 28))
    return dob, pt["gender"]


def pick_visits(rng, wts):
    days = sorted(wts)
    k = min(len(days), rng.randint(3, 8))
    start = rng.randint(0, len(days) - k)
    return days[start:start + k]


def weight_str(lb_value, unit):
    lb = float(lb_value)
    if unit == "kg":
        v = round(lb * LB_TO_KG, 1)
    else:
        v = round(lb, 1)
    return v, f"{fmt_num(v)} {unit}"


def t1_flowsheet(pdf, rng, sid, visits, wts, bps, bmis, hts, dob, sex, adms):
    """Vitals flowsheet table, MM/DD/YYYY, lb. Easy: date sits on the same row."""
    unit, style = "lb", "mdy"
    lo, hi = visits[0], visits[-1]
    bp_only = [x for x in sorted(bps) if lo <= x <= hi and x not in visits]
    rows = sorted(set(visits) | set(rng.sample(bp_only, min(3, len(bp_only)))))
    pdf.line("RIVERBEND FAMILY MEDICINE - VITALS FLOWSHEET", font="Courier-Bold", size=11)
    pdf.line(f"Patient ID: {sid}   Sex: {sex}   DOB: {fmt(dob, style)}", font="Courier")
    pdf.line(f"Report printed: {fmt(hi + dt.timedelta(days=rng.randint(30, 400)), style)}", font="Courier")
    pdf.line()
    xs = [54, 150, 270, 370, 470]
    pdf.row(["Date", "Blood Pressure", "Weight", "BMI", "Height"], xs, font="Courier-Bold")
    gt = []
    for day in rows:
        w = ""
        if day in visits:
            v, w = weight_str(wts[day], unit)
            gt.append({"date": day.isoformat(), "weight": v, "unit": unit})
        bmi = f"{bmis[day]} kg/m2" if day in bmis else ""
        ht = f"{hts[day]} in" if day in hts else ""
        pdf.row([fmt(day, style), bps.get(day, ""), w, bmi, ht], xs, font="Courier")
    pdf.line()
    pdf.line(f"Next scheduled visit: {fmt(hi + dt.timedelta(days=rng.randint(60, 200)), style)}", font="Courier")
    return gt


def t2_soap(pdf, rng, sid, visits, wts, bps, bmis, hts, dob, sex, adms):
    """SOAP progress notes, ISO dates, lb. Lab-draw date sits between visit date and weight."""
    unit, style = "lb", "iso"
    pdf.line("OUTPATIENT PROGRESS NOTES", font="Helvetica-Bold", size=12)
    pdf.line(f"MRN {sid}  |  DOB {fmt(dob, style)}  |  Sex {sex}")
    pdf.line()
    gt, prev = [], None
    for i, day in enumerate(visits):
        v, w = weight_str(wts[day], unit)
        gt.append({"date": day.isoformat(), "weight": v, "unit": unit})
        labs = day - dt.timedelta(days=rng.randint(2, 10))
        pdf.line(f"Date of service: {fmt(day, style)}     Provider: Internal Medicine Clinic", font="Helvetica-Bold")
        pdf.line(f"S: Follow-up visit. Labs drawn {fmt(labs, style)} were reviewed with the patient.")
        obj = f"O: BP {bps[day]}. " if day in bps else "O: "
        obj += f"Weight {w}"
        if prev is not None:
            pv, pw = weight_str(wts[prev], unit)
            obj += f" (previous {pw} on {fmt(prev, style)})"
        obj += "."
        if day in bmis:
            obj += f" BMI {bmis[day]} kg/m2."
        pdf.line(obj)
        if prev is not None:
            delta = round(v - weight_str(wts[prev], unit)[0], 1)
            pdf.line(f"   Weight change since last visit: {'+' if delta >= 0 else '-'}{fmt_num(abs(delta))} {unit}.")
        if i == 0:
            pdf.line(f"   Goal weight discussed: {fmt_num(round(v * 0.93))} {unit}.")
        pdf.line("A/P: Continue current plan. Return to clinic in 6 months.")
        pdf.line()
        prev = day
    return gt


T3_SENTENCES = [
    "At the clinic visit on {date}, {pr} weighed {w}; blood pressure was {bp}.",
    "{Pp} weight was recorded as {w} at the appointment of {date}.",
    "When seen on {date}, {pp} weight measured {w}.",
    "A body weight of {w} was documented on {date}.",
]


def t3_letter(pdf, rng, sid, visits, wts, bps, bmis, hts, dob, sex, adms):
    """Narrative letter, long dates, kg. Some sentences put the weight before its date."""
    unit, style = "kg", "long"
    pr, pp = ("she", "her") if sex == "F" else ("he", "his")
    pdf.line("Lakeview Internal Medicine Associates", font="Helvetica-Bold", size=12)
    pdf.line(f"Letter dated {fmt(visits[-1] + dt.timedelta(days=rng.randint(14, 120)), style)}")
    pdf.line()
    pdf.line(f"Re: patient {sid}, born {fmt(dob, style)}")
    pdf.line()
    pdf.line("Dear Colleague,")
    pdf.line("I am writing to summarize this patient's recent outpatient weight history.")
    near = [a for a in adms if visits[0] - dt.timedelta(days=365) <= a[0] <= visits[-1]]
    if near:
        a = near[0]
        pdf.line(f"{pr.capitalize()} was admitted to hospital on {fmt(a[0], style)} and discharged on {fmt(a[1], style)}.")
    gt = []
    for day in visits:
        v, w = weight_str(wts[day], unit)
        gt.append({"date": day.isoformat(), "weight": v, "unit": unit})
        s = rng.choice(T3_SENTENCES).format(date=fmt(day, style), w=w, bp=bps.get(day, "not recorded"),
                                            pr=pr, pp=pp, Pp=pp.capitalize())
        pdf.line(s)
    pdf.line()
    pdf.line("Kind regards,")
    pdf.line("Outpatient Clinic")
    return gt


def t4_columns(pdf, rng, sid, visits, wts, bps, bmis, hts, dob, sex, adms):
    """Multi-column visit summary: dates in a header row, weights in a row below (unseen in pilot)."""
    unit, style = "lb", "mdy"
    pdf.line("VISIT SUMMARY BY DATE", font="Courier-Bold", size=11)
    pdf.line(f"ID {sid}  DOB {fmt(dob, style)}  Sex {sex}", font="Courier")
    pdf.line(f"Summary generated {fmt(visits[-1] + dt.timedelta(days=rng.randint(30, 300)), style)}", font="Courier")
    pdf.line()
    gt = []
    xs = [54, 175, 280, 385, 490]
    for b in range(0, len(visits), 4):
        block = visits[b:b + 4]
        pdf.row(["Visit date"] + [fmt(x, style) for x in block], xs, font="Courier-Bold")
        pdf.row(["Blood pressure"] + [bps.get(x, "-") for x in block], xs, font="Courier")
        cells = []
        for x in block:
            v, w = weight_str(wts[x], unit)
            gt.append({"date": x.isoformat(), "weight": v, "unit": unit})
            cells.append(w)
        pdf.row(["Weight"] + cells, xs, font="Courier")
        pdf.row(["BMI"] + [f"{bmis[x]} kg/m2" if x in bmis else "-" for x in block], xs, font="Courier")
        pdf.line()
    return gt


def t5_timeline(pdf, rng, sid, visits, wts, bps, bmis, hts, dob, sex, adms):
    """Clinical timeline, DD-Mon-YYYY, kg. An imaging date sits right above each weight (unseen in pilot)."""
    unit, style = "kg", "dmon"
    pdf.line("CLINICAL TIMELINE", font="Helvetica-Bold", size=12)
    pdf.line(f"Subject {sid}    Date of birth {fmt(dob, style)}    Sex {sex}")
    pdf.line()
    events = [(day, "visit") for day in visits]
    for a in adms:
        if visits[0] - dt.timedelta(days=200) <= a[0] <= visits[-1]:
            events.append((a[0], ("adm", a[1])))
    gt = []
    for day, kind in sorted(events, key=lambda e: e[0]):
        if kind == "visit":
            v, w = weight_str(wts[day], unit)
            gt.append({"date": day.isoformat(), "weight": v, "unit": unit})
            scan = day - dt.timedelta(days=rng.randint(1, 14))
            study = rng.choice(["CT abdomen/pelvis", "chest radiograph", "renal ultrasound", "MRI lumbar spine"])
            pdf.line(f"{fmt(day, style)}   Office visit, general medicine", font="Helvetica-Bold")
            pdf.line(f"      - Imaging reviewed: {study} performed {fmt(scan, style)}")
            bp = f", BP {bps[day]}" if day in bps else ""
            pdf.line(f"      - Vitals: weight {w}{bp}")
        else:
            pdf.line(f"{fmt(day, style)}   Hospital admission", font="Helvetica-Bold")
            pdf.line(f"      - Discharged {fmt(kind[1], style)}")
    return gt


TEMPLATES = {"T1": t1_flowsheet, "T2": t2_soap, "T3": t3_letter, "T4": t4_columns, "T5": t5_timeline}


def main():
    rng = random.Random(SEED)
    weights, bps, bmis, heights, patients, adms = load()
    sids = sorted(weights)
    rng.shuffle(sids)
    plan = [("pilot", t) for t in ["T1", "T2", "T3"] for _ in range(3)]
    plan += [("test", t) for t in TEMPLATES for _ in range(10)]
    assert len(sids) >= len(plan)
    manifest = []
    for (split, tpl), sid in zip(plan, sids):
        out = OUT / split
        out.mkdir(parents=True, exist_ok=True)
        dob, sex = patient_info(rng, patients[sid])
        visits = pick_visits(rng, weights[sid])
        name = f"{split}_{tpl}_{sid}"
        font = "Courier" if tpl in ("T1", "T4") else "Helvetica"
        pdf = PDF(out / f"{name}.pdf", font=font)
        gt = TEMPLATES[tpl](pdf, rng, sid, visits, weights[sid], bps[sid], bmis[sid],
                            heights[sid], dob, sex, adms[sid])
        pdf.save()
        manifest.append({"doc": name, "split": split, "template": tpl, "subject_id": sid,
                         "pdf": f"{split}/{name}.pdf", "ground_truth": gt})
    (OUT / "ground_truth.json").write_text(json.dumps(manifest, indent=1))
    n = {s: sum(len(m["ground_truth"]) for m in manifest if m["split"] == s) for s in ("pilot", "test")}
    print(f"{len(manifest)} docs; ground-truth pairs: {n}")


if __name__ == "__main__":
    main()
