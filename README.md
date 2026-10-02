# Local decision model for extracting visit dates and body weights from medical-record PDFs

This project builds on an ACVIM 2026 Forum abstract from the Chu Lab (Texas A&M). But uses
decision model.

**Original study:** Chang, Arkenberg, Creevy & Chu, *Using Artificial Intelligence for Scalable Data
Extraction From Medical Records in the Dog Aging Project*, abstract OT09, 2026 ACVIM Forum,
J Vet Intern Med 40(5)

- **Task:** extract every (visit date, body weight) pair from heterogeneous PDF records.
- **Design:** 59 records with 559 pairs. Rules and prompts were developed on a pilot set of 9 records,
  then applied to 50 more records that included formats unseen in the pilot.
- **Results:** a commercial veterinary LLM (VetRec) reached a weighted accuracy (WA) of 83%, against
  51% for a rule-based method. The LLM produced 46 non-compliant (malformed) outputs.

**This project** replaces the cloud LLM with **JevK5-9B**, a local decision model. A decision model does
not generate text: it returns a probability for each option of a typed question. So every output is a
valid (date, weight) pair by construction.

> **Data using human medical records dataset since veterinary medical records lacks open dataset.**

**Status:**

- **v1 (below) is complete.** Its results are the current results of this project.
- **v2 is still being tested.** It is a closer replication of OT09 with 23 formats and 559 pairs; see
  [docs/v2.md](docs/v2.md).

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

### result
- **Non-compliance is 0 for both methods by construction.** The model can only pick from listed options.
- **Confidence flags the mistakes.** All 5 wrong JevK5 decisions (out of 228) had probability below 0.7.
  Sending the 8 decisions under 0.7 (3.5%) to a human reviewer would catch every one of them.

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

## More details

- [Methods](docs/methods.md): data formats, candidate extraction, rules, JevK5 questions, WA definitions, speed
- [Findings and error analysis](docs/error-analysis.md)
- [Data and limitations](docs/limitations.md)
- [v2 (in progress)](docs/v2.md)

## Credits and licenses

- **Data:** MIMIC-IV Clinical Database Demo v2.2 (Johnson et al., 2023, PhysioNet,
  [doi:10.13026/dp1f-ex47](https://doi.org/10.13026/dp1f-ex47)), ODbL v1.0. The derived data in
  `data/` and `results/` is shared under ODbL; see [data/README.md](data/README.md).
- **Model:** [JevK5-9B GGUF](https://huggingface.co/alibiserikbay/JevK5-GGUF) (Apache-2.0), a community
  alternative to TypeSafe's Jev that is not affiliated with TypeSafe. Not included; downloaded by the
  setup script.
- **Runtime:** [llama.cpp](https://github.com/ggml-org/llama.cpp) (MIT). Not included.
