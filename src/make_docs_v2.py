"""v2: replicate the ACVIM 2026 OT09 design with MIMIC-IV Demo weights.

OT09: 59 PDF records, 49 dogs, 559 (date, body weight) pairs; a pilot set of
9 records in 9 formats was used to develop the rules and prompts; the other
50 records included 14 formats never seen in the pilot.

Here: 49 MIMIC-IV Demo patients, 59 PDFs (10 patients have two records from
different "clinics", covering consecutive date ranges), exactly 559 pairs.
Formats P1-P9 are the pilot formats; U1-U14 appear only in the test set.
Pilot = one record in each of P1-P9. Test = 50 records covering U1-U14 and P1-P9.
"""
import datetime as dt
import json
import random
from pathlib import Path

from make_docs import LB_TO_KG, PDF, fmt, fmt_num, load, patient_info

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "docs_v2"
SEED = 20261003
N_PATIENTS, N_TWO_RECORDS, CAP, TARGET_PAIRS = 49, 10, 20, 559
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt2(date, style):
    """Date styles beyond make_docs.fmt."""
    if style == "dot":
        return f"{date.day:02d}.{date.month:02d}.{date.year}"
    if style == "dmy_long":
        return f"{date.day} {MON[date.month - 1]} {date.year}"
    if style == "wkday":
        return f"{date.strftime('%a')}, {MON[date.month - 1]} {date.day}, {date.year}"
    if style == "spaced":
        return f"{date.month:02d} {date.day:02d} {date.year}"
    if style == "slash_ymd":
        return f"{date.year}/{date.month:02d}/{date.day:02d}"
    return fmt(date, style)


class Rec:
    """Everything a template needs about one record."""

    def __init__(self, rng, sid, visits, wts, bps, bmis, hts, dob, sex, adms):
        self.rng, self.sid, self.visits = rng, sid, visits
        self.wts, self.bps, self.bmis, self.hts = wts, bps, bmis, hts
        self.dob, self.sex, self.adms = dob, sex, adms
        self.gt = []

    def w(self, day, unit, with_unit=True):
        lb = float(self.wts[day])
        v = round(lb * LB_TO_KG, 1) if unit == "kg" else round(lb, 1)
        self.gt.append({"date": day.isoformat(), "weight": v, "unit": unit})
        return f"{fmt_num(v)} {unit}" if with_unit else fmt_num(v)

    def peek(self, day, unit):
        lb = float(self.wts[day])
        return round(lb * LB_TO_KG, 1) if unit == "kg" else round(lb, 1)

    def plus(self, day, lo, hi):
        return day + dt.timedelta(days=self.rng.randint(lo, hi))

    def bp(self, day, default="-"):
        return self.bps.get(day, default)

    def bp_only_days(self, k):
        lo, hi = self.visits[0], self.visits[-1]
        extra = [x for x in sorted(self.bps) if lo <= x <= hi and x not in self.visits]
        return sorted(self.rng.sample(extra, min(k, len(extra))))

    def adm_near(self, days=365):
        return [a for a in self.adms if self.visits[0] - dt.timedelta(days=days) <= a[0] <= self.visits[-1]]


# ---------------------------------------------------------------- pilot formats
def p1_flowsheet(pdf, r):
    """Vitals flowsheet; units only in the column header ("Weight (lb)")."""
    s = "mdy"
    pdf.line("RIVERBEND FAMILY MEDICINE - VITALS FLOWSHEET", font="Courier-Bold", size=11)
    pdf.line(f"Patient ID: {r.sid}   Sex: {r.sex}   DOB: {fmt2(r.dob, s)}", font="Courier")
    pdf.line(f"Report printed: {fmt2(r.plus(r.visits[-1], 30, 400), s)}", font="Courier")
    pdf.line()
    xs = [54, 150, 270, 370, 470]
    pdf.row(["Date", "BP (mmHg)", "Weight (lb)", "BMI (kg/m2)", "Height (in)"], xs, font="Courier-Bold")
    for day in sorted(set(r.visits) | set(r.bp_only_days(3))):
        wt = r.w(day, "lb", with_unit=False) if day in r.visits else ""
        pdf.row([fmt2(day, s), r.bp(day, ""), wt, r.bmis.get(day, ""), r.hts.get(day, "")], xs, font="Courier")
    pdf.line()
    pdf.line(f"Next scheduled visit: {fmt2(r.plus(r.visits[-1], 60, 200), s)}", font="Courier")


