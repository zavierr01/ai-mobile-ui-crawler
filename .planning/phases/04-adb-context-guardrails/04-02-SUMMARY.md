---
phase: 04-adb-context-guardrails
plan: 02
subsystem: adb-context
tags: [ui-dump-validation, context-precheck, skip-reason, step-phase, guardrails]

# Dependency graph
requires:
  - phase: 04-adb-context-guardrails
    provides: DeviceContext dataclass, DeviceContextCapture, ADB package/activity extraction, step_phase_transitions with context columns
provides:
  - UIDumpValidator class with validate() and validate_ui_dump_with_retry()
  - UIDumpValidationResult dataclass with is_valid, is_parseable, element_count, error
  - StepSkipReason enum (TARGET_APP_MISMATCH, INVALID_UI_DUMP)
  - Context pre-check gate in _handle_tool_execution_event before DECIDE
  - UI dump validation gate in _handle_tool_execution_event before DECIDE
  - Skip path (CAPTURE -> CHECKPOINT) in StepPhaseStateMachine
affects: [adb-context-guardrails, step-state-machine-and-ui-sync]

# Tech tracking
tech-stack:
  added: [xml.etree.ElementTree for UI dump parsing]
  patterns: [validation-gate before decision layer, skip-path in step phase machine]

key-files:
  created: []
  modified:
    - src/mobile_crawler/domain/context_guard.py
    - src/mobile_crawler/domain/droidrun_agent_service.py
    - src/mobile_crawler/domain/step_phase.py

key-decisions:
  - "Used CAPTURE->CHECKPOINT direct skip path rather than CAPTURE->RECORD->CHECKPOINT to truly bypass DECIDE/EXECUTE"
  - "UIDumpValidator validates a11y_tree from DroidRun's state_provider when available, falls back gracefully when not"
  - "StepSkipReason persisted as JSON metadata on skipped transition for observability"

patterns-established:
  - "Validation gate pattern: validate data before it reaches AI decision layer, skip step on failure"
  - "Skip path in state machine: CAPTURE -> CHECKPOINT bypasses DECIDE/EXECUTE/RECORD with skip_reason metadata"

requirements-completed:
  - CTX-02

# Metrics
duration: 4min
completed: 2026-05-05
---

# Phase 4 Plan 2: ADB Context Guardrails Summary

**UI dump validation gate and context pre-check wired into DroidRun step execution, skipping invalid steps instead of aborting the run**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-05T21:32:35Z
- **Completed:** 2026-05-05T21:36:14Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- UIDumpValidator validates UI dumps as parseable (XML or iterable) and non-empty before the decision layer per D-03
- validate_ui_dump_with_retry retries once on transient failures per D-04 before marking step as skipped
- Context pre-check at CAPTURE phase compares current package against target app per D-02
- Package mismatch skips DECIDE/EXECUTE, transitioning directly CAPTURE -> CHECKPOINT with skip metadata
- Invalid UI dumps also skip DECIDE/EXECUTE with INVALID_UI_DUMP skip reason persisted
- StepPhaseStateMachine updated with CAPTURE -> CHECKPOINT skip transition for guardrail bypass path

## Task Commits

Each task was committed atomically:

1. **Task 1: Create UIDumpValidator with parseable and non-empty checks** - `05cf39e` (feat)
2. **Task 2: Wire validation gate and context pre-check into DroidRun step execution** - `406886d` (feat)

## Files Created/Modified
- `src/mobile_crawler/domain/context_guard.py` - Added UIDumpValidator, UIDumpValidationResult, StepSkipReason (appended to existing DeviceContext module)
- `src/mobile_crawler/domain/droidrun_agent_service.py` - Added context pre-check and UI dump validation gates in _handle_tool_execution_event; initialized DeviceContextCapture and UIDumpValidator; set _target_package from app_package
- `src/mobile_crawler/domain/step_phase.py` - Added CAPTURE -> CHECKPOINT valid transition for skip path

## Decisions Made
- Used CAPTURE -> CHECKPOINT direct skip path rather than intermediate phases, so DECIDE/EXECUTE/RECORD are truly bypassed — this required adding the transition to VALID_TRANSITIONS
- UIDumpValidator validates a11y_tree from DroidRun's state_provider when available; if state_provider is unavailable (some execution paths), validation is skipped gracefully rather than blocking
- StepSkipReason values persisted as JSON metadata on the skip transition, enabling downstream analysis of why steps were skipped

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added CAPTURE -> CHECKPOINT skip transition to StepPhaseStateMachine**
- **Found during:** Task 2 (context pre-check and validation gate wiring)
- **Issue:** Plan's skip path requires CAPTURE -> CHECKPOINT direct transition, but the existing state machine only allowed CAPTURE -> DECIDE. Without this transition, the skip path would throw ValueError at runtime.
- **Fix:** Added `StepPhase.CHECKPOINT` to `VALID_TRANSITIONS[StepPhase.CAPTURE]` so the skip path works correctly.
- **Files modified:** src/mobile_crawler/domain/step_phase.py
- **Verification:** StepPhaseStateMachine tests (13 passed) plus manual verification that both CAPTURE -> DECIDE and CAPTURE -> CHECKPOINT transitions work
- **Committed in:** 406886d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Essential for correctness — skip path would fail at runtime without this transition. No scope creep.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- UI dump validation gate complete, ready for Plan 03 (app-switch recovery)
- StepSkipReason enum shared between Plans 02 and 03 for consistent skip tracking
- _current_device_context stored on service for downstream recovery decisions
- All skip reasons persisted in step_phase_transitions metadata for observability

## Self-Check: PASSED

- All 3 modified files verified on disk
- Both plan commits found in git log: `05cf39e` and `406886d`
- SUMMARY.md created at `.planning/phases/04-adb-context-guardrails/04-02-SUMMARY.md`
- All 6 verification criteria from plan passed
- All 4 success criteria met
- All 13 existing step_phase tests still pass

---
*Phase: 04-adb-context-guardrails*
*Completed: 2026-05-05*