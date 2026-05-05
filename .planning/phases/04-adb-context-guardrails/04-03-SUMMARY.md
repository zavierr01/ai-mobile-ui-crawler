---
phase: 04-adb-context-guardrails
plan: 03
subsystem: adb-context
tags: [adb, am-start, app-switch-recovery, launcher-resolution, context-guard]

# Dependency graph
requires:
  - phase: 04-adb-context-guardrails
    provides: DeviceContextCapture, UIDumpValidator, StepSkipReason, context pre-check in step execution
provides:
  - AppSwitchRecovery class with detect-and-recover loop
  - RecoveryAttempt dataclass for tracking recovery attempts
  - resolve_launcher_activity() method with caching on ADBActionExecutor
  - am_start_recovery() method using adb shell am start
  - Recovery logic wired into _handle_tool_execution_event for app-switch detection
  - FatalError raised on 3 consecutive recovery failures
affects: [adb-context-guardrails, step-state-machine-and-ui-sync]

# Tech tracking
tech-stack:
  added: []
  patterns: [am-start-recovery for app relaunch, launcher-activity-resolution with caching, consecutive-failure-abort pattern]

key-files:
  created: []
  modified:
    - src/mobile_crawler/domain/context_guard.py
    - src/mobile_crawler/domain/adb_action_executor.py
    - src/mobile_crawler/domain/droidrun_agent_service.py

key-decisions:
  - "Primary recovery uses am start -n with resolved launcher activity (D-05), monkey is only fallback"
  - "Launcher activity cached per package to avoid repeated ADB resolution calls"
  - "AppSwitchRecovery.detect_and_recover() performs up to 3 retry loops internally, resetting on success"
  - "On 3 consecutive failures, FatalError aborts the entire run per D-06"
  - "Post-recovery context capture provides fresh DeviceContext before continuing the step"

patterns-established:
  - "Recovery loop: detect mismatch → attempt recovery → verify → continue or abort"
  - "Launcher resolution: resolve-activity primary, dumpsys fallback, cached per package"
  - "Consecutive failure limit: abort after 3 failures to prevent infinite loops"

requirements-completed:
  - CTX-03

# Metrics
duration: 2min
completed: 2026-05-05
---

# Phase 4 Plan 3: ADB Context Guardrails Summary

**App-switch detection and automatic recovery using am start with launcher activity resolution, aborting after 3 consecutive failures per D-06**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-05T21:37:38Z
- **Completed:** 2026-05-05T21:39:53Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added resolve_launcher_activity() with two-tier resolution (resolve-activity primary, dumpsys fallback) and per-package caching
- Added am_start_recovery() method using `adb shell am start -n` with launcher activity per D-05, monkey as fallback
- Created AppSwitchRecovery class with detect_and_recover() loop that retries up to 3 times per D-06
- Created RecoveryAttempt dataclass for tracking individual recovery attempts
- Wired app-switch recovery into _handle_tool_execution_event — on TARGET_APP_MISMATCH, attempts recovery before skipping
- On successful recovery, fresh context is captured and step continues normally
- On 3 consecutive failures, raises FatalError to abort the run per D-06

## Task Commits

Each task was committed atomically:

1. **Task 1: Add am start recovery and launcher resolution to ADBActionExecutor** - `20249b9` (feat)
2. **Task 2: Create AppSwitchRecovery and wire detection/recovery loop into step execution** - `97f4a13` (feat)

## Files Created/Modified
- `src/mobile_crawler/domain/adb_action_executor.py` - Added resolve_launcher_activity() with caching, am_start_recovery() with am start -n
- `src/mobile_crawler/domain/context_guard.py` - Added RecoveryAttempt dataclass, AppSwitchRecovery class with detect_and_recover()
- `src/mobile_crawler/domain/droidrun_agent_service.py` - Wired AppSwitchRecovery into _wire_observers_to_agent and _handle_tool_execution_event

## Decisions Made
- Primary recovery uses `am start -n` with resolved launcher activity per D-05 — monkey is only a fallback when resolution fails
- Launcher activity resolution cached per package in `_launcher_activity_cache` dictionary to avoid repeated ADB calls
- AppSwitchRecovery performs all 3 retry attempts internally in detect_and_recover(), resetting consecutive failure counter on success
- On 3 consecutive failures, FatalError is raised to abort the run entirely per D-06 — no silent continuation
- Post-recovery context re-capture provides fresh DeviceContext before the step proceeds

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- App-switch detection and recovery complete, CTX-03 requirement met
- All three plans in Phase 04 complete (context capture, UI dump validation, app-switch recovery)
- Phase 04 (ADB Context Guardrails) fully implemented, ready for Phase 05 (Test Coverage & Reliability)

## Self-Check: PASSED

- All 3 modified files verified on disk
- Both plan commits found in git log: `20249b9` and `97f4a13`
- SUMMARY.md created at `.planning/phases/04-adb-context-guardrails/04-03-SUMMARY.md`
- All 7 verification criteria from plan passed
- All 6 success criteria met

---
*Phase: 04-adb-context-guardrails*
*Completed: 2026-05-05*