def p2_soap(pdf, r):
    """SOAP notes; lab-draw date between visit date and weight; previous weight, change, goal."""
    s, unit = "iso", "lb"
    pdf.line("OUTPATIENT PROGRESS NOTES", font="Helvetica-Bold", size=12)
    pdf.line(f"MRN {r.sid}  |  DOB {fmt2(r.dob, s)}  |  Sex {r.sex}")
    pdf.line()
    prev = None
    for i, day in enumerate(r.visits):
        pdf.line(f"Date of service: {fmt2(day, s)}     Provider: Internal Medicine Clinic", font="Helvetica-Bold")
        pdf.line(f"S: Follow-up visit. Labs drawn {fmt2(day - dt.timedelta(days=r.rng.randint(2, 10)), s)} were reviewed.")
        o = (f"O: BP {r.bps[day]}. " if day in r.bps else "O: ") + f"Weight {r.w(day, unit)}"
        if prev:
            o += f" (previous {fmt_num(r.peek(prev, unit))} {unit} on {fmt2(prev, s)})"
        pdf.line(o + "." + (f" BMI {r.bmis[day]} kg/m2." if day in r.bmis else ""))
        if prev:
            d = round(r.peek(day, unit) - r.peek(prev, unit), 1)
            pdf.line(f"   Weight change since last visit: {'+' if d >= 0 else '-'}{fmt_num(abs(d))} {unit}.")
        if i == 0:
            pdf.line(f"   Goal weight discussed: {fmt_num(round(r.peek(day, unit) * 0.93))} {unit}.")
        pdf.line("A/P: Continue current plan. Return to clinic in 6 months.")
        pdf.line()
        prev = day


P3_SENT = ["At the clinic visit on {date}, {pr} weighed {w}; blood pressure was {bp}.",
           "{Pp} weight was recorded as {w} at the appointment of {date}.",
           "When seen on {date}, {pp} weight measured {w}.",
           "A body weight of {w} was documented on {date}."]


def p3_letter(pdf, r):
    """Narrative letter; some sentences put the weight before its date."""
    s, unit = "long", "kg"
    pr, pp = ("she", "her") if r.sex == "F" else ("he", "his")
    pdf.line("Lakeview Internal Medicine Associates", font="Helvetica-Bold", size=12)
    pdf.line(f"Letter dated {fmt2(r.plus(r.visits[-1], 14, 120), s)}")
    pdf.line()
    pdf.line(f"Re: patient {r.sid}, born {fmt2(r.dob, s)}")
    pdf.line("Dear Colleague,")
    pdf.line("I am writing to summarize this patient's recent outpatient weight history.")
    for a in r.adm_near()[:1]:
        pdf.line(f"{pr.capitalize()} was admitted to hospital on {fmt2(a[0], s)} and discharged on {fmt2(a[1], s)}.")
    for day in r.visits:
        pdf.line(r.rng.choice(P3_SENT).format(date=fmt2(day, s), w=r.w(day, unit), bp=r.bp(day, "not recorded"),
                                              pr=pr, pp=pp, Pp=pp.capitalize()))
    pdf.line()
    pdf.line("Kind regards,")
    pdf.line("Outpatient Clinic")


def p4_statement(pdf, r):
    """Billing statement; payment rows carry their own dates."""
    s = "mdy"
    pdf.line("NORTHGATE MEDICAL GROUP - PATIENT ACCOUNT STATEMENT", font="Courier-Bold", size=11)
    pdf.line(f"Statement date: {fmt2(r.plus(r.visits[-1], 20, 90), s)}   Account: {r.sid}", font="Courier")
    pdf.line(f"Guarantor DOB: {fmt2(r.dob, s)}", font="Courier")
    pdf.line()
    xs = [54, 150, 380, 470]
    pdf.row(["Date", "Description", "Charge", "Payment"], xs, font="Courier-Bold")
    for day in r.visits:
        pdf.row([fmt2(day, s), "Office visit, established patient", "$145.00", ""], xs, font="Courier")
        pdf.line(f"           Patient weight recorded at visit: {r.w(day, 'lb')}", font="Courier")
        pdf.row([fmt2(r.plus(day, 15, 40), s), "Payment received - thank you", "", "$145.00"], xs, font="Courier")
    pdf.line()
    pdf.line("Balance due: $0.00", font="Courier")


