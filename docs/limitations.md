# Data and limitations

## Data

No public veterinary records with visit dates and weights could be found, so the ground truth is the
real (de-identified, date-shifted) outpatient weights of the MIMIC-IV Clinical Database Demo, placed
into synthetic PDF layouts. See [data/README.md](../data/README.md) for the source and license.

## Limitations

- **Synthetic layouts.** The values are real but the layouts are generated: digital PDFs with no scans,
  OCR noise or handwriting. Results are not directly comparable to OT09's 83% on real veterinary records.
- **Not pure raw-text extraction.** Both methods rely on the same regex candidate extractor, so this
  measures "regex candidates + model decisions", not the model reading values from raw text by itself.
- **Weak v1 baseline.** The v1 rules have no encounter segmentation, and a stronger traditional rule set
  would likely score higher on T5. [v2](v2.md) addresses this.
- **Same author for system and test formats.** The extraction system and the test formats were written
  by the same author. Development was restricted to the pilot, but the test formats were not designed
  blind.
- **Dates.** MIMIC dates are shifted into 2100-2200.
