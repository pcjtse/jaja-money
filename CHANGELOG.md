# Changelog

All notable changes to jaja-money are documented here.

## [0.1.0.0] - 2026-05-10

### Added
- **Scheduled Overnight Batch Analysis (P23.1)** — new `src/services/scheduler.py` service
  that scores every watchlist ticker nightly using APScheduler. Populates
  `analysis_history` and seeds `signal_returns`, enabling Signal Quality, Factor
  Attribution, and ML weight retraining pages to function without manual runs.
- **Batch run tracking** — new `batch_runs` SQLite table records each batch run's
  status, processed/error counts, symbols scored, and duration. Accessible via
  `save_batch_run` / `get_last_batch_run` in `src/data/history.py`.
- **Batch Analysis sidebar** on the Signal Quality page — shows last run status
  (✅/⚠️/❌/⏳), next scheduled run countdown, and a "Run Batch Now" button for
  on-demand scoring.
- **Config support** for `batch_analysis` section in `config.yaml` (enabled,
  schedule_hour, schedule_minute) with matching `_Config` properties.
- Priority 23 feature backlog (P23.1–P23.6) added to `todo.md`.

### Fixed
- Test isolation bug in `tests/test_openclaw_skill.py` — three tests were directly
  mutating `sys.modules["src.analysis.factors"].compute_factors` without cleanup,
  contaminating the scheduler tests when the full suite ran. Replaced with proper
  `patch()` context managers.
- Engineering debt TODOs (TODO-001 through TODO-004) resolved.
- Mock earnings calendar date made dynamic (was hardcoded to a past date).
