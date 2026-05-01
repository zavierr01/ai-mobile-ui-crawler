# Codebase Concerns

**Analysis Date:** 2026-05-01

## Tech Debt

**Secret storage path inconsistency:**
- Issue: secrets are saved as encrypted values in `secrets` table from `src/mobile_crawler/ui/widgets/settings_panel.py:673-757`, but also written as plain settings in `src/mobile_crawler/ui/main_window.py:509-533`.
- Files: `src/mobile_crawler/ui/widgets/settings_panel.py`, `src/mobile_crawler/ui/main_window.py`, `src/mobile_crawler/infrastructure/user_config_store.py`
- Impact: duplicated credential paths, accidental plaintext persistence, and inconsistent runtime reads.
- Fix approach: route all API keys through `UserConfigStore.set_secret_plaintext()` and stop writing keys via `ConfigManager.set()`.

**Error suppression in core paths:**
- Issue: exceptions are swallowed with `except Exception: pass/continue` in runtime-critical code.
- Files: `src/mobile_crawler/infrastructure/database.py:305-306`, `src/mobile_crawler/core/crawler_loop.py:283-286`, `src/mobile_crawler/domain/droidrun_agent_service.py:91-93`
- Impact: failures become silent, root-cause analysis is slow, and partial failures appear as successful execution.
- Fix approach: replace blanket suppression with typed exceptions and structured logging including context (`run_id`, `step_number`, operation).

**Monolithic classes increase change risk:**
- Issue: UI/controller files are very large and hold mixed responsibilities.
- Files: `src/mobile_crawler/ui/main_window.py` (~1249 lines), `src/mobile_crawler/ui/widgets/settings_panel.py` (~853 lines), `src/mobile_crawler/domain/droidrun_agent_service.py` (~729 lines)
- Impact: high regression probability and difficult localized testing.
- Fix approach: split orchestration, UI composition, and persistence concerns into smaller modules with explicit interfaces.

**Packaging and test config drift:**
- Issue: duplicated test configuration exists in both `pytest.ini` and `pyproject.toml`, and `requirements.txt` does not represent full runtime dependencies.
- Files: `pytest.ini`, `pyproject.toml`, `requirements.txt`
- Impact: non-reproducible local environments and different behavior between `pytest` invocations.
- Fix approach: keep a single pytest config source and generate/maintain one authoritative dependency manifest.

## Known Bugs

**Pre-crawl device validation uses wrong attribute:**
- Symptoms: validation fails with a generic device connectivity error even when device is attached.
- Files: `src/mobile_crawler/core/pre_crawl_validator.py:130`
- Trigger: any validation path calling `_check_device_connected()` with connected devices.
- Workaround: change `d.id` to `d.device_id`.

**Replicate API key lookup mismatch:**
- Symptoms: OmniParser Replicate backend reports missing key even after saving key in settings.
- Files: `src/mobile_crawler/domain/omni_parser_client.py:114`, `src/mobile_crawler/ui/widgets/settings_panel.py:786-789`
- Trigger: local key saved as `replicate_api_key`; runtime lookup expects `omniparser_replicate_api_key`.
- Workaround: read `replicate_api_key` (or migrate key names with backward-compatible fallback).

**CLI tests fail on default test command:**
- Symptoms: `ModuleNotFoundError: No module named 'mobile_crawler'` during collection.
- Files: `pytest.ini`, `tests/cli/test_config_command.py`
- Trigger: running `pytest` with `pytest.ini` (missing `pythonpath = src`).
- Workaround: add `pythonpath = src` to `pytest.ini` or remove duplicated config file.

## Security Considerations

**Hardcoded third-party credential in test code:**
- Risk: repository contains a static API credential in test source.
- Files: `tests/integration/test_mailosaur_e2e.py`
- Current mitigation: Not detected.
- Recommendations: remove hardcoded secret, load only from environment/secure store, rotate exposed token.

**Plaintext key file generated in project root:**
- Risk: startup script writes MobSF API key to plaintext file.
- Files: `scripts/start.ps1:396-410`, `src/mobile_crawler/ui/widgets/settings_panel.py:627-650`
- Current mitigation: `.mobsf_api_key` is gitignored in `.gitignore:70`.
- Recommendations: avoid filesystem plaintext storage; pass key via process env or secret store and delete transient artifacts immediately.

