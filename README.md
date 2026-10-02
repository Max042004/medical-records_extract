# Local decision model for extracting visit dates and body weights from medical-record PDFs

This project replicates the design of an ACVIM 2026 Forum abstract from the Chu Lab (Texas A&M) with a
**decision model that runs entirely on a laptop**, so record text never leaves the machine.

**Original study:** Chang, Arkenberg, Creevy & Chu, *Using Artificial Intelligence for Scalable Data
Extraction From Medical Records in the Dog Aging Project*, abstract OT09, 2026 ACVIM Forum,
J Vet Intern Med 40(5), [doi:10.1093/jvimsj/aalag196](https://doi.org/10.1093/jvimsj/aalag196).

- **Task:** extract every (visit date, body weight) pair from heterogeneous PDF records.
- **Design:** 59 PDF records, 49 dogs, 559 pairs. Rules and prompts were developed on a pilot set of
  9 records in 9 formats, then applied to 50 more records that included 14 formats unseen in the pilot.
- **Results:** a commercial veterinary LLM (VetRec) reached a weighted accuracy of 83%, against 51% for
  a rule-based method. The LLM produced 46 non-compliant (malformed) outputs.

**This project** keeps that design (9 pilot formats, 14 unseen formats, 59 records, 49 patients,
559 pairs) and replaces the cloud LLM with **JevK5-9B**, a local decision model. A decision model does
not generate text: it returns a probability for each option of a typed question. So every output is a
valid (date, weight) pair by construction.

> **Data is human, not veterinary.** No public veterinary records with visit dates and weights could be
> found, so the ground truth is the real (de-identified, date-shifted) outpatient weights of the
> MIMIC-IV Clinical Database Demo, placed into synthetic PDF layouts. See [Limitations](#limitations).

## Results

**Status: partial run.** The JevK5 test run stopped at **37 of 50 test records**. The 13 records not yet
processed are the second copies of P1-P9 and the third copies of U1-U4. Every comparison below scores
the rules baseline on exactly the same records as JevK5. `python src/report_v2.py` reproduces this table.

| Subset | Records | Pairs | JevK5 WA | JevK5 E/P/H/O/N | Rules WA | Rules E/P/H/O/N |
|---|---:|---:|---:|---|---:|---|
| Pilot (P1-P9) | 9 | 93 | 98.2% | 92/0/1/1/0 | 100.0% | 93/0/0/0/0 |
| Test, finished records | 37 | 313 | 94.7% | 294/5/2/14/0 | 79.4% | 247/54/2/12/0 |
| &nbsp;&nbsp;unseen formats (U1-U14) | 28 | 223 | 93.4% | 204/5/0/14/0 | 74.1% | 164/48/2/11/0 |
| &nbsp;&nbsp;pilot formats (P1-P9) | 9 | 90 | 97.8% | 90/0/2/0/0 | 92.6% | 83/6/0/1/0 |
| **All finished records (OT09-style)** | **46** | **406 / 559** | **95.5%** | 386/5/3/15/0 | **84.2%** | 340/54/2/12/0 |

- The rules baseline on the full 50-record test set scores 84.7% WA.
- **Hardware:** MacBook Air M4, 16 GB.
- **Speed:** about 15 s per distinct weight value, which is two model calls.

### Weighted accuracy

WA = 3E / (3E + 3P + 3H + 2O + 1N), the formula from OT09. The abstract does not define the categories
precisely; this project uses the following one-to-one matching per record (`src/score.py`):

| Code | Category | Definition |
|---|---|---|
| E | Exact match | date and weight (value + unit) equal a ground-truth pair |
| P | Partial match | only the date or only the weight equals a still-unmatched ground-truth pair |
| H | Hallucination | a predicted pair matching no ground-truth pair on either field |
| O | Omission | a ground-truth pair left unmatched |
| N | Non-compliance | an output that is not a valid (ISO date, number, unit) triple |

### What the errors show

**JevK5 handles unseen layouts better.** Examples by format (JevK5 / rules):

| Format | JevK5 | Rules |
|---|---:|---:|
| U1, dates in a header row with weights in the row below | 100% | 28% |
| U12, a later "synced" date on the same line as the weight | 100% | 0% |
| P3, narrative letters | 100% | 66% |

**Encounter segmentation makes the rules much stronger.** On U2 (an imaging date directly above each
weight, the failure OT09 describes), rules score 100% once weights are assigned to the date that opens
their visit segment. The first experiment's rules had no segmentation and scored 0% there.

**The "rank by occurrence" rule causes most JevK5 errors.** A value that appears n times is asked
once, and its occurrences take the top n options. This fails in two ways:

- **Mentions are not always separate measurements.** "previous 172.7 lb on …" repeats an earlier
  weight, so an extra, wrong date is taken. This produced the P2 hallucinations.
- **NONE lands inside the top n.** It then hides a real repeat measurement. This produced the U2, U3
  and U5 omissions, and P6 in the pilot.

On U14 (79.2%), the model sometimes took a check-in's *scheduled* date instead of its *completed* date
for repeated values.

**Both methods score 0% on U9 (`01 22 2147`) and U13 (`2147/01/22`).** These date formats never appear
in the pilot, so the pilot-derived candidate extractor does not recognise them.

**Non-compliance is 0 for both methods by construction.** The model can only pick from listed options.

## How it works

### Data: 23 formats

`src/make_docs_v2.py` takes the 49 MIMIC-IV Demo patients with the most dated weights. Ten of them get
two records covering consecutive date ranges, for 59 PDFs and exactly 559 pairs. Each record is
rendered in one of 23 formats, each with its own distractors:

| Pilot formats | | Unseen formats (test only) | |
|---|---|---|---|
| P1 | vitals flowsheet, unit only in the column header | U1 | dates in a header row, weights below |
| P2 | SOAP notes: lab-draw date, previous weight, weight change, goal | U2 | timeline with an imaging date above each weight |
| P3 | narrative letter, weight sometimes before its date | U3 | referral: weights newest first, date in parentheses |
| P4 | billing statement with payment dates | U4 | two-column page: problem list with diagnosis dates |
| P5 | European dotted dates, lab collected/reported dates | U5 | weight column before date column |
| P6 | dosing record: "(measured date)", mg/kg doses | U6 | portal messages with a sent date |
| P7 | nursing intake form, tetanus and next-appointment dates | U7 | wellness rows with a "next due" date |
| P8 | discharge summary: weight-trend list, dry-weight target | U8 | nursing flowsheet with times and an order date |
| P9 | EHR export lines with an "entered" date | U9 | claim form with spaced dates (`MM DD YYYY`) |
| | | U10 | physiotherapy: goal body mass with a target date |
| | | U11 | nutrition: usual and ideal body weight |
| | | U12 | connected-scale log with a later "synced" date |
| | | U13 | anthropometrics table, `YYYY/MM/DD`, unit in header |
| | | U14 | care-plan check-ins: scheduled vs completed date, target weight |

**Split:** the pilot is one record in each of P1-P9. The test is 50 records covering U1-U14 and P1-P9.

### Shared step: candidate extraction (`src/candidates.py`)

`pdftotext -layout` turns each PDF into text. Regular expressions then list every date and every
number with a weight unit, including distractors. Weights are numbers followed by lb or kg, or numbers
under a column header such as "Weight (lb)". BMI (`kg/m2`) and dose units (`mg/kg`) are excluded.

The supported date formats are the ones seen in the pilot. **Both methods depend on this step:** a date
or weight it misses cannot be recovered.

### Rules baseline (`src/extract_v2.py`, `rules`)

1. **Drop non-measurements.** Remove signed numbers, and numbers preceded by words such as goal, target
   or previous.
2. **Drop non-visit dates.** Remove dates preceded on their own line by words such as DOB, collected,
   reported, entered or payment.
3. **Pair each weight with a date:**
   1. a date on the weight's own line (the nearest one), otherwise
   2. the date that opens the encounter segment the weight sits in, otherwise
   3. the nearest preceding date.

   A segment opens at a line that starts with a date, or with "Date of service:", "Visit date:" or
   "CLINIC VISIT" followed by a date.

### JevK5 (`src/extract_v2.py`, `jevk5`)

The unmodified record text is the evidence for every question. Equal values are grouped, and each
distinct value gets two typed questions:

1. **Gate (yes/no):** "Does the record give 74.4 kg as the patient's own body weight on some date?",
   rejecting weight changes and goal or target weights.
2. **Date (choice):** "On which date was the body weight 74.4 kg measured?" The options are up to 15
   candidate dates nearest to the value's occurrences, plus NONE.

A value that occurs n times takes the n highest-ranked options in order. The answer is read from the
next-token log-probabilities of the option letters (`src/jevk5_client.py`, following the model card)
and calibrated with the model's published temperature (1.316).

### Pilot development log (test formats were not used)

| Step | Change | Pilot WA | Kept in |
|---|---|---:|---|
| Rules | keyword lists and same-line rule; fixed a keyword window that crossed into the previous line | 87.8% → 100% | `archive/pilot_rules_no-segmentation.json` |
| Rules | encounter segmentation added | 100% | `pred_rules_pilot.json` |
| JevK5 a | one question per occurrence, target quoted with its line | 99.3% | `archive/pilot_jevk5_a_line-quote.json` |
| JevK5 b | target marked inside the record text; rejected by design choice, stopped | — | `archive/pilot_jevk5_b_in-text-marker_partial.json` |
| JevK5 c | value-only questions with the rank rule; gate asked "measured at a visit?" | 92.3% | `archive/pilot_jevk5_c_rank_gate-visit.json` |
| JevK5 d | gate asked "a measured body weight?" | 95.3% | `archive/pilot_jevk5_d_rank_gate-measured.json` |
| **JevK5 final** | gate asks whether the record gives the value as the patient's weight on some date; 0/87 gate errors on pilot values | **98.2%** | `pred_jevk5_pilot.json` |

Files are under `results/v2/`. Prompts and rules were frozen before the test run.

## Earlier experiment (v1)

This was a smaller first design: 5 formats (T1-T3 pilot, T4-T5 unseen), 59 records and 168 test pairs.
JevK5 asked one question per occurrence and quoted the occurrence's line. The rules had no segmentation.

| | Pilot WA | Test WA |
|---|---:|---:|
| Rules (no segmentation) | 92.6% | 64.6% |
| JevK5 | 100% | 96.6% |

Seven of the eight JevK5 test errors came from repeated identical values that a line quote could not
tell apart; six of them sat on a single line. Files are in `data/docs/` and `results/v1/`, and the scripts are `src/make_docs.py` and
`src/extract.py`.

## Reproduce

Requires macOS on Apple Silicon (for the bundled llama.cpp build), Python 3.10+ and poppler.

```bash
brew install poppler
scripts/setup.sh                      # MIMIC demo tables, llama.cpp, JevK5 model (6.47 GB), venv
.venv/bin/python src/make_docs_v2.py  # regenerate data/docs_v2 (deterministic seed)
./run_server.sh                       # in a second terminal; serves the model on 127.0.0.1:8080
cd src
../.venv/bin/python extract_v2.py rules all
../.venv/bin/python extract_v2.py jevk5 pilot
../.venv/bin/python extract_v2.py jevk5 test   # resumes from results/v2/pred_jevk5_test.json
../.venv/bin/python report_v2.py
```

**Server settings.** `run_server.sh` uses one slot with frequent context checkpoints
(`-np 1 -ub 256 -cms 64`). The model's hybrid Qwen3.5 layers can only reuse a cached prefix from a
checkpoint, and with these settings successive questions about the same record were about 2.8× faster
with identical answers.

## Limitations

- **Synthetic layouts.** The values are real but the layouts are generated: digital PDFs with no scans,
  OCR noise or handwriting. Results are not directly comparable to OT09's 83% on real veterinary records.
- **Not pure raw-text extraction.** Both methods rely on the same regex candidate extractor, so this
  measures "regex candidates + model decisions". A design where the model reads values itself (fixed
  option sets such as month 1-12 and digits 0-9) was discussed but not run.
- **Same author for system and test formats.** The extraction system and the test formats were written
  by the same author. Development was restricted to the pilot, but the test formats were not designed
  blind.
- **Partial run.** 13 test records were not processed by JevK5.
- **Dates.** MIMIC dates are shifted into 2100-2200.

## Credits and licenses

- **Data:** MIMIC-IV Clinical Database Demo v2.2 (Johnson et al., 2023, PhysioNet,
  [doi:10.13026/dp1f-ex47](https://doi.org/10.13026/dp1f-ex47)), ODbL v1.0. The derived data in
  `data/` and `results/` is shared under ODbL; see [data/README.md](data/README.md).
- **Model:** [JevK5-9B GGUF](https://huggingface.co/alibiserikbay/JevK5-GGUF) (Apache-2.0), a community
  alternative to TypeSafe's Jev that is not affiliated with TypeSafe. Not included; downloaded by the
  setup script.
- **Runtime:** [llama.cpp](https://github.com/ggml-org/llama.cpp) (MIT). Not included.
