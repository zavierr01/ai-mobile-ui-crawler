# Testing Patterns

**Analysis Date:** 2026-05-01

## Test Framework

**Runner:**
- `pytest` (configured in `pyproject.toml` and `pytest.ini`)
- Config: `pyproject.toml` (`[tool.pytest.ini_options]`) and `pytest.ini`

**Assertion Library:**
- Built-in `assert` with `pytest` helpers (`pytest.raises`, fixtures)

**Run Commands:**
```bash
pytest                                  # Run all tests
pytest -k "main_window"                 # Focused run pattern used in this repo
pytest --cov=mobile_crawler --cov-report=html --cov-report=term-missing  # Coverage
```

## Test File Organization

**Location:**
- Primary tests under `tests/`, grouped by layer (`tests/cli`, `tests/core`, `tests/domain`, `tests/infrastructure`, `tests/ui`, `tests/integration`, `tests/unit`).
- Legacy root-level test file also exists: `test_droidrun_integration.py`.

**Naming:**
- Files: `test_*.py` (example: `tests/infrastructure/test_database.py`)
- Classes: `Test*` (example: `class TestDatabaseManager` in `tests/infrastructure/test_database.py`)
- Functions: `test_*` (example: `test_schema_creation` in `tests/infrastructure/test_database.py`)

**Structure:**
```text
tests/
├── conftest.py
├── cli/
├── core/
├── domain/
├── infrastructure/
├── integration/
├── ui/
└── unit/
```

## Test Structure

**Suite Organization:**
```python
class TestCrawlCommand:
    @patch('mobile_crawler.cli.commands.crawl.DatabaseManager')
    def test_crawl_command_basic(...):
        runner = CliRunner()
        result = runner.invoke(cli, ['crawl', ...])
        assert result.exit_code == 0
```
Pattern source: `tests/cli/test_crawl_command.py`

**Patterns:**
- Setup pattern: heavy use of `@pytest.fixture` for app objects, repos, temp DBs (`tests/conftest.py`, `tests/infrastructure/test_database.py`, `tests/ui/test_main_window.py`)
- Teardown pattern: `yield` fixtures with cleanup after yield (temp files/db/UI windows) (`tests/infrastructure/test_database.py`, `tests/ui/test_main_window.py`)
- Assertion pattern: direct state/output assertions, often multiple checks per scenario (`tests/core/test_stuck_detector.py`, `tests/ui/test_run_history_view.py`)

## Mocking

**Framework:** `unittest.mock` (`Mock`, `MagicMock`, `patch`) + `pytest` `monkeypatch`

**Patterns:**
```python
@patch('mobile_crawler.cli.commands.crawl.RunRepository')
def test_crawl_command_basic(...):
    mock_run_repo = Mock()
    mock_run_repo.create_run.return_value = 123
```
From `tests/cli/test_crawl_command.py`

```python
monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
```
From `tests/ui/test_run_history_view.py`

**What to Mock:**
- External dependencies (ADB/process calls in `tests/integration/conftest.py`)
- Network/service clients (`requests.Session` in `tests/domain/providers/test_openrouter_adapter.py`)
- UI dialogs and service wiring (`tests/ui/test_main_window.py`, `tests/ui/test_run_history_view.py`)

**What NOT to Mock:**
- Core pure logic and state transitions (`tests/core/test_crawl_state_machine.py`, `tests/core/test_stuck_detector.py`)
- Dataclass/value behavior (`tests/unit/reporting/test_generator.py`)

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def db_manager(temp_db_path):
    manager = DatabaseManager(temp_db_path)
    yield manager
    manager.close()
```
From `tests/infrastructure/test_database.py`

**Location:**
- Shared fixtures: `tests/conftest.py`
- Integration-specific fixtures: `tests/integration/conftest.py`
- Local per-module fixtures: inside each `test_*.py`

## Coverage

**Requirements:** No minimum threshold enforced; coverage collection is enabled by default via pytest addopts in `pyproject.toml`.

**View Coverage:**
```bash
pytest --cov=mobile_crawler --cov-report=html --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Pure logic and component behavior in `tests/core`, `tests/domain`, `tests/unit`

**Integration Tests:**
- Cross-component and filesystem/database flows in `tests/integration/test_artifact_grouping.py` and `tests/integration/test_export_consolidation.py`
- Device-dependent flows with runtime skip behavior in `tests/integration/conftest.py`

**E2E Tests:**
- Present as live external-service tests (example: `tests/integration/test_mailosaur_e2e.py`), using real SMTP/API integration paths

## Common Patterns

**Async Testing:**
```python
Not used; tests are synchronous pytest functions.
```

**Error Testing:**
```python
with pytest.raises(ValueError, match="Invalid transition"):
    machine.transition_to(CrawlState.RUNNING)
```
From `tests/core/test_crawl_state_machine.py`

---

*Testing analysis: 2026-05-01*
