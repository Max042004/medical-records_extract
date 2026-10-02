"""PDF -> text, then deterministic candidate extraction.

Every date and every number-with-a-weight-unit becomes a typed candidate.
Downstream steps only choose among these candidates, so their output is
always a valid (ISO date, number, unit) triple: format non-compliance is
impossible by construction.
"""
import datetime as dt
import re
import subprocess
from dataclasses import dataclass

MONTH_ALT = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
             r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?")
MONTH_NUM = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), "dmy"),  # v2 pilot format P5
    (re.compile(rf"\b({MONTH_ALT})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I), "Mdy"),
    (re.compile(rf"\b(\d{{1,2}})[-\s]({MONTH_ALT})\.?[-\s,]+(\d{{4}})\b", re.I), "dMy"),
]
# A number followed by a weight unit; "kg/m2" (BMI) and "mg/kg" style rates are excluded.
WEIGHT_RE = re.compile(
    r"(?<![\w.])([+-]?\d{1,3}(?:\.\d{1,2})?)\s?(lbs?|pounds?|kgs?|kilograms?)\b(?!\s*/)", re.I)
UNIT = {"lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
        "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg"}


@dataclass
class Span:
    start: int
    end: int
    raw: str
    line_no: int
    line: str


@dataclass
class DateCand(Span):
    iso: str


@dataclass
class WeightCand(Span):
    value: float
    unit: str
    signed: bool
    col: int = 0  # offset of the value inside its line

    def marked_line(self, width=90):
        """The line with the target value wrapped in [[ ]], trimmed around it."""
        a, b = self.col, self.col + len(self.raw.strip())
        raw = self.full_line
        s = raw[:a] + "[[" + raw[a:b] + "]]" + raw[b:]
        lo = max(0, a - width)
        return re.sub(r"\s{3,}", "   ", ("..." if lo else "") + s[lo:b + 4 + width].strip())


def pdf_to_text(path):
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                         capture_output=True, text=True, check=True).stdout
    lines = [ln.rstrip() for ln in out.replace("\f", "\n").splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _line_info(text, pos):
    line_no = text.count("\n", 0, pos)
    a = text.rfind("\n", 0, pos) + 1
    b = text.find("\n", pos)
    return line_no, text[a:b if b != -1 else len(text)].strip()


def _to_iso(groups, kind):
    if kind == "ymd":
        y, m, d = groups
    elif kind == "mdy":
        m, d, y = groups
    elif kind == "dmy":
        d, m, y = groups
    elif kind == "Mdy":
        mon, d, y = groups
        m = MONTH_NUM[mon[:3].lower()]
    else:
        d, mon, y = groups
        m = MONTH_NUM[mon[:3].lower()]
    try:
        return dt.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def find_dates(text):
    found = {}
    for pat, kind in DATE_PATTERNS:
        for m in pat.finditer(text):
            iso = _to_iso(m.groups(), kind)
            if iso and not any(s <= m.start() < e for s, e in found):
                line_no, line = _line_info(text, m.start())
                found[(m.start(), m.end())] = DateCand(m.start(), m.end(), m.group(0), line_no, line, iso)
    return sorted(found.values(), key=lambda c: c.start)


# Table header whose weight column carries the unit, e.g. "Weight (lb)" (v2 pilot format P1).
HEADER_UNIT_RE = re.compile(r"\b(?:weight|wt)\s*\((lbs?|kgs?)\)", re.I)
NUMBER_RE = re.compile(r"(?<![\w./])(\d{1,3}(?:\.\d{1,2})?)(?![\w./])")


def _weight(text, start, raw, value, unit, signed):
    line_no, line = _line_info(text, start)
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", start)
    c = WeightCand(start, start + len(raw), raw, line_no, line, value, unit, signed, start - a)
    c.full_line = text[a:b if b != -1 else len(text)]
    return c


def _header_unit_weights(text):
    """Bare numbers sitting under a 'Weight (unit)' column header, until the next blank line."""
    out, lines, pos = [], text.split("\n"), 0
    starts = []
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    for i, ln in enumerate(lines):
        for h in HEADER_UNIT_RE.finditer(ln):
            col_a = h.start()
            nxt = re.search(r"\s{2,}\S", ln[h.end():])
            col_b = h.end() + nxt.start() + 1 if nxt else len(ln) + 40
            for j in range(i + 1, len(lines)):
                if not lines[j].strip():
                    break
                for m in NUMBER_RE.finditer(lines[j]):
                    if col_a - 2 <= m.start() < col_b:
                        out.append(_weight(text, starts[j] + m.start(), m.group(1), float(m.group(1)),
                                           UNIT[h.group(1).lower()], False))
    return out


def find_weights(text):
    out = [_weight(text, m.start(), m.group(0), abs(float(m.group(1))), UNIT[m.group(2).lower()],
                   m.group(1)[0] in "+-")
           for m in WEIGHT_RE.finditer(text)]
    taken = [(c.start, c.end) for c in out]
    out += [c for c in _header_unit_weights(text) if not any(s <= c.start < e for s, e in taken)]
    return sorted(out, key=lambda c: c.start)