def p5_lab_visits(pdf, r):
    """European dotted dates; collected/reported lab dates sit between visit date and weight."""
    s, unit = "dot", "kg"
    pdf.line("MEDIZINISCHES VERSORGUNGSZENTRUM - CLINIC VISITS AND LABORATORY", font="Helvetica-Bold", size=11)
    pdf.line(f"Patient {r.sid}   born {fmt2(r.dob, s)}")
    pdf.line()
    for day in r.visits:
        col = day - dt.timedelta(days=r.rng.randint(1, 6))
        pdf.line(f"CLINIC VISIT {fmt2(day, s)}", font="Helvetica-Bold")
        pdf.line(f"   Laboratory: specimen collected {fmt2(col, s)}, reported {fmt2(col + dt.timedelta(days=1), s)}")
        pdf.line(f"   Body weight: {r.w(day, unit)}" + (f"    Blood pressure: {r.bps[day]}" if day in r.bps else ""))
        pdf.line()


def p6_dosing(pdf, r):
    """Medication dosing record; weight written before its 'measured' date; mg/kg doses."""
    s, unit = "iso", "kg"
    pdf.line("ANTICOAGULATION AND DOSING RECORD", font="Helvetica-Bold", size=12)
    pdf.line(f"Patient {r.sid}   DOB {fmt2(r.dob, s)}")
    pdf.line()
    for day in r.visits:
        start = r.plus(day, 1, 5)
        dose = r.rng.choice([1, 1.5, 5, 10])
        pdf.line(f"Dosing weight: {r.w(day, unit)} (measured {fmt2(day, s)})")
        pdf.line(f"   Enoxaparin {dose} mg/kg, start {fmt2(start, s)}, stop {fmt2(r.plus(start, 5, 14), s)}")
    pdf.line()
    pdf.line(f"Pharmacist review completed {fmt2(r.plus(r.visits[-1], 1, 30), s)}")


def p7_intake(pdf, r):
    """Nursing intake form, one per visit, key: value fields."""
    s, unit = "long", "lb"
    pdf.line("NURSING INTAKE FORMS", font="Helvetica-Bold", size=12)
    pdf.line(f"Patient {r.sid}, date of birth {fmt2(r.dob, s)}")
    pdf.line()
    for day in r.visits:
        pdf.line(f"Visit date: {fmt2(day, s)}")
        if day in r.hts:
            pdf.line(f"Height: {r.hts[day]} in")
        pdf.line(f"Weight: {r.w(day, unit)}")
        pdf.line(f"Blood pressure: {r.bp(day, 'not taken')}")
        pdf.line(f"Last tetanus booster: {fmt2(r.dob + dt.timedelta(days=r.rng.randint(6000, 20000)), s)}")
        pdf.line(f"Next appointment: {fmt2(r.plus(day, 30, 180), s)}")
        pdf.line()


def p8_discharge(pdf, r):
    """Discharge summary with an outpatient weight-trend list and a dry-weight target."""
    s, unit = "dmy_long", "kg"
    admit = r.plus(r.visits[-1], 20, 120)
    a0 = (admit, admit + dt.timedelta(days=r.rng.randint(3, 12)))
    pdf.line("DISCHARGE SUMMARY", font="Helvetica-Bold", size=12)
    pdf.line(f"Patient {r.sid}   DOB {fmt2(r.dob, s)}   Sex {r.sex}")
    pdf.line(f"Admission date: {fmt2(a0[0], s)}   Discharge date: {fmt2(a0[1], s)}")
    pdf.line()
    pdf.line("Outpatient weight trend before admission:")
    for day in r.visits:
        pdf.line(f"   - {fmt2(day, s)}: {r.w(day, unit)}")
    pdf.line(f"Dry weight target at discharge: {fmt_num(round(r.peek(r.visits[-1], unit) * 0.95, 1))} {unit}")
    pdf.line(f"Follow-up appointment: {fmt2(a0[1] + dt.timedelta(days=14), s)}")


