---
phase: 03-step-state-machine-ui-sync
reviewed: 2026-05-05T12:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - src/mobile_crawler/config/defaults.py
  - src/mobile_crawler/core/crawler_event_listener.py
  - src/mobile_crawler/core/crawler_loop.py
  - src/mobile_crawler/domain/action_verifier.py
  - src/mobile_crawler/domain/droidrun_agent_service.py
  - src/mobile_crawler/domain/step_phase.py
  - src/mobile_crawler/domain/step_phase_models.py
  - src/mobile_crawler/domain/ui_wait_predicate.py
  - src/mobile_crawler/infrastructure/database.py
  - src/mobile_crawler/infrastructure/step_phase_repository.py
  - tests/domain/test_action_verifier.py
  - tests/domain/test_step_phase.py
  - tests/domain/test_ui_wait_predicate.py
  - tests/infrastructure/test_step_phase_repository.py
findings:
  critical: 3
  warning: 6
  info: 4
  total: 13
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-05T12:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Reviewed 14 source files implementing the step phase state machine, UI synchronization predicates, action verification, and their integration into the DroidRun agent service. The domain models and state machine (`step_phase.py`, `step_phase_models.py`) are clean and well-tested. However, the infrastructure layer has **connection leak bugs** in the repository, the `ActionVerifier` uses non-deterministic hashing, and the `DroidRunAgentService` has a module-level logger manipulation side effect and an orphaned database connection. Three critical bugs were found that will cause incorrect runtime behavior.

## Critical Issues

### CR-01: SQLite connection leaks in StepPhaseRepository

**File:** `src/mobile_crawler/infrastructure/step_phase_repository.py:77,103,126,153,274`
**Severity:** BLOCKER

Five methods (`get_current_phase`, `get_transitions_for_step`, `get_transitions_for_run`, `get_step_phase_summary`, `get_latest_step_for_run`) call `self.db_manager.get_connection()` and assign the connection to a local variable but never close it. Only `record_transition` and `update_step_current_phase` correctly use `with closing(...)` to ensure cleanup. Each unclosed call holds an open SQLite file handle. Under sustained crawl activity (hundreds of steps per run), this leaks connections until the process exhausts file descriptors or SQLite returns `SQLITE_BUSY`.

The `get_step_phase_summary` method at line 153 is particularly severe because it also calls `get_current_phase` internally (line 168), leaking **two** connections per invocation.

**Fix:**
```python
# Example fix for get_current_phase (line 77):
def get_current_phase(self, run_id: int, step_number: int) -> Optional[str]:
    with closing(self.db_manager.get_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT to_phase FROM step_phase_transitions
            WHERE run_id = ? AND step_number = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """,
            (run_id, step_number),
        )
        row = cursor.fetchone()
        return row[0] if row else None
```

Apply the same `with closing(...)` pattern to all five methods.

### CR-02: Non-deterministic hash() causes ActionVerifier to produce false negatives

**File:** `src/mobile_crawler/domain/action_verifier.py:80`
**Severity:** BLOCKER

Line 80 uses Python's built-in `hash(formatted_text)` to fingerprint UI state. Python's `hash()` is randomized per process via `PYTHONHASHSEED` (enabled by default since Python 3.3). While this is fine within a single session, the `verify()` method calls `capture_pre_state()` again at line 110 to get `post_state`, which also uses `hash()`. Since both calls are in the same process, they will produce the same hash for the same string. **However**, the real problem is that `hash()` can produce collisions: different strings may produce the same hash, causing `ActionVerifier` to report `ui_changed=False` when the UI actually changed. For a verification component whose purpose is detecting state changes, using an uncontrolled hash function undermines its correctness.

A more correct approach is to compare the raw strings directly, or use a deterministic hash like SHA-256 if the text is very large.

**Fix:**
```python
# In capture_pre_state, store the raw text instead of hash:
return {
    "package": current_app or "",
    "ui_text": formatted_text,  # Store raw text for direct comparison
    "element_count": len(elements) if elements else 0,
}

# In verify, compare raw text:
ui_changed = pre_state.get("ui_text") != post_state.get("ui_text")
```

