# Codebase Structure

**Analysis Date:** 2026-05-01

## Directory Layout

```text
mobile-crawler/
├── src/mobile_crawler/          # Main application package
│   ├── cli/                     # Click CLI group + command modules
│   ├── ui/                      # PySide6 main window + widgets/resources
│   ├── core/                    # Crawl orchestration, lifecycle, logging bridges
│   ├── domain/                  # Service logic, providers, models, reporting facade
│   ├── infrastructure/          # SQLite/repos, ADB/system integration, managers
│   ├── config/                  # Defaults, config manager, app-data path helpers
│   └── reporting/               # Report contracts/parsers/templates/generator
├── tests/                       # Layered pytest suites (ui/core/domain/infra/etc.)
├── external/droidrun/           # Vendored submodule used by DroidRunAgentService
├── scripts/                     # PowerShell startup automation
├── docs/                        # User-facing guides
├── run_cli.py                   # CLI bootstrap
├── run_ui.py                    # GUI bootstrap
└── pyproject.toml               # Packaging/tooling config
```

## Directory Purposes

**`src/mobile_crawler/cli`:**
- Purpose: Command-line entry and subcommand dispatch.
- Contains: `main.py`, `commands/crawl.py`, `commands/config.py`, `commands/report.py`, `commands/list.py`, `commands/delete.py`.
- Key files: `src/mobile_crawler/cli/main.py`, `src/mobile_crawler/cli/commands/crawl.py`.

**`src/mobile_crawler/ui`:**
- Purpose: Desktop UI composition and event wiring.
- Contains: `main_window.py`, `signal_adapter.py`, `widgets/*.py`, `resources/*`.
- Key files: `src/mobile_crawler/ui/main_window.py`, `src/mobile_crawler/ui/signal_adapter.py`.

**`src/mobile_crawler/core`:**
- Purpose: Crawl lifecycle orchestration and state/control primitives.
- Contains: `crawler_loop.py`, `crawl_controller.py`, `crawl_state_machine.py`, `crawler_event_listener.py`, `log_sinks.py`.
- Key files: `src/mobile_crawler/core/crawler_loop.py`, `src/mobile_crawler/core/crawler_event_listener.py`.

**`src/mobile_crawler/domain`:**
- Purpose: Business/service logic for DroidRun integration, providers, reporting.
- Contains: `droidrun_agent_service.py`, `providers/*`, `grounding/*`, `models.py`, `report_generator.py`.
- Key files: `src/mobile_crawler/domain/droidrun_agent_service.py`, `src/mobile_crawler/domain/providers/registry.py`.

**`src/mobile_crawler/infrastructure`:**
- Purpose: DB schema/repositories and external system adapters.
- Contains: `database.py`, `*_repository.py`, `user_config_store.py`, `session_folder_manager.py`, `device_detection.py`, `mobsf_manager.py`.
- Key files: `src/mobile_crawler/infrastructure/database.py`, `src/mobile_crawler/infrastructure/run_repository.py`.

**`tests`:**
- Purpose: Automated test suites by concern/layer.
- Contains: `tests/ui`, `tests/core`, `tests/domain`, `tests/infrastructure`, `tests/integration`, `tests/unit`.
- Key files: `tests/conftest.py`, `tests/ui/test_main_window.py`, `tests/infrastructure/test_database.py`.

## Key File Locations

**Entry Points:**
- `run_cli.py`: Python CLI bootstrap to `mobile_crawler.cli.main:run`.
- `run_ui.py`: Python GUI bootstrap to `mobile_crawler.ui.main_window:run`.
- `src/mobile_crawler/cli/main.py`: Click group and command registration.
- `src/mobile_crawler/ui/main_window.py`: GUI construction and application `run()` function.

**Configuration:**
- `pyproject.toml`: package metadata, script entry points, lint/test tool config.
- `src/mobile_crawler/config/config_manager.py`: precedence-based config access (DB → env → defaults).
- `src/mobile_crawler/config/defaults.py`: default runtime settings.
- `src/mobile_crawler/config/paths.py`: OS-specific app-data root.

**Core Logic:**
- `src/mobile_crawler/core/crawler_loop.py`: run orchestration and event emission.
- `src/mobile_crawler/domain/droidrun_agent_service.py`: DroidRun execution adapter and cleanup.
- `src/mobile_crawler/infrastructure/database.py`: schema/migration entry.
- `src/mobile_crawler/infrastructure/session_folder_manager.py`: artifact directory policy.

**Testing:**
- `pytest.ini`: test path/markers.
- `tests/`: main suite root.
- `test_droidrun_integration.py`: standalone integration smoke script.

## Naming Conventions

**Files:**
- Python modules use `snake_case.py` (`crawler_loop.py`, `run_repository.py`, `ai_model_selector.py`).
- Tests use `test_*.py` (`tests/ui/test_main_window.py`, `tests/domain/test_prompt_builder.py`).

**Directories:**
- Top-level package areas map to architecture layers (`core`, `domain`, `infrastructure`, `ui`, `cli`, `config`).
- UI-specific components are grouped under `ui/widgets/`.

## Where to Add New Code

**New Feature:**
- Primary code: start in `src/mobile_crawler/domain/` for feature logic, `src/mobile_crawler/core/` for orchestration hooks.
- Integration adapters: place external/API/DB interactions in `src/mobile_crawler/infrastructure/`.
- UI wiring (if needed): `src/mobile_crawler/ui/main_window.py` plus dedicated widget in `src/mobile_crawler/ui/widgets/`.
- Tests: mirror layer under `tests/domain/`, `tests/core/`, `tests/infrastructure/`, or `tests/ui/`.

**New Component/Module:**
- CLI command: add module under `src/mobile_crawler/cli/commands/` and register in `src/mobile_crawler/cli/main.py`.
- Domain service: add `snake_case` module under `src/mobile_crawler/domain/`.
- Repository/table logic: add under `src/mobile_crawler/infrastructure/` and update `database.py` schema/migration paths.

**Utilities:**
- Shared cross-layer helper: `src/mobile_crawler/utils/` (currently minimal; prefer explicit layer placement first).
- UI-only helper: `src/mobile_crawler/ui/` or `src/mobile_crawler/ui/widgets/`.

## Special Directories

**`external/droidrun`:**
- Purpose: Submodule dependency for exploration engine.
- Generated: No (versioned submodule checkout).
- Committed: Yes.

**`src/mobile_crawler/reporting/templates`:**
- Purpose: Jinja2 HTML report templates.
- Generated: No.
- Committed: Yes.

**`src/mobile_crawler/ui/resources`:**
- Purpose: Qt resource manifest + compiled resource module.
- Generated: `resources_rc.py` is generated from `resources.qrc`.
- Committed: Yes.

**`htmlcov`:**
- Purpose: pytest coverage HTML output.
- Generated: Yes.
- Committed: No (artifact directory).

---

*Structure analysis: 2026-05-01*