def p9_export(pdf, r):
    """EHR export lines with an 'entered' date after the value."""
    s, unit = "iso", "lb"
    pdf.line("EHR OBSERVATION EXPORT", font="Courier-Bold", size=11)
    pdf.line(f"subject={r.sid} dob={fmt2(r.dob, s)} exported={fmt2(r.plus(r.visits[-1], 10, 100), s)}", font="Courier")
    pdf.line()
    for day in sorted(set(r.visits) | set(r.bp_only_days(3))):
        entered = fmt2(r.plus(day, 0, 3), s)
        if day in r.visits:
            pdf.line(f"{fmt2(day, s)} | WEIGHT | {r.w(day, unit)} | entered {entered} by RN", font="Courier")
        if day in r.bps:
            pdf.line(f"{fmt2(day, s)} | BP     | {r.bps[day]} mmHg | entered {entered} by RN", font="Courier")


# --------------------------------------------------------------- unseen formats
def u1_columns(pdf, r):
    """Dates in a header row, weights in a row underneath (4 visits per block)."""
    s = "mdy"
    pdf.line("VISIT SUMMARY BY DATE", font="Courier-Bold", size=11)
    pdf.line(f"ID {r.sid}  DOB {fmt2(r.dob, s)}  Sex {r.sex}", font="Courier")
    pdf.line(f"Summary generated {fmt2(r.plus(r.visits[-1], 30, 300), s)}", font="Courier")
    pdf.line()
    xs = [54, 175, 280, 385, 490]
    for b in range(0, len(r.visits), 4):
        block = r.visits[b:b + 4]
        pdf.row(["Visit date"] + [fmt2(x, s) for x in block], xs, font="Courier-Bold")
        pdf.row(["Blood pressure"] + [r.bp(x) for x in block], xs, font="Courier")
        pdf.row(["Weight"] + [r.w(x, "lb") for x in block], xs, font="Courier")
        pdf.row(["BMI"] + [f"{r.bmis[x]} kg/m2" if x in r.bmis else "-" for x in block], xs, font="Courier")
        pdf.line()


def u2_timeline(pdf, r):
    """Timeline; an imaging date sits right above each weight."""
    s, unit = "dmon", "kg"
    pdf.line("CLINICAL TIMELINE", font="Helvetica-Bold", size=12)
    pdf.line(f"Subject {r.sid}    Date of birth {fmt2(r.dob, s)}    Sex {r.sex}")
    pdf.line()
    events = [(d, None) for d in r.visits] + [(a[0], a[1]) for a in r.adm_near(200)]
    for day, disch in sorted(events, key=lambda e: e[0]):
        if disch is None:
            study = r.rng.choice(["CT abdomen/pelvis", "chest radiograph", "renal ultrasound", "MRI lumbar spine"])
            pdf.line(f"{fmt2(day, s)}   Office visit, general medicine", font="Helvetica-Bold")
            pdf.line(f"      - Imaging reviewed: {study} performed {fmt2(day - dt.timedelta(days=r.rng.randint(1, 14)), s)}")
            pdf.line(f"      - Vitals: weight {r.w(day, unit)}" + (f", BP {r.bps[day]}" if day in r.bps else ""))
        else:
            pdf.line(f"{fmt2(day, s)}   Hospital admission", font="Helvetica-Bold")
            pdf.line(f"      - Discharged {fmt2(disch, s)}")


def u3_referral(pdf, r):
    """Referral letter: recent weights newest first, each followed by its date in parentheses."""
    s, unit = "mdy", "lb"
    pdf.line("REFERRAL TO ENDOCRINOLOGY", font="Helvetica-Bold", size=12)
    pdf.line(f"Referral date: {fmt2(r.plus(r.visits[-1], 5, 60), s)}     Patient {r.sid}, DOB {fmt2(r.dob, s)}")
    pdf.line()
    pdf.line("Reason for referral: weight change and glucose intolerance.")
    pdf.line("Recent weights (most recent first):")
    items = [f"{r.w(day, unit)} ({fmt2(day, s)})" for day in reversed(r.visits)]
    for i in range(0, len(items), 3):
        pdf.line("   " + ", ".join(items[i:i + 3]) + ("," if i + 3 < len(items) else "."))
    pdf.line()
    pdf.line("Thank you for seeing this patient.")


