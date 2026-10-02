# Data notice

The PDFs and `ground_truth.json` files in `data/docs/` and `data/docs_v2/`, and the prediction
files in `results/`, are derived from the **MIMIC-IV Clinical Database Demo v2.2**:

> Johnson, A., Bulgarelli, L., Pollard, T., Horng, S., Celi, L. A., & Mark, R. (2023).
> MIMIC-IV Clinical Database Demo (version 2.2). PhysioNet. https://doi.org/10.13026/dp1f-ex47

The demo is released under the [Open Data Commons Open Database License v1.0 (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/).
The derived data in this repository is shared under the same license.

The dates are MIMIC's de-identified, date-shifted dates (years 2100-2200), and the body weights are
the `Weight (Lbs)` rows of the demo's `omr` table. The page layouts, distractor dates and distractor
numbers in the PDFs are synthetic (see `src/make_docs.py` and `src/make_docs_v2.py`).

The raw demo tables are not stored here; `scripts/setup.sh` downloads them from PhysioNet.
