# Findings and error analysis (v1)

Results are in the [README](../README.md#results-v1).

## Findings

- **Rules break on unseen layouts.** The rules assign each weight to the nearest preceding date. On T5
  that is the imaging date printed right above the weight, so every pair is wrong (0%). This is the
  failure OT09 describes. JevK5 reads the context and scores 97.8% on T5.
- **A yes/no gate was needed.** The first JevK5 version only asked "which date?". It assigned weight
  changes (e.g. "-8 lb") to visit dates and scored 75% on the pilot. Asking first "is this a body weight
  measured at a visit?" fixed it: the gate made no errors on the 41 pilot weight candidates it was
  checked on, and the pilot score rose to 100%.

## JevK5 errors on the test set

| Errors | Cause | Kind of problem |
|---|---|---|
| 7 omissions | The question names the target weight by its value and its line. When identical values repeat, e.g. `141 lb   141 lb` in one T4 row, the question cannot tell them apart. Six of the seven were on a single line. | Design of the question, not the model |
| 1 hallucination | The model gave 280 lb the date of the "previous visit" written in the same line. Its confidence was 0.53. | Genuine model error |

Per-decision logs (chosen option and probability for every weight) are in
`results/v1/pred_jevk5_test.json`.
