# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-office desktop tool that automates a hospital's daily HIS (Hospital Information System) report. Staff upload ~9 raw Excel exports (bed occupancy, OP/IP admissions & discharges, billing, AEPL credit postings, etc.), the tool detects which file is which report, computes every figure the "Final output" workbook needs, and writes/exports that workbook. Runs as a desktop app (FastAPI backend + React frontend, wrapped in pywebview) or as two dev servers.

## Commands

Setup (from repo root):
```
npm run setup   # pip install -r requirements.txt + npm install (root) + npm install (frontend)
```

Dev (backend + frontend together, backend on :8000, frontend on :5173 via Vite):
```
npm run dev
```
Or individually: `npm run dev:backend` / `npm run dev:frontend`.

Backend tests (pytest, no config file — run from repo root so `backend.*` imports resolve):
```
pytest backend/tests
pytest backend/tests/test_billing.py
pytest backend/tests/test_billing.py::test_process_billing_op_filters_o_b_only   # single test
```
Note: some tests (`test_date_detection.py`, `test_detection.py::test_detects_all_9_reports_from_real_sample_workbook`, `test_loading.py`, `test_long_stay_patients.py`) depend on a real sample workbook (`Daily report to automate.xlsx`) that isn't checked into the repo — they fail with `FileNotFoundError` unless that file is present locally. That's expected, not a regression.

Frontend (from `frontend/`):
```
npm run dev       # Vite dev server
npm run build     # production build -> frontend/dist (this is what the exe bundles)
npm run lint      # oxlint
```

Packaging a distributable desktop exe (Windows, from repo root):
```
build.bat
```
Builds the frontend, creates an isolated `.venv`, then runs PyInstaller with `build_exe.spec` to produce `dist/HospitalReportAutomation.exe`.

## Architecture

**Desktop shell**: `launcher.py` starts the FastAPI app (`backend.main:app`) via uvicorn in a background thread, then opens it in a native window with pywebview (falls back to the default browser if the WebView2 runtime is missing). `window.pywebview.api.*` (the `Api` class in launcher.py) exposes native OS dialogs/actions the browser sandbox can't do itself (folder picker, opening a folder in Explorer) — the frontend feature-detects `window.pywebview?.api` and shows a "desktop app only" message otherwise.

**Dual runtime paths** (`backend/runtime_paths.py`): the app runs both from source (repo root) and as a frozen PyInstaller onefile exe, and these need different writable/read-only locations. `FROZEN` (checked via `sys.frozen`) switches between them. Read-only shipped assets (built frontend, default config/template) live in `BUNDLE_DIR` (`sys._MEIPASS` when frozen). Writable data (`config/*.json`, `backend/data/*.json`, generated output workbooks) lives next to the exe (`%APPDATA%\HospitalReportAutomation`) when frozen so it survives restarts, or at the repo root when running from source. `ensure_runtime_files()` seeds the writable config dir from the bundle on first frozen launch. Any new persistent file must be wired through this module, not hardcoded — this is the one seam that makes "works from source" and "works as a shipped exe" both true.

**Report pipeline** (`backend/stages/`): each of the 9 report types is one pipeline stage — a pure function taking an already-loaded pandas DataFrame and returning computed values, no file I/O. `backend/stages/pipeline.py::run_pipeline()` wires all stages together into one flat `values` dict keyed to match `final_output.ROW_MAP`. `backend/stages/detection.py` figures out which uploaded file/sheet is which report type (by sheet name + column-signature matching); `backend/stages/loading.py` turns the detected mapping into the DataFrames the pipeline consumes. `backend/main.py`'s `/detect` and `/process` endpoints are the two-step flow the frontend drives: detect first (so the user can confirm/override auto-matched files), then process.

**Category mapping** (`backend/stages/category_mapping.py` + `config/category_map.json`): raw "Category" values from HIS exports (CPR, ECHS, TPA, etc., with year-suffixed variants like "CPR 26") get normalized and mapped to a fixed bucket + Domestic/International region. Values with no match go to `backend/stages/category_review.py`'s review queue instead of silently miscounting; the frontend's Category Review panel lets staff resolve them, and resolutions are `overrides` (run-scoped, keyed by `normalize_loose(raw_value)`) threaded through nearly every stage function — never written back to the master `category_map.json`. Confirmed overrides can be persisted separately as "learned overrides" (`backend/stages/learned_overrides.py`, `config/learned_overrides.json`) so the same correction doesn't need reconfirming every day.

**Final output workbook** (`backend/stages/final_output.py`): `ROW_MAP` is the single source of truth mapping each Final-output sheet row number to the metric key the pipeline produces — this is the contract between `run_pipeline()`'s output and the spreadsheet layout. `write_final_output()` loads `config/final_output_template.xlsx`, writes today's values into a caller-specified date column, and (via `backend/monthly_average.py` + `backend/stages/mtd.py`) computes/writes the Daily Average and MTD (Proj) columns next to it. Rows not in `ROW_MAP` are never touched by code — e.g. the manually-filled "Collection (INR)" section exists only as template layout, not as computed output.

**Daily history / MTD** (`backend/stages/daily_history.py`, `config/daily_history.json`, `backend/history_store.py`): the app processes one day at a time and has no other memory of past days, so true month-to-date figures require persisting each day's values as they're computed (`record_day`, keyed by month → metric → day-of-month). Metrics are classified in `mtd.py` as cumulative (sum/average over recorded days, then projected across the full month), average-style/snapshot (e.g. Occupancy %, averaged not summed — projecting a point-in-time reading is meaningless), or constant (Bed Strength). A completed month rolls over from the live 3-column block into a static 2-column pair (`finalize_month()` in `monthly_average.py`) inserted just left of the "Particulars" column, using however many days were actually recorded that month (not the calendar length) — a month the automation joined mid-way still gets a real average instead of staying blank.

**Verification** (`backend/verification.py`): an independent, best-effort recompute of key figures (e.g. Total Billing) directly from the raw source DataFrames, run after the main pipeline purely as a diagnostic cross-check. It must never turn a successful pipeline run into a hard error — failures are logged and swallowed (`_run_verification_safely` in main.py).

**Format validation** (`backend/format_validator.py`): before processing, uploaded files are checked against `backend/data/schema_baselines.json` (expected column names per report type). A genuine schema mismatch blocks the run with a specific "which report, which missing column" error rather than a downstream KeyError; baselines can be reset per-category if the HIS export format has legitimately changed.

**Error surfacing**: stage functions raise `ValueError` (never bare `KeyError`) for "expected column not found" — `KeyError.__str__()` wraps its message in extra stray quotes, which used to leak as garbled text into the frontend's error banner. `backend/stages/pipeline.py`'s `StageProcessingError` wraps whatever a stage raises with which report label failed, so `/process` can tell the user which specific uploaded file was the problem instead of a generic failure.
