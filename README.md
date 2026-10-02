# Local decision model for extracting visit dates and body weights from medical-record PDFs

This project builds on an ACVIM 2026 Forum abstract from the Chu Lab (Texas A&M). It uses a
**decision model that runs entirely on a laptop**, so record text never leaves the machine.

**Original study:** Chang, Arkenberg, Creevy & Chu, *Using Artificial Intelligence for Scalable Data
Extraction From Medical Records in the Dog Aging Project*, abstract OT09, 2026 ACVIM Forum,
J Vet Intern Med 40(5), [doi:10.1093/jvimsj/aalag196](https://doi.org/10.1093/jvimsj/aalag196).

- **Task:** extract every (visit date, body weight) pair from heterogeneous PDF records.
- **Design:** 59 records with 559 pairs. Rules and prompts were developed on a pilot set of 9 records,
  then applied to 50 more records that included formats unseen in the pilot.
- **Results:** a commercial veterinary LLM (VetRec) reached a weighted accuracy (WA) of 83%, against
  51% for a rule-based method. The LLM produced 46 non-compliant (malformed) outputs.

**This project** replaces the cloud LLM with **JevK5-9B**, a local decision model. A decision model does
not generate text: it returns a probability for each option of a typed question. So every output is a
valid (date, weight) pair by construction.

> **Data is human, not veterinary.** No public veterinary records with visit dates and weights could be
> found, so the ground truth is the real (de-identified, date-shifted) outpatient weights of the
> MIMIC-IV Clinical Database Demo, placed into synthetic PDF layouts. See [Limitations](#limitations).

**Status:**

- **v1 (below) is complete.** Its results are the current results of this project.
- **v2 is still being tested.** It is a closer replication of OT09 with 23 formats and 559 pairs; see
  [v2 (in progress)](#v2-in-progress).

## Results (v1)

The test set has 50 records and 168 ground-truth pairs. Formats T4 and T5 never appear in the pilot set.

| Format | Rules | JevK5-9B (local) |
|---|---:|---:|
| T1 vitals flowsheet | 100.0% | 100.0% |
| T2 SOAP progress notes | 100.0% | 97.2% |
| T3 narrative letter | 67.8% | 100.0% |
| T4 multi-column summary (unseen in pilot) | 44.3% | 86.2% |
| T5 timeline, imaging date right above each weight (unseen in pilot) | 0.0% | 97.8% |
| **Total WA** | **64.6%** | **96.6%** |
| Exact / partial / hallucination / omission / non-compliance | 107 / 54 / 0 / 7 / 0 | 161 / 0 / 1 / 7 / 0 |

**Pilot set** (9 records, 27 pairs): rules 92.6%, JevK5 100%. Prompts and rules were frozen before the
test run.

### Findings

- **Rules break on unseen layouts.** The rules assign each weight to the nearest preceding date. On T5
  that is the imaging date printed right above the weight, so every pair is wrong (0%). This is the
  failure OT09 describes. JevK5 reads the context and scores 97.8% on T5.
- **A yes/no gate was needed.** The first JevK5 version only asked "which date?". It assigned weight
  changes (e.g. "-8 lb") to visit dates and scored 75% on the pilot. Asking first "is this a body weight
  measured at a visit?" fixed it: the gate made no errors on the 41 pilot weight candidates it was
  checked on, and the pilot score rose to 100%.
- **Non-compliance is 0 for both methods by construction.** The model can only pick from listed options.
- **Confidence flags the mistakes.** All 5 wrong JevK5 decisions (out of 228) had probability below 0.7.
  Sending the 8 decisions under 0.7 (3.5%) to a human reviewer would catch every one of them.

### Error analysis

| Errors | Cause | Kind of problem |
|---|---|---|
| 7 omissions | The question names the target weight by its value and its line. When identical values repeat, e.g. `141 lb   141 lb` in one T4 row, the question cannot tell them apart. Six of the seven were on a single line. | Design of the question, not the model |
| 1 hallucination | The model gave 280 lb the date of the "previous visit" written in the same line. Its confidence was 0.53. | Genuine model error |

## How it works (v1)

### Data

`src/make_docs.py` renders each MIMIC-IV Demo patient's weights into one of five PDF layouts, adding
distractor dates and numbers:

| Format | Layout | Dates / unit | Main distractors |
|---|---|---|---|
| T1 | vitals flowsheet table | MM/DD/YYYY, lb | BP-only dates, DOB, printed date |
| T2 | SOAP progress notes | YYYY-MM-DD, lb | lab-draw date between visit date and weight; previous weight; weight change; goal weight |
| T3 | narrative letter | Month D, YYYY, kg | weight written before its date; admission dates |
| T4 | multi-column summary | MM/DD/YYYY, lb | dates in a header row, weights in the row below |
| T5 | clinical timeline | DD-Mon-YYYY, kg | an imaging date directly above each weight |

**Split:** the pilot is 9 records (T1-T3) with 27 pairs. The test is 50 records (T1-T5, ten of each)
with 168 pairs.

### Shared step: candidate extraction (`src/candidates.py`)

`pdftotext -layout` turns each PDF into text. Regular expressions then list every date and every
number with a weight unit, including distractors. BMI (`kg/m2`) and dose units (`mg/kg`) are excluded.
Both methods depend on this step.

### Rules baseline (`src/extract.py`, `rules`)

1. Drop signed numbers, and numbers preceded by words such as change, goal or previous.
2. Drop dates preceded by words such as DOB, born, drawn or printed.
3. Assign each remaining weight to the nearest preceding date.

All keyword lists were written from the pilot formats only.

### JevK5 (`src/extract.py`, `jevk5`)

The full record text is the evidence for every question. Each weight gets two typed questions:

1. **Gate (yes/no):** "Is the value "127 lb" in the line "…" a body weight measured at a visit?" Weight
   changes and goal weights should be answered no.
2. **Date (choice):** "On which date was this body weight measured?" The options are up to 15 candidate
   dates nearest to the weight, plus NONE.

The answer is read from the next-token log-probabilities of the option letters
(`src/jevk5_client.py`, following the model card) and calibrated with the model's published temperature
(1.316).

### Weighted accuracy (`src/score.py`)

WA = 3E / (3E + 3P + 3H + 2O + 1N), the formula from OT09. The abstract does not define the categories
precisely; this project uses the following one-to-one matching per record:

| Code | Category | Definition |
|---|---|---|
| E | Exact match | date and weight (value + unit) equal a ground-truth pair |
| P | Partial match | only the date or only the weight equals a still-unmatched ground-truth pair |
| H | Hallucination | a predicted pair matching no ground-truth pair on either field |
| O | Omission | a ground-truth pair left unmatched |
| N | Non-compliance | an output that is not a valid (ISO date, number, unit) triple |

### Speed

On a MacBook Air M4 (16 GB), the 50 test records took 47 minutes, a median of 12.7 s per weight
candidate. That run used llama.cpp's default server settings. `run_server.sh` now uses settings that
reuse the cached record between questions; see [Reproduce](#reproduce).

## v2 (in progress)

v2 is still being tested. Its results will be added once the test run is complete.

It follows OT09's design more closely:

- **Scale:** 59 records, 49 patients and exactly 559 pairs, with 10 patients contributing two records.
- **Formats:** a pilot of 9 records in 9 formats (P1-P9), and a 50-record test set that adds 14 formats
  never seen in the pilot (U1-U14).
- **Rules:** encounter segmentation is added. A weight is assigned to the date that opens its visit
  segment, a classic pre-LLM technique, which makes the baseline much stronger.
- **JevK5:** questions name the weight value only ("On which date was 74.4 kg measured?") and the record
  text is not modified. A value that appears n times in a record takes the n highest-ranked dates.

The relevant files are:

- `src/make_docs_v2.py`, `src/extract_v2.py` and `src/report_v2.py`
- `data/docs_v2/`
- `results/v2/`, where `archive/` keeps every pilot iteration

## Reproduce

Requires macOS on Apple Silicon (for the bundled llama.cpp build), Python 3.10+ and poppler.

```bash
brew install poppler
scripts/setup.sh                      # MIMIC demo tables, llama.cpp, JevK5 model (6.47 GB), venv
.venv/bin/python src/make_docs.py     # regenerate data/docs (deterministic seed)
./run_server.sh                       # in a second terminal; serves the model on 127.0.0.1:8080
cd src
../.venv/bin/python extract.py rules test
../.venv/bin/python extract.py jevk5 test     # resumes from results/v1/pred_jevk5_test.json
../.venv/bin/python score.py ../results/v1/pred_rules_test.json ../results/v1/pred_jevk5_test.json
```

**Server settings.** `run_server.sh` uses one slot with frequent context checkpoints
(`-np 1 -ub 256 -cms 64`). The model's hybrid Qwen3.5 layers can only reuse a cached prefix from a
checkpoint. In a check on one record, successive questions ran about 2.8× faster with identical answers.

## Limitations

- **Synthetic layouts.** The values are real but the layouts are generated: digital PDFs with no scans,
  OCR noise or handwriting. Results are not directly comparable to OT09's 83% on real veterinary records.
- **Not pure raw-text extraction.** Both methods rely on the same regex candidate extractor, so this
  measures "regex candidates + model decisions", not the model reading values from raw text by itself.
- **Weak v1 baseline.** The v1 rules have no encounter segmentation, and a stronger traditional rule set
  would likely score higher on T5. v2 addresses this.
- **Same author for system and test formats.** The extraction system and the test formats were written
  by the same author. Development was restricted to the pilot, but the test formats were not designed
  blind.
- **Dates.** MIMIC dates are shifted into 2100-2200.

## Credits and licenses

- **Data:** MIMIC-IV Clinical Database Demo v2.2 (Johnson et al., 2023, PhysioNet,
  [doi:10.13026/dp1f-ex47](https://doi.org/10.13026/dp1f-ex47)), ODbL v1.0. The derived data in
  `data/` and `results/` is shared under ODbL; see [data/README.md](data/README.md).
- **Model:** [JevK5-9B GGUF](https://huggingface.co/alibiserikbay/JevK5-GGUF) (Apache-2.0), a community
  alternative to TypeSafe's Jev that is not affiliated with TypeSafe. Not included; downloaded by the
  setup script.
- **Runtime:** [llama.cpp](https://github.com/ggml-org/llama.cpp) (MIT). Not included.
