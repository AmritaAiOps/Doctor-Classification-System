# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Daily HIS Report Automation — a local web tool for a hospital office PC. The user uploads daily Excel exports from the Hospital Information System; the backend detects which report each sheet is, runs a processing pipeline, and writes figures into a copy of `config/final_output_template.xlsx` (`Final output.xlsx`), downloadable from the UI. Single-user, single-PC by design (see the RUN_STATE comment in `backend/main.py`).

## Commands

```
npm run setup                 # pip install -r requirements.txt + npm installs (root + frontend)
npm run dev                   # backend (uvicorn :8000) + frontend (vite :5173) concurrently
npm run dev:backend           # python -m uvicorn backend.main:app --reload --port 8000
python -m pytest backend/tests                          # all tests
python -m pytest backend/tests/test_billing.py          # one file
python -m pytest backend/tests/test_billing.py -k name  # one test
npm run lint --prefix frontend                          # oxlint
npm run build --prefix frontend                         # vite build -> frontend/dist
```

Run Python from the repo root — everything imports as `backend.*`.

## Architecture

**Backend** (Python / FastAPI / pandas): `backend/main.py` holds all HTTP routes: `/detect`, `/process`, `/download/{id}`, `/category-review`, `/category-review/resolve`. Flow:

1. `/detect` — reads first 20 rows of every sheet in every uploaded file; `stages/detection.py` fuzzy-identifies the report type per sheet, `stages/date_detection.py` guesses the report date. Frontend shows the proposed mapping for confirmation.
2. `/process` — `stages/loading.py` builds one DataFrame per report type from the confirmed mapping, then `stages/pipeline.py::run_pipeline` runs stages 1–7 (one module per report: `simple_counters`, `cat_dependent_counts`, `long_stay_patients`, `billing`, `billing_aggregation`, `aepl_billing`) producing a flat `values` dict keyed to `final_output.ROW_MAP`. Any stage failure raises `StageProcessingError(label, reason)` so the API names the offending report instead of a generic 500.
3. `_write_output` — `stages/daily_history.py::record_day` persists today's figures, `stages/mtd.py` computes MTD/daily-average columns, `stages/final_output.py` writes everything into the template.
4. Category review loop — `/process` keeps the run in in-memory `RUN_STATE`; `/category-review/resolve` applies user bucket corrections and re-runs the pipeline without re-uploading.

**Category mapping** has three layers, deliberately separate:
- `config/category_map.json` — master raw-category → bucket table (never written at runtime; rebuilt by `scripts/build_category_map.py`).
- `config/learned_overrides.json` — user-confirmed exceptions persisted across days (`stages/learned_overrides.py`).
- Run-scoped overrides passed through `run_pipeline(overrides=...)` from the Category Review panel.
Buckets are the fixed 5-value enum in `main.py::VALID_BUCKETS`; unmatched values are excluded from category totals and surfaced as warnings. Fuzzy matching lives in `stages/category_mapping.py` (rapidfuzz).

**Runtime files** (all resolved relative to repo root via `Path(__file__)`): `config/*.json` (some read/write), `config/final_output_template.xlsx`, `data/outputs/<uuid>/Final output.xlsx`.

**Frontend** (React 19 + Vite, `frontend/src/App.jsx` is essentially the whole app): calls the API with relative URLs; `frontend/vite.config.js` proxies the four API paths to :8000 in dev.

## Conventions

- Every non-trivial stage module has a matching `backend/tests/test_<stage>.py` — add/update one when touching a stage.
- API errors return `{"status": "error", "failed_file": ..., "reason": ...}` with plain-language reasons, not raised exceptions (except 404s).