### CR-03: Orphaned database connection in _initialize_omni_parser

**File:** `src/mobile_crawler/domain/droidrun_agent_service.py:319-321`
**Severity:** BLOCKER

`_initialize_omni_parser` creates a new `DatabaseManager()` and calls `get_connection()`, assigning the connection to `self._ui_context_manager`. This connection is never closed. When `cleanup()` runs later, it nulls out agent attributes but never closes `self._ui_context_manager`'s database connection. This leaks a SQLite connection for the lifetime of the service, and the `DatabaseManager` itself is local to the method and discarded, so its `close()` method can never be called.

**Fix:**
Store the `DatabaseManager` instance and close it in `cleanup()`, or use the same `DatabaseManager` pattern used in `begin_step_tracking` (where it is also not stored, but at least the connection is managed by the repository's `closing()` pattern).

```python
def _initialize_omni_parser(self) -> None:
    try:
        self._omni_parser_client = OmniParserClient(self.config_manager)
        self._omni_db_manager = DatabaseManager()
        db_conn = self._omni_db_manager.get_connection()
        self._ui_context_manager = UIContextManager(db_conn, self._omni_parser_client)
    except Exception as e:
        logger.warning(f"Failed to initialize OmniParser: {e}")
        self._omni_parser_client = None
        self._ui_context_manager = None

async def cleanup(self) -> None:
    # ... existing cleanup ...
    if hasattr(self, '_omni_db_manager') and self._omni_db_manager:
        self._omni_db_manager.close()
        self._omni_db_manager = None
```

## Warnings

### WR-01: CancelledErrorFilter over-broad message pattern suppresses legitimate errors

**File:** `src/mobile_crawler/domain/droidrun_agent_service.py:44`
**Severity:** WARNING

The filter condition `"CancelledError" in msg and "task" in msg.lower()` will suppress any ERROR-level log that contains both "CancelledError" and "task" (case-insensitive). This could suppress genuine errors from unrelated libraries that happen to include both words. For example, a message like "CancelledError in background task pool" from a library error unrelated to graceful cancellation would be silently dropped.

**Fix:** Narrow the pattern to match specific known message formats, or check `record.exc_info` more thoroughly instead of relying on message text matching.

### WR-02: Module-level side effects on root logger at import time

**File:** `src/mobile_crawler/domain/droidrun_agent_service.py:51-57`
**Severity:** WARNING

Lines 51-57 install a `CancelledErrorFilter` on the root logger and three library loggers at module import time. This is a side effect of importing the module. Any code that imports `DroidRunAgentService` (even for type checking or testing) will have its root logger silently modified. This can interfere with other modules' logging behavior and makes testing difficult (the filter persists across test modules).

**Fix:** Move the filter installation into an initialization method (e.g., `__init__` or a classmethod `_setup_logging()`) so it only runs when the service is actually used, not on import.

### WR-03: State machine desynchronization on transition failure

**File:** `src/mobile_crawler/domain/droidrun_agent_service.py:456-525`
**Severity:** WARNING

In `_handle_tool_execution_event`, `_current_step_number` is incremented at line 457 before the phase transitions begin at line 466. If a `ValueError` is raised (invalid transition at line 518), the exception handler logs a warning and returns. However, `_current_step_number` has already been incremented, and the state machine is stuck in an intermediate phase (e.g., `EXECUTE` or `RECORD`). The next tool event will try `CAPTURE -> DECIDE` from whatever intermediate state the machine is in, causing another `ValueError`, and so on. Once the machine desynchronizes, all subsequent events will fail silently.

**Fix:** Either (a) roll back `_current_step_number` on failure, or (b) reset the state machine to `CAPTURE` in the exception handler, or (c) increment `_current_step_number` only after successful completion of the full cycle.

### WR-04: Private protocol method _get_current_app

**File:** `src/mobile_crawler/domain/action_verifier.py:26,74`
**Severity:** WARNING

The `Driver` protocol at line 26 declares `_get_current_app` with a leading underscore (private by convention), and `ActionVerifier` calls it at line 74. Using a private method name in a public Protocol interface is a code smell -- callers must implement a method with a private-looking name, and linters may warn about accessing private members. The underscore prefix signals "internal implementation detail" but this is part of a public contract.

**Fix:** Rename to `get_current_app` (without underscore) in both the Protocol and the call site.

### WR-05: scroll_up and scroll_down wait profiles missing from defaults.py config keys

**File:** `src/mobile_crawler/config/defaults.py` and `src/mobile_crawler/domain/ui_wait_predicate.py:44-45`
**Severity:** WARNING

`DEFAULT_WAIT_PROFILES` in `ui_wait_predicate.py` defines entries for `scroll_up` and `scroll_down` (lines 44-45), but `defaults.py` does not include corresponding `wait_scroll_up_*` or `wait_scroll_down_*` keys. If a user configures `wait_scroll_up_timeout_ms` in their settings, `AdaptiveWaitConfig._load_profile` will call `config_manager.get("wait_scroll_up_timeout_ms", default.timeout_ms)`. Since the key does not exist in DEFAULTS, the config manager may return the default or raise, depending on its implementation. This is an inconsistency between the wait profiles and the config defaults.

**Fix:** Add `wait_scroll_up_timeout_ms`, `wait_scroll_up_poll_interval_ms`, `wait_scroll_down_timeout_ms`, and `wait_scroll_down_poll_interval_ms` to `defaults.py`.

### WR-06: request_cancel lambda captures handler by late-binding reference

**File:** `src/mobile_crawler/domain/droidrun_agent_service.py:1073`
**Severity:** WARNING

In `request_cancel`, the lambda `lambda: asyncio.create_task(handler.cancel_run())` captures `handler` (a local variable assigned at line 1067 from `self._current_handler`). This is correct as-written because `handler` is bound to a local at line 1067. However, the method is called from another thread (the main thread) while the async loop thread may be modifying `self._current_handler`. There is a TOCTOU race: by the time the lambda executes on the event loop, `self._current_handler` may have been set to `None` by `_shutdown_active_workflow`. The local `handler` capture prevents a `NoneType` error, but the cancellation may target a handler that has already been cleaned up.

**Fix:** Add a `if not handler.done()` check inside the lambda, or use `call_soon_threadsafe` with a proper callback function that validates the handler state.

## Info

### IN-01: Duplicated StateProvider protocol definition

**File:** `src/mobile_crawler/domain/action_verifier.py:19-21` and `src/mobile_crawler/domain/ui_wait_predicate.py:15-18`
**Severity:** INFO

The `StateProvider` Protocol is defined independently in both `action_verifier.py` and `ui_wait_predicate.py` with identical signatures. This duplication means changes to one must be mirrored in the other.

**Fix:** Extract the `StateProvider` protocol to a shared module (e.g., `domain/protocols.py`) and import it in both files.

### IN-02: DatabaseManager created but never stored in begin_step_tracking

**File:** `src/mobile_crawler/domain/droidrun_agent_service.py:351-353`
**Severity:** INFO

`begin_step_tracking` creates a `DatabaseManager()` and passes it to `StepPhaseRepository`, but does not store the `DatabaseManager` reference. The repository opens connections via `db_manager.get_connection()` on each call, which is fine for SQLite. However, the `DatabaseManager`'s `close()` method can never be called since it is not stored. This is a minor leak concern (the SQLite connections in the repository should use `closing()` as noted in CR-01).

### IN-03: Launch_app retry loop missing scroll_up/scroll_down profile config

**File:** `src/mobile_crawler/config/defaults.py`
**Severity:** INFO

The defaults file includes `wait_launch_app_timeout_ms` / `poll_interval_ms` but the `DEFAULT_WAIT_PROFILES` in `ui_wait_predicate.py` uses key `"launch_app"` which is the same. However `defaults.py` does not have `wait_launch_app_*` keys, so the config lookup for launch_app will never find user overrides. This is a minor inconsistency similar to WR-05.

### IN-04: Commented-out code comment in defaults.py

**File:** `src/mobile_crawler/config/defaults.py:62`
**Severity:** INFO

Line 62 contains `# Test credentials` as a section header with no entries below it. This is a remnant from removed configuration or a placeholder. It adds noise to the config file.

---

_Reviewed: 2026-05-05T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