def u4_two_column(pdf, r):
    """Two-column page: problem list with diagnosis dates on the left, weight history on the right."""
    s, unit = "mdy", "lb"
    problems = ["Hypertension", "Type 2 diabetes", "Hyperlipidemia", "Osteoarthritis, knee", "GERD",
                "Chronic kidney disease", "Hypothyroidism", "Depression", "Asthma", "Gout"]
    r.rng.shuffle(problems)
    pdf.line("CLINIC SUMMARY", font="Helvetica-Bold", size=12)
    pdf.line(f"Patient {r.sid}   DOB {fmt2(r.dob, s)}")
    pdf.line()
    pdf.row(["PROBLEM LIST", "WEIGHT HISTORY"], [54, 330], font="Helvetica-Bold")
    n = max(len(r.visits), 4)
    for i in range(n):
        left = ""
        if i < len(problems):
            onset = r.visits[0] - dt.timedelta(days=r.rng.randint(200, 4000))
            left = f"{problems[i]}, diagnosed {fmt2(onset, s)}"
        right = f"{fmt2(r.visits[i], s)}   {r.w(r.visits[i], unit)}" if i < len(r.visits) else ""
        pdf.row([left, right], [54, 330])


def u5_weight_first(pdf, r):
    """Weight-history table with the weight column before the date column."""
    s, unit = "long", "kg"
    pdf.line("WEIGHT HISTORY REPORT", font="Courier-Bold", size=11)
    pdf.line(f"Patient {r.sid}  DOB {fmt2(r.dob, s)}", font="Courier")
    pdf.line()
    xs = [54, 160, 360]
    pdf.row(["Weight", "Date recorded", "Location"], xs, font="Courier-Bold")
    for day in reversed(r.visits):
        pdf.row([r.w(day, unit), fmt2(day, s), r.rng.choice(["Clinic A", "Clinic B", "Annex"])], xs, font="Courier")


def u6_portal(pdf, r):
    """Patient-portal messages; each message header carries a sent date (day after the visit)."""
    s_head, s_body, unit = "wkday", "mdy", "lb"
    pdf.line("PATIENT PORTAL - MESSAGE HISTORY", font="Helvetica-Bold", size=12)
    pdf.line(f"Account {r.sid}")
    pdf.line()
    for day in r.visits:
        sent = r.plus(day, 1, 3)
        pdf.line(f"From: Care Team    Sent: {fmt2(sent, s_head)} 9:14 AM", font="Helvetica-Bold")
        pdf.line(f"Your weight at your visit on {fmt2(day, s_body)} was {r.w(day, unit)}. Keep up the good work.")
        pdf.line()


def u7_wellness(pdf, r):
    """Immunizations plus wellness rows with a 'next due' date on the same line."""
    s, unit = "long", "lb"
    pdf.line("PREVENTIVE CARE RECORD", font="Helvetica-Bold", size=12)
    pdf.line(f"Patient {r.sid}   DOB {fmt2(r.dob, s)}")
    pdf.line()
    pdf.line("Immunizations:", font="Helvetica-Bold")
    for vac in ["Influenza", "Tdap", "Pneumococcal"]:
        pdf.line(f"   {vac}: given {fmt2(r.visits[0] - dt.timedelta(days=r.rng.randint(30, 900)), s)}")
    pdf.line("Wellness checks:", font="Helvetica-Bold")
    for day in r.visits:
        bmi = f" - BMI {r.bmis[day]} kg/m2" if day in r.bmis else ""
        pdf.line(f"   {fmt2(day, s)} - Weight {r.w(day, unit)}{bmi} - next due {fmt2(day + dt.timedelta(days=365), s)}")


def u8_nursing(pdf, r):
    """Nursing flowsheet with times; order dates for 'daily weights' as distractors."""
    s, unit = "mdy", "kg"
    pdf.line("NURSING FLOWSHEET - VITAL SIGNS", font="Courier-Bold", size=11)
    pdf.line(f"MRN {r.sid}   DOB {fmt2(r.dob, s)}", font="Courier")
    pdf.line(f"Order: weight at every visit (ordered {fmt2(r.visits[0] - dt.timedelta(days=30), s)})", font="Courier")
    pdf.line()
    for day in r.visits:
        hh = r.rng.randint(7, 16)
        pdf.line(f"{fmt2(day, s)} {hh:02d}:{r.rng.randint(0, 59):02d}  Weight {r.w(day, unit)} (standing scale)", font="Courier")
        if day in r.bps:
            pdf.line(f"{fmt2(day, s)} {hh:02d}:{r.rng.randint(0, 59):02d}  BP {r.bps[day]}", font="Courier")


