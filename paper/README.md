# Research paper: Knowledge Desk

`main.tex` is an IEEE journal-format paper (IEEEtran). `main.pdf` is the compiled version.

Every number, table and figure in the paper is generated from raw experiment output; none is typed by hand.

| Folder | Contents |
| --- | --- |
| `experiments/corpus.py` | Deterministic synthetic enterprise corpus and labelled question generator |
| `experiments/run_experiments.py` | Retrieval ablation, access control, answer guard, faithfulness, audit, scaling (writes `results.json`) |
| `experiments/run_guard.py` | Entity-span guard experiment (writes `results_guard.json`) |
| `experiments/run_formats.py` | Eight-format parsing robustness (writes `results_formats.json`) |
| `experiments/make_artifacts.py` | Results to `tables/*.tex`, `figures/*.pdf` and `tables/numbers.tex` (macros used in the text) |
| `refs/verify_refs.py` | Looks every reference up in arXiv / Crossref and writes `refs.bib` only from the retrieved metadata |

## Reproduce

```powershell
cd backend
.venv\Scripts\python -m pip install matplotlib
cd ..\paper\experiments
..\..\backend\.venv\Scripts\python run_experiments.py        # about 30 min
..\..\backend\.venv\Scripts\python run_guard.py              # about 20 min
..\..\backend\.venv\Scripts\python run_formats.py            # about 2 min
..\..\backend\.venv\Scripts\python make_artifacts.py
cd ..
tectonic main.tex                                           # or upload paper/ to Overleaf
```

## Before submitting
- Fill the author names, department and contact in `main.tex` (placeholders are in square brackets).
- Acknowledgements: mention the industry contact only in wording that person has approved.
- Make the GitHub repository public (or change the Availability section) and add a licence.
- The benchmark is synthetic; see the Discussion and Limitations section before claiming more than it supports.