**Secrets can be echoed to terminal:**
- Risk: `config get` prints decrypted secret values to stdout.
- Files: `src/mobile_crawler/cli/commands/config.py:97-101`
- Current mitigation: output prefix `[ENCRYPTED]` only labels the value but still reveals plaintext.
- Recommendations: redact by default and add explicit `--show-secret` confirmation flow.

## Performance Bottlenecks

**Inefficient run lookup path:**
- Problem: single run fetch performs full-table query then Python-side search.
- Files: `src/mobile_crawler/infrastructure/run_repository.py:75-85`
- Cause: `get_run_by_id()` delegates to `get_all_runs()`.
- Improvement path: add direct SQL query `SELECT * FROM runs WHERE id = ?`.

**ADB-heavy per-device metadata fetch:**
- Problem: each detected device triggers multiple sequential `adb shell getprop` calls.
- Files: `src/mobile_crawler/infrastructure/device_detection.py:185-205`
- Cause: property-by-property subprocess invocation.
- Improvement path: fetch all props once (`getprop`) and parse in memory.

**PCAP parsing caps and low-fidelity HTTPS handling:**
- Problem: parser stops at 1000 requests and represents HTTPS as `https://unknown`.
- Files: `src/mobile_crawler/reporting/parsers/pcap_parser.py:8-50`
- Cause: hardcoded cap and placeholder TLS parsing.
- Improvement path: stream parse with configurable cap and add SNI/host extraction.

## Fragile Areas

**Private-method coupling across UI widgets:**
- Files: `src/mobile_crawler/ui/main_window.py:791-795`, `src/mobile_crawler/ui/main_window.py:889-892`
- Why fragile: parent widget calls child internals (`_is_full_response`, `_load_runs`) instead of stable public API.
- Safe modification: expose explicit public methods in `AIMonitorPanel` and `RunHistoryView`; update call sites to public contracts only.
- Test coverage: limited direct contract tests for these widget interactions.

**Global logging side effects at import time:**
- Files: `src/mobile_crawler/domain/droidrun_agent_service.py:43-52`
- Why fragile: root logger filters are modified during module import and affect unrelated logging paths.
- Safe modification: register filters in explicit startup wiring and make it idempotent.
- Test coverage: no targeted tests asserting logger isolation across modules.

## Scaling Limits

**Single-process, local-SQLite execution model:**
- Current capacity: one crawler process with local file DB (`src/mobile_crawler/infrastructure/database.py`).
- Limit: concurrent multi-device crawl orchestration is constrained by process/thread model.
- Scaling path: isolate run execution workers and move persistence to a multi-writer datastore.

**Growing local artifacts per run:**
- Current capacity: artifacts are always materialized into session folders (`src/mobile_crawler/core/crawler_loop.py:141-143`).
- Limit: disk growth and slower run history operations over long-lived usage.
- Scaling path: retention policy + archival for old runs + lazy loading in history UI.

## Dependencies at Risk

**DroidRun submodule compatibility drift:**
- Risk: tight runtime coupling to external submodule internals and async handler types.
- Impact: upstream API changes can break crawler loop and cleanup.
- Migration plan: wrap submodule calls behind a compatibility adapter and pin tested commit ranges.
- Files: `.gitmodules`, `src/mobile_crawler/domain/droidrun_agent_service.py`

## Missing Critical Features

**Continuous integration pipeline:**
- Problem: repository has no detected CI workflow for tests/linting.
- Blocks: reliable regression detection before merge.
- Files: `.github/` (no `workflows/*.yml` detected)

## Test Coverage Gaps

**Security-sensitive credential flow testing:**
- What's not tested: prevention of plaintext secret persistence and secret redaction in CLI output.
- Files: `src/mobile_crawler/ui/main_window.py`, `src/mobile_crawler/cli/commands/config.py`, `tests/cli/test_config_command.py`
- Risk: credential leakage remains undetected.
- Priority: High

**Failure-path and recovery assertions:**
- What's not tested: schema migration failures, suppressed listener exceptions, and crawler loop cleanup under exceptions.
- Files: `src/mobile_crawler/infrastructure/database.py`, `src/mobile_crawler/core/crawler_loop.py`
- Risk: latent runtime failures appear only in production sessions.
- Priority: High

**Integration tests depend on live external systems:**
- What's not tested: deterministic offline equivalents for auth/mail workflows.
- Files: `tests/integration/test_auth_e2e.py`, `tests/integration/test_mailosaur_e2e.py`
- Risk: flaky test outcomes and reduced confidence in CI adoption.
- Priority: Medium

---

*Concerns audit: 2026-05-01*