def u9_claim(pdf, r):
    """Claim-form style with spaced date boxes (MM DD YYYY)."""
    s, unit = "spaced", "lb"
    pdf.line("HEALTH INSURANCE CLAIM - SERVICE LINES", font="Courier-Bold", size=11)
    pdf.line(f"INSURED ID {r.sid}    PATIENT BIRTH DATE {fmt2(r.dob, s)}", font="Courier")
    pdf.line()
    pdf.row(["DATE OF SERVICE", "CPT", "NOTES"], [54, 200, 260], font="Courier-Bold")
    for day in r.visits:
        pdf.row([fmt2(day, s), "99214", f"vitals: wt {r.w(day, unit)}, BP {r.bp(day)}"], [54, 200, 260], font="Courier")


def u10_physio(pdf, r):
    """Physiotherapy progress report; goal body mass with a target date."""
    s, unit = "iso", "kg"
    pdf.line("PHYSIOTHERAPY PROGRESS REPORT", font="Helvetica-Bold", size=12)
    pdf.line(f"Client {r.sid}   DOB {fmt2(r.dob, s)}")
    pdf.line(f"Initial evaluation: {fmt2(r.visits[0] - dt.timedelta(days=r.rng.randint(7, 60)), s)}")
    goal = fmt_num(round(r.peek(r.visits[0], unit) * 0.92, 1))
    pdf.line(f"Goal: body mass <= {goal} {unit} by {fmt2(r.visits[-1] + dt.timedelta(days=90), s)}")
    pdf.line()
    for i, day in enumerate(r.visits, 1):
        pdf.line(f"Session {i}, {fmt2(day, s)}: body mass {r.w(day, unit)} on clinic scale; exercises progressed.")


def u11_nutrition(pdf, r):
    """Dietitian note: usual and ideal body weight as distractors, then a weight table."""
    s, unit = "dot", "kg"
    first = r.peek(r.visits[0], unit)
    pdf.line("NUTRITION ASSESSMENT", font="Helvetica-Bold", size=12)
    pdf.line(f"Patient {r.sid}   born {fmt2(r.dob, s)}   Consult date {fmt2(r.visits[0], s)}")
    pdf.line()
    pdf.line(f"Usual body weight (patient report): {fmt_num(round(first * 1.08, 1))} {unit}")
    pdf.line(f"Ideal body weight (Hamwi): {fmt_num(round(first * 0.85, 1))} {unit}")
    pdf.line("Measured weights at nutrition visits:")
    for day in r.visits:
        pdf.line(f"   {fmt2(day, s)}    {r.w(day, unit)}")


def u12_telehealth(pdf, r):
    """Remote-monitoring log; a later 'synced' timestamp follows each reading on the same line."""
    s, unit = "iso", "kg"
    pdf.line("REMOTE MONITORING - CONNECTED SCALE", font="Courier-Bold", size=11)
    pdf.line(f"Enrollee {r.sid}   enrolled {fmt2(r.visits[0] - dt.timedelta(days=r.rng.randint(5, 40)), s)}", font="Courier")
    pdf.line()
    for day in r.visits:
        t = f"{r.rng.randint(6, 9):02d}:{r.rng.randint(0, 59):02d}"
        pdf.line(f"{fmt2(day, s)} {t}  scale reading {r.w(day, unit)}  synced {fmt2(r.plus(day, 1, 4), s)} 22:00", font="Courier")


def u13_anthro(pdf, r):
    """Anthropometrics table with units in the header only and YYYY/MM/DD dates."""
    s = "slash_ymd"
    pdf.line("ANTHROPOMETRIC MEASUREMENTS", font="Courier-Bold", size=11)
    pdf.line(f"Patient {r.sid}  DOB {fmt2(r.dob, s)}", font="Courier")
    pdf.line()
    xs = [54, 160, 270, 380]
    pdf.row(["Date", "Weight (kg)", "Height (cm)", "BMI"], xs, font="Courier-Bold")
    for day in r.visits:
        ht = str(round(float(r.hts[day]) * 2.54)) if day in r.hts else ""
        pdf.row([fmt2(day, s), r.w(day, "kg", with_unit=False), ht, r.bmis.get(day, "")], xs, font="Courier")


