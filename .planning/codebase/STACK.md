# Technology Stack

**Analysis Date:** 2026-05-01

## Languages

**Primary:**
- Python 3.9+ - Core app, CLI/GUI, crawling, integrations in `src/mobile_crawler/` and entrypoints `run_cli.py`, `run_ui.py`.

**Secondary:**
- PowerShell - Local orchestration scripts in `scripts/start.ps1`.
- SQL (SQLite dialect) - Schema and persistence in `src/mobile_crawler/infrastructure/database.py` and `src/mobile_crawler/infrastructure/user_config_store.py`.

## Runtime

**Environment:**
- CPython 3.9+ (`requires-python = ">=3.9"` in `pyproject.toml`).
- Desktop runtime with local Android tooling (`adb`) and optional local services (Appium, MobSF, Ollama) configured in `scripts/start.ps1` and `src/mobile_crawler/config/defaults.py`.

**Package Manager:**
- pip/setuptools (build backend in `pyproject.toml`).
- Lockfile: missing at repository root (no `poetry.lock`, `Pipfile.lock`, or `uv.lock` outside submodule `external/droidrun/`).

## Frameworks

**Core:**
- PySide6 >=6.6.0 - Desktop GUI (`src/mobile_crawler/ui/main_window.py`).
- Click >=8.1.0 - CLI commands (`src/mobile_crawler/cli/main.py`, `src/mobile_crawler/cli/commands/*.py`).
- DroidRun (git submodule) - traversal/agent engine loaded from `external/droidrun` via `src/mobile_crawler/domain/droidrun_agent_service.py`.

**Testing:**
- pytest (configured in `pyproject.toml` and `pytest.ini`).
- pytest-cov / pytest-qt (dev extras in `pyproject.toml`).

**Build/Dev:**
- setuptools (`pyproject.toml`).
- Ruff + Black + isort (`pyproject.toml`, `.pre-commit-config.yaml`).
- pre-commit hooks (`.pre-commit-config.yaml`).

## Key Dependencies

**Critical:**
- `google-genai` - Gemini integration in `src/mobile_crawler/domain/providers/gemini_adapter.py`.
- `requests` - HTTP integrations (OpenRouter, MobSF, OmniParser local) in `src/mobile_crawler/domain/providers/openrouter_adapter.py`, `src/mobile_crawler/infrastructure/mobsf_manager.py`, `src/mobile_crawler/domain/omni_parser_client.py`.
- `ollama` - local LLM integration in `src/mobile_crawler/domain/providers/ollama_adapter.py`.
- `PySide6` - application UI in `src/mobile_crawler/ui/`.
- `cryptography` - secret encryption in `src/mobile_crawler/infrastructure/user_config_store.py`.

**Infrastructure:**
- `appium-python-client` declared in `pyproject.toml`; Appium server orchestration in `scripts/start.ps1`.
- `mailosaur` (`requirements.txt`) with service wrapper in `src/mobile_crawler/infrastructure/mailosaur/service.py`.
- `jinja2` and `dpkt` (`requirements.txt`) for report generation/parsing in `src/mobile_crawler/reporting/generator.py` and `src/mobile_crawler/reporting/parsers/pcap_parser.py`.
- `easyocr`, `pytesseract`, `imagehash`, `Pillow` for visual analysis in `src/mobile_crawler/domain/grounding/ocr_engine.py` and related modules.

## Configuration

**Environment:**
- Configuration precedence is SQLite → `CRAWLER_*` env vars → defaults (`src/mobile_crawler/config/config_manager.py`).
- Defaults are centralized in `src/mobile_crawler/config/defaults.py`.
- Secrets are persisted encrypted in `user_config.db` (`src/mobile_crawler/infrastructure/user_config_store.py`).
- `.env` file present at repo root; use for local environment configuration only (content not analyzed).

**Build:**
- Packaging and tool config in `pyproject.toml`.
- CLI/GUI script entrypoints defined in `pyproject.toml` under `[project.scripts]`.

## Platform Requirements

**Development:**
- Python 3.9+, pip, and virtualenv.
- Android Debug Bridge (ADB) for device actions (`src/mobile_crawler/domain/adb_action_executor.py`).
- Optional Node.js/npx and Docker to run Appium + MobSF via `scripts/start.ps1`.

**Production:**
- Local desktop execution target (CLI/GUI).
- Android device/emulator connectivity via ADB.
- Optional local services for advanced features: Ollama (`http://localhost:11434`), MobSF (`http://localhost:8000`), Appium (`127.0.0.1:4723`).

---

*Stack analysis: 2026-05-01*
