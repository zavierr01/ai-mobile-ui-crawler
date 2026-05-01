# External Integrations

**Analysis Date:** 2026-05-01

## APIs & External Services

**AI Model Providers:**
- Google Gemini - primary hosted vision model calls.
  - SDK/Client: `google-genai` in `src/mobile_crawler/domain/providers/gemini_adapter.py`
  - Auth: `gemini_api_key` secret or env fallback `GEMINI_API_KEY` / `GOOGLE_API_KEY` in `src/mobile_crawler/domain/droidrun_agent_service.py`
- OpenRouter - hosted multi-model chat completions.
  - SDK/Client: `requests` in `src/mobile_crawler/domain/providers/openrouter_adapter.py`
  - Auth: `openrouter_api_key` secret (Bearer token)
- Ollama (local) - local model inference.
  - SDK/Client: `ollama` in `src/mobile_crawler/domain/providers/ollama_adapter.py`
  - Auth: Not required (local endpoint, default `http://localhost:11434`)

**Mobile Automation & Analysis Services:**
- DroidRun submodule - agent execution engine imported from `external/droidrun` by `src/mobile_crawler/domain/droidrun_agent_service.py`.
  - SDK/Client: local Python package path injection (`sys.path` add)
  - Auth: provider-specific API keys passed into DroidRun config
- MobSF - static Android security analysis.
  - SDK/Client: `requests` in `src/mobile_crawler/infrastructure/mobsf_manager.py`
  - Auth: `mobsf_api_key` in `Authorization` header
- PCAPdroid - network capture via Android intent API.
  - SDK/Client: ADB command execution in `src/mobile_crawler/domain/traffic_capture_manager.py`
  - Auth: optional `pcapdroid_api_key`
- OmniParser (Replicate/local backend) - UI element parsing.
  - SDK/Client: `replicate` package (lazy import) and `requests` in `src/mobile_crawler/domain/omni_parser_client.py`
  - Auth: `replicate_api_key` or env `REPLICATE_API_KEY`
- Mailosaur - OTP and magic-link retrieval.
  - SDK/Client: `mailosaur` SDK in `src/mobile_crawler/infrastructure/mailosaur/service.py`
  - Auth: `mailosaur_api_key` + `mailosaur_server_id`

## Data Storage

**Databases:**
- SQLite (local files)
  - Connection: `crawler.db` managed by `src/mobile_crawler/infrastructure/database.py`
  - Client: stdlib `sqlite3`
- SQLite for settings/secrets
  - Connection: `user_config.db` managed by `src/mobile_crawler/infrastructure/user_config_store.py`
  - Client: stdlib `sqlite3` + `cryptography` for encrypted secrets

**File Storage:**
- Local filesystem only (session artifacts: screenshots, reports, PCAP, logs) managed by `src/mobile_crawler/infrastructure/session_folder_manager.py` and `src/mobile_crawler/domain/report_generator.py`.

**Caching:**
- SQLite table `omni_parser_cache` in `src/mobile_crawler/infrastructure/database.py`.
- In-memory model registry cache in `src/mobile_crawler/domain/providers/registry.py`.

## Authentication & Identity

**Auth Provider:**
- Custom API-key based integrations (no OAuth/SSO provider detected).
  - Implementation: encrypted secret storage in `user_config.db` (`src/mobile_crawler/infrastructure/user_config_store.py`) with optional environment fallback in `src/mobile_crawler/domain/droidrun_agent_service.py`.

## Monitoring & Observability

**Error Tracking:**
- None dedicated (no Sentry/Datadog SDK detected).

**Logs:**
- Python logging + DB/file sinks in `src/mobile_crawler/core/log_sinks.py`.
- DroidRun JSONL trace logs written by `DroidRunLogHandler` in `src/mobile_crawler/domain/droidrun_agent_service.py`.

## CI/CD & Deployment

**Hosting:**
- Local desktop execution (CLI and PySide6 GUI via `run_cli.py`, `run_ui.py`).

**CI Pipeline:**
- Not detected in `.github/workflows/` (directory absent).
- Local quality automation via pre-commit in `.pre-commit-config.yaml`.

## Environment Configuration

**Required env vars:**
- Dynamic `CRAWLER_<KEY>` overrides for config values (`src/mobile_crawler/config/config_manager.py`).
- Provider fallbacks in `src/mobile_crawler/domain/droidrun_agent_service.py`: `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `REPLICATE_API_KEY`.
- Local service URLs are config keys (`mobsf_api_url`, `omniparser_local_url`, Ollama base URL in provider registry).

**Secrets location:**
- Encrypted secrets table in `user_config.db` (`src/mobile_crawler/infrastructure/user_config_store.py`).
- Optional `.mobsf_api_key` file produced by `scripts/start.ps1` and loaded by `src/mobile_crawler/ui/widgets/settings_panel.py`.

## Webhooks & Callbacks

**Incoming:**
- None detected (no webhook HTTP server/endpoints in `src/mobile_crawler/`).

**Outgoing:**
- HTTPS API calls to OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) from `src/mobile_crawler/domain/providers/openrouter_adapter.py`.
- HTTPS model-list fetch (`https://openrouter.ai/api/v1/models`) from `src/mobile_crawler/domain/providers/registry.py`.
- MobSF REST calls (`/api/v1/*`) from `src/mobile_crawler/infrastructure/mobsf_manager.py`.
- Local OmniParser calls (`/health`, `/parse`) from `src/mobile_crawler/domain/omni_parser_client.py`.

---

*Integration audit: 2026-05-01*