def u14_careplan(pdf, r):
    """Care-plan check-ins: scheduled and completed dates on one line, plus a target weight."""
    s, unit = "iso", "lb"
    pdf.line("CHRONIC CARE PLAN - CHECK-INS", font="Helvetica-Bold", size=12)
    pdf.line(f"Member {r.sid}   DOB {fmt2(r.dob, s)}")
    pdf.line()
    target = fmt_num(round(r.peek(r.visits[0], unit) * 0.9))
    for i, day in enumerate(r.visits, 1):
        sched = day - dt.timedelta(days=r.rng.randint(1, 10))
        pdf.line(f"Check-in #{i} - scheduled {fmt2(sched, s)}, completed {fmt2(day, s)}: "
                 f"weight {r.w(day, unit)} (target <= {target} {unit})")


PILOT = {"P1": p1_flowsheet, "P2": p2_soap, "P3": p3_letter, "P4": p4_statement, "P5": p5_lab_visits,
         "P6": p6_dosing, "P7": p7_intake, "P8": p8_discharge, "P9": p9_export}
UNSEEN = {"U1": u1_columns, "U2": u2_timeline, "U3": u3_referral, "U4": u4_two_column, "U5": u5_weight_first,
          "U6": u6_portal, "U7": u7_wellness, "U8": u8_nursing, "U9": u9_claim, "U10": u10_physio,
          "U11": u11_nutrition, "U12": u12_telehealth, "U13": u13_anthro, "U14": u14_careplan}
COURIER = {"P1", "P4", "P9", "U1", "U5", "U8", "U9", "U12", "U13"}


def plan_records(rng, weights):
    """49 patients, 10 of them with two records; visits per record capped so the total is 559."""
    sids = sorted(weights, key=lambda s: (-len(weights[s]), s))[:N_PATIENTS]
    n_rec = {s: 2 if i < N_TWO_RECORDS else 1 for i, s in enumerate(sids)}
    take = {s: min(len(weights[s]), n_rec[s] * CAP) for s in sids}
    for s in sids:  # top up to exactly TARGET_PAIRS from patients with spare visits
        while sum(take.values()) < TARGET_PAIRS and take[s] < len(weights[s]) and take[s] < n_rec[s] * CAP + 3:
            take[s] += 1
    assert sum(take.values()) == TARGET_PAIRS, sum(take.values())
    records = []
    for s in sids:
        days = sorted(weights[s])
        start = rng.randint(0, len(days) - take[s])
        window = days[start:start + take[s]]
        if n_rec[s] == 1:
            records.append((s, window))
        else:
            half = len(window) // 2
            records += [(s, window[:half]), (s, window[half:])]
    return records


def main():
    rng = random.Random(SEED)
    weights, bps, bmis, heights, patients, adms = load()
    records = plan_records(rng, weights)
    rng.shuffle(records)
    plan = [("pilot", p) for p in PILOT]
    unseen, seen = list(UNSEEN), list(PILOT)
    cycle = unseen + seen
    plan += [("test", f) for f in (cycle * 2 + unseen[:4])]
    assert len(plan) == len(records) == 59
    dobs = {}
    manifest = []
    for i, ((split, form), (sid, visits)) in enumerate(zip(plan, records), 1):
        if sid not in dobs:
            dobs[sid] = patient_info(rng, patients[sid])
        dob, sex = dobs[sid]
        out = OUT / split
        out.mkdir(parents=True, exist_ok=True)
        name = f"{split}_{form}_{sid}_{i:02d}"
        r = Rec(rng, sid, visits, weights[sid], bps[sid], bmis[sid], heights[sid], dob, sex, adms[sid])
        pdf = PDF(out / f"{name}.pdf", font="Courier" if form in COURIER else "Helvetica")
        (PILOT | UNSEEN)[form](pdf, r)
        pdf.save()
        manifest.append({"doc": name, "split": split, "template": form, "unseen_format": form in UNSEEN,
                         "subject_id": sid, "pdf": f"{split}/{name}.pdf", "ground_truth": r.gt})
    (OUT / "ground_truth.json").write_text(json.dumps(manifest, indent=1))
    pairs = {s: sum(len(m["ground_truth"]) for m in manifest if m["split"] == s) for s in ("pilot", "test")}
    print(f"{len(manifest)} records, {len({m['subject_id'] for m in manifest})} patients, "
          f"{sum(pairs.values())} pairs {pairs}, formats: pilot {len(PILOT)}, unseen {len(UNSEEN)}")


if __name__ == "__main__":
    main()
