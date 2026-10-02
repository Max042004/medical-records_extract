# How it works (v1)

## Data

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

## Shared step: candidate extraction (`src/candidates.py`)

`pdftotext -layout` turns each PDF into text. Regular expressions then list every date and every
number with a weight unit, including distractors. BMI (`kg/m2`) and dose units (`mg/kg`) are excluded.
Both methods depend on this step.

## Rules baseline (`src/extract.py`, `rules`)

1. Drop signed numbers, and numbers preceded by words such as change, goal or previous.
2. Drop dates preceded by words such as DOB, born, drawn or printed.
3. Assign each remaining weight to the nearest preceding date.

All keyword lists were written from the pilot formats only.

## JevK5 (`src/extract.py`, `jevk5`)

The full record text is the evidence for every question. Each weight gets two typed questions:

1. **Gate (yes/no):** "Is the value "127 lb" in the line "…" a body weight measured at a visit?" Weight
   changes and goal weights should be answered no.
2. **Date (choice):** "On which date was this body weight measured?" The options are up to 15 candidate
   dates nearest to the weight, plus NONE.

The answer is read from the next-token log-probabilities of the option letters
(`src/jevk5_client.py`, following the model card) and calibrated with the model's published temperature
(1.316).

## Weighted accuracy (`src/score.py`)

WA = 3E / (3E + 3P + 3H + 2O + 1N), the formula from OT09. The abstract does not define the categories
precisely; this project uses the following one-to-one matching per record:

| Code | Category | Definition |
|---|---|---|
| E | Exact match | date and weight (value + unit) equal a ground-truth pair |
| P | Partial match | only the date or only the weight equals a still-unmatched ground-truth pair |
| H | Hallucination | a predicted pair matching no ground-truth pair on either field |
| O | Omission | a ground-truth pair left unmatched |
| N | Non-compliance | an output that is not a valid (ISO date, number, unit) triple |

## Speed

On a MacBook Air M4 (16 GB), the 50 test records took 47 minutes, a median of 12.7 s per weight
candidate. That run used llama.cpp's default server settings.

**Server settings.** `run_server.sh` now uses one slot with frequent context checkpoints
(`-np 1 -ub 256 -cms 64`). The model's hybrid Qwen3.5 layers can only reuse a cached prefix from a
checkpoint. In a check on one record, successive questions ran about 2.8× faster with identical answers.
