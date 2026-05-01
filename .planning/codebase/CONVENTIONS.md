# Coding Conventions

**Analysis Date:** 2026-05-01

## Naming Patterns

**Files:**
- Use `snake_case.py` for source and test modules (examples: `src/mobile_crawler/core/stuck_detector.py`, `tests/core/test_stuck_detector.py`).
- Name tests with `test_*.py` (examples: `tests/cli/test_main.py`, `tests/ui/test_main_window.py`).

**Functions:**
- Use `snake_case` for functions/methods (examples: `record_screen_visit()` in `src/mobile_crawler/core/stuck_detector.py`, `test_cli_help()` in `tests/cli/test_main.py`).
- Prefix internal helpers with `_` (examples: `_create_services()` in `src/mobile_crawler/ui/main_window.py`, `_create_signal_adapter()` in `tests/ui/test_signal_adapter.py`).

**Variables:**
- Use `snake_case` for local/module variables (examples: `mock_config_manager` in `tests/cli/test_crawl_command.py`, `stale_run_cleaner` in `src/mobile_crawler/ui/main_window.py`).
- Use `UPPER_SNAKE_CASE` for constants (examples: `APP_PACKAGE` in `tests/integration/test_auth_e2e.py`).

**Types:**
- Use `PascalCase` for classes, enums, dataclasses (examples: `DatabaseManager` in `src/mobile_crawler/infrastructure/database.py`, `ActionResult` in `src/mobile_crawler/domain/models.py`).
- Prefer explicit typing via `typing` and built-in generics (examples: `Optional[Path]` in `src/mobile_crawler/infrastructure/database.py`, `list[Callable[..., None]]` in `src/mobile_crawler/core/crawl_controller.py`).

## Code Style

**Formatting:**
- Tool used: Black + Ruff formatter via pre-commit (`.pre-commit-config.yaml`).
- Key settings:
  - Line length: `120` (`pyproject.toml` `[tool.black]`, `[tool.ruff]`)
  - Target Python: `py39` (`pyproject.toml` `[tool.black]`, `[tool.ruff]`)

**Linting:**
- Tool used: Ruff (`pyproject.toml` `[tool.ruff.lint]`).
- Key rules:
  - Enabled families: `E`, `W`, `F`, `I`, `B`, `C4`, `UP`
  - Common ignores: `E501`, `B008`, `C901`
  - Per-file ignores: `__init__.py` allows unused imports; `tests/**/*` allows `B011`

## Import Organization

**Order:**
1. Standard library imports (example in `src/mobile_crawler/core/crawl_controller.py`: `logging`, `threading`, `typing`, `enum`)
2. Third-party imports (example in `src/mobile_crawler/cli/commands/crawl.py`: `click`)
3. First-party absolute imports from `mobile_crawler.*` (example in `src/mobile_crawler/cli/commands/crawl.py`)

**Path Aliases:**
- Not used. Import project code through absolute package paths rooted at `mobile_crawler` (example: `from mobile_crawler.infrastructure.database import DatabaseManager` in `tests/infrastructure/test_database.py`).

## Error Handling

**Patterns:**
- Catch broad exceptions at process boundaries, then report and exit gracefully (example: CLI command wrapper in `src/mobile_crawler/cli/commands/crawl.py`).
- Catch sink/listener failures and continue processing (examples: `LoggingService.log()` in `src/mobile_crawler/core/logging_service.py`, `_notify_state_change()` in `src/mobile_crawler/core/crawl_controller.py`).
- Use `pytest.raises(...)` for expected failure paths in tests (example: `tests/core/test_crawl_state_machine.py`).

## Logging

**Framework:** Python `logging` + custom sink abstraction (`src/mobile_crawler/core/logging_service.py`, `src/mobile_crawler/core/log_sinks.py`)

**Patterns:**
- Create module-level logger with `logging.getLogger(__name__)` (example: `src/mobile_crawler/core/stuck_detector.py`).
- Keep structured event output as JSON when needed (example: `JSONEventListener` in `src/mobile_crawler/cli/commands/crawl.py`).
- Use `print(..., file=sys.stderr)` only as fallback in logging infrastructure (example: `src/mobile_crawler/core/logging_service.py`).

## Comments

**When to Comment:**
- Add module/class/function docstrings consistently (examples throughout `src/mobile_crawler/...` and `tests/...`).
- Use inline comments for intent and platform nuance (examples: Windows lock retry comment in `tests/infrastructure/test_database.py`, precedence notes in `src/mobile_crawler/config/config_manager.py`).

**JSDoc/TSDoc:**
- Not applicable (Python codebase). Use Python docstrings instead.

## Function Design

**Size:**  
- Prefer small focused methods for state/query behavior (example: property methods in `src/mobile_crawler/core/stuck_detector.py`).

**Parameters:**  
- Use explicit typed parameters and defaults for optional behavior (examples: `initialize(..., safety_settings: Optional[Dict[str, Any]] = None)` in `src/mobile_crawler/domain/providers/openrouter_adapter.py`; `crawl(..., provider: Optional[str], ...)` in `src/mobile_crawler/cli/commands/crawl.py`).

**Return Values:**  
- Return domain objects/dataclasses for structured data (example: `ActionResult` in `src/mobile_crawler/domain/models.py`).
- Return `None` for command-style mutators and side-effect methods (example: `ConfigManager.set()` in `src/mobile_crawler/config/config_manager.py`).

## Module Design

**Exports:**  
- Prefer direct imports from concrete modules instead of barrel re-exports (examples: `from mobile_crawler.infrastructure.database import DatabaseManager` in multiple files).

**Barrel Files:**  
- Minimal use; `__init__.py` is mainly package marker (examples: `src/mobile_crawler/__init__.py`, `tests/__init__.py`).

---

*Convention analysis: 2026-05-01*
