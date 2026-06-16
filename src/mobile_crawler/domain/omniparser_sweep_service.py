"""Deterministic OmniParser sweep crawl mode.

Instead of an LLM agent deciding what to tap each step, this service runs
OmniParser once per screen to detect all UI element bounding boxes, then
mechanically taps each box in turn, captures the result, and either returns
(breadth) or recurses (depth) into newly discovered screens.

LLM calls are reserved for a handful of judgment tasks:
- noise filtering + grouping of detected boxes (one call per screen)
- outcome classification when a heuristic pixel-diff is ambiguous
- sub-element edge-probe redraw decisions when ambiguous
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple

from PIL import Image, ImageChops, ImageDraw

from mobile_crawler.config.config_manager import ConfigManager
from mobile_crawler.domain.adb_action_executor import ADBActionExecutor
from mobile_crawler.domain.droidrun_agent_service import DroidRunResult
from mobile_crawler.domain.omni_parser_client import OmniParserClient
from mobile_crawler.infrastructure.database import DatabaseManager
from mobile_crawler.infrastructure.element_group_repository import ElementGroup, ElementGroupRepository
from mobile_crawler.infrastructure.step_log_repository import StepLog, StepLogRepository

logger = logging.getLogger(__name__)

# Pixel-diff thresholds (fraction of pixels that differ) used to classify
# tap outcomes without an LLM call.
_DIFF_NAVIGATED_THRESHOLD = 0.35   # above this -> almost certainly a new screen
_DIFF_NO_CHANGE_THRESHOLD = 0.01   # below this -> almost certainly nothing happened

# Bound on extra boxes discovered via edge-probing per screen, to keep the
# sweep from growing unboundedly.

_SETTLE_DELAY_SECONDS = 1.0


@dataclass
class _Group:
    """In-memory representation of a tappable element group for one screen."""
    db_id: int
    bbox: Tuple[int, int, int, int]  # pixel coords (left, top, right, bottom)
    label: str
    member_bboxes: List[Tuple[int, int, int, int]]
    is_carousel: bool = False


@dataclass
class _FrontierEntry:
    """A screen to sweep, identified by its signature once visited."""
    depth: int


class OmniParserSweepService:
    """Lifecycle-compatible alternative to DroidRunAgentService.

    Provides the same lifecycle methods (`begin_step_tracking`,
    `configure_run_logging`, `execute_exploration_task`, `request_cancel`,
    `cleanup`) so `CrawlerLoop` can use either service interchangeably.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        ai_interaction_repository: Any,
        device_id: str,
    ):
        self.config_manager = config_manager
        self.device_id = device_id

        self._adb = ADBActionExecutor(device_id=device_id)
        self._omni_parser_client = OmniParserClient(config_manager)

        self._current_run_id: Optional[int] = None
        self._current_step_number: int = 0
        self._emit_step_phase_event = None
        self._screenshots_dir: Optional[str] = None
        self._db_manager = None
        self._step_log_repository: Optional[StepLogRepository] = None
        self._element_group_repository: Optional[ElementGroupRepository] = None

        self._cancel_requested = False
        self._app_package: str = ""
        self._visited_signatures: Set[str] = set()
        self._noise_filter_cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def begin_step_tracking(
        self,
        run_id: int,
        emit_step_phase_event=None,
        screenshots_dir: Optional[str] = None,
    ) -> None:
        """Initialize per-run tracking state."""
        self._current_run_id = run_id
        self._current_step_number = 0
        self._emit_step_phase_event = emit_step_phase_event
        self._screenshots_dir = screenshots_dir

        db_manager = DatabaseManager()
        self._db_manager = db_manager
        self._step_log_repository = StepLogRepository(db_manager)
        self._element_group_repository = ElementGroupRepository(db_manager)

    def configure_run_logging(self, run_id, log_dir, emit_debug, enable_ui) -> None:
        """Configure logging for this run (no-op beyond storing the callback)."""
        self._current_run_id = run_id
        self._emit_step_phase_event = emit_debug

    def request_cancel(self) -> bool:
        """Request cancellation of the current sweep."""
        self._cancel_requested = True
        return True

    def cleanup(self) -> None:
        """Release any resources held by this service."""
        pass

    def clear_run_logging(self) -> None:
        """Clear per-run logging state (mirrors DroidRunAgentService)."""
        self._emit_step_phase_event = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def execute_exploration_task(
        self,
        run_id: int,
        app_package: str,
        max_steps: int = 100,
        exploration_objective: Optional[str] = None,
        max_duration_seconds: Optional[float] = None,
    ) -> DroidRunResult:
        """Run the deterministic OmniParser sweep.

        `max_steps` counts element taps (not LLM calls).
        """
        self._cancel_requested = False
        self._app_package = app_package
        start_time = time.time()

        sweep_mode = self.config_manager.get("omni_sweep_mode", "breadth")

        successful_actions = 0
        failed_actions = 0
        total_actions = 0
        steps_completed = 0
        completion_reason = "max_steps_reached"

        try:
            steps_completed, successful_actions, failed_actions, total_actions, completion_reason = (
                await self._sweep_screen(
                    depth=0,
                    sweep_mode=sweep_mode,
                    max_steps=max_steps,
                    max_duration_seconds=max_duration_seconds,
                    start_time=start_time,
                    steps_completed=0,
                    successful_actions=0,
                    failed_actions=0,
                    total_actions=0,
                )
            )
            success = True
            error_message = None
        except Exception as e:
            logger.exception("OmniParser sweep failed")
            success = False
            error_message = str(e)
            completion_reason = "error"

        total_duration_ms = (time.time() - start_time) * 1000

        final_state = {
            "successful_actions": successful_actions,
            "failed_actions": failed_actions,
            "total_actions": total_actions,
            "completion_reason": completion_reason if not self._cancel_requested else "cancelled",
        }

        return DroidRunResult(
            success=success,
            steps_completed=steps_completed,
            actions_taken=[],
            final_state=final_state,
            error_message=error_message,
            total_duration_ms=total_duration_ms,
        )

    # ------------------------------------------------------------------
    # Core sweep algorithm
    # ------------------------------------------------------------------

    async def _sweep_screen(
        self,
        depth: int,
        sweep_mode: str,
        max_steps: int,
        max_duration_seconds: Optional[float],
        start_time: float,
        steps_completed: int,
        successful_actions: int,
        failed_actions: int,
        total_actions: int,
    ) -> Tuple[int, int, int, int, str]:
        """Sweep all element groups on the current screen.

        Returns (steps_completed, successful_actions, failed_actions, total_actions, completion_reason).
        """
        if self._cancel_requested:
            return steps_completed, successful_actions, failed_actions, total_actions, "cancelled"
        if steps_completed >= max_steps:
            return steps_completed, successful_actions, failed_actions, total_actions, "max_steps_reached"
        if max_duration_seconds is not None and (time.time() - start_time) >= max_duration_seconds:
            return steps_completed, successful_actions, failed_actions, total_actions, "max_duration_reached"

        screen_bytes = self._take_screenshot_bytes()
        if screen_bytes is None:
            return steps_completed, successful_actions, failed_actions, total_actions, "screenshot_failed"

        signature = self._compute_screen_signature(screen_bytes)
        screen_w, screen_h = self._adb._get_screen_size()

        signature, groups = self._get_or_create_groups(signature, screen_bytes, screen_w, screen_h)

        # Raw boxes overview saved inside _get_or_create_groups on first visit.

        self._visited_signatures.add(signature)

        # Track which groups navigated to which destination for post-hoc merging.
        destination_map: Dict[int, str] = {}

        for group in groups:
            if self._cancel_requested:
                return steps_completed, successful_actions, failed_actions, total_actions, "cancelled"
            if steps_completed >= max_steps:
                return steps_completed, successful_actions, failed_actions, total_actions, "max_steps_reached"
            if max_duration_seconds is not None and (time.time() - start_time) >= max_duration_seconds:
                return steps_completed, successful_actions, failed_actions, total_actions, "max_duration_reached"

            existing = self._get_group_status(signature, group)
            if existing in ("noise", "dead"):
                continue

            self._current_step_number += 1
            steps_completed += 1
            total_actions += 1

            pre_bytes = self._take_screenshot_bytes()
            if pre_bytes is None:
                failed_actions += 1
                continue

            action_result = self._adb.click(group.bbox)
            time.sleep(_SETTLE_DELAY_SECONDS)

            post_bytes = self._take_screenshot_bytes()
            if post_bytes is None:
                failed_actions += 1
                continue

            # Take a second idle screenshot to measure background animation noise.
            time.sleep(0.5)
            idle_bytes = self._take_screenshot_bytes()

            outcome, reason = self._classify_outcome(pre_bytes, post_bytes, idle_bytes)

            # Save pre-tap screenshot annotated with the bbox that was tapped (source page).
            tap_screenshot_path = self._save_step_screenshot(
                pre_bytes, group.bbox, f"tap_{self._current_step_number:04d}_before"
            )
            # Save post-tap screenshot (result page, no annotation).
            self._save_step_screenshot(
                post_bytes, None, f"tap_{self._current_step_number:04d}_after"
            )

            if action_result.success:
                successful_actions += 1
            else:
                failed_actions += 1

            self._record_step_log(
                action_type="tap_element",
                bbox=group.bbox,
                screenshot_path=tap_screenshot_path,
                success=action_result.success,
                reasoning=reason,
                description=f"Tap element group '{group.label}' -> {outcome}",
            )

            if outcome == "navigated":
                self._update_group_status(signature, group, "navigated", reason)
                to_sig = self._compute_screen_signature(post_bytes)
                destination_map[group.db_id] = to_sig
                arrival_path = self._save_arrival_screenshot(post_bytes, to_sig)
                self._record_navigation_edge(signature, to_sig, group.label, arrival_path, group.bbox)
                self._emit_debug_log(
                    f"Navigation edge: {signature} -> {to_sig} via '{group.label}'"
                )
                self._return_to_base(signature)
                time.sleep(_SETTLE_DELAY_SECONDS)

                # Probe other sample points within this bbox to detect multiple elements.
                steps_completed, successful_actions, failed_actions, total_actions = (
                    self._probe_bbox_subregions(
                        group=group,
                        base_signature=signature,
                        known_to_sig=to_sig,
                        steps_completed=steps_completed,
                        successful_actions=successful_actions,
                        failed_actions=failed_actions,
                        total_actions=total_actions,
                        destination_map=destination_map,
                    )
                )

                if sweep_mode == "depth":
                    (
                        steps_completed,
                        successful_actions,
                        failed_actions,
                        total_actions,
                        sub_reason,
                    ) = await self._sweep_screen(
                        depth=depth + 1,
                        sweep_mode=sweep_mode,
                        max_steps=max_steps,
                        max_duration_seconds=max_duration_seconds,
                        start_time=start_time,
                        steps_completed=steps_completed,
                        successful_actions=successful_actions,
                        failed_actions=failed_actions,
                        total_actions=total_actions,
                    )
                    if sub_reason in ("cancelled", "max_steps_reached", "max_duration_reached"):
                        self._return_to_base(signature)
                        return steps_completed, successful_actions, failed_actions, total_actions, sub_reason

            elif outcome == "in_place_change":
                self._update_group_status(signature, group, "in_place", reason)
                self._handle_in_place_change(
                    signature, group, pre_bytes, post_bytes, screen_w, screen_h
                )

            else:  # no_change
                self._update_group_status(signature, group, "noise", reason)

        # After sweeping all groups, regroup by destination and save merged screenshot.
        self._regroup_by_destination(signature, screen_bytes, destination_map)

        return steps_completed, successful_actions, failed_actions, total_actions, "screen_complete"

    # ------------------------------------------------------------------
    # OmniParser + grouping
    # ------------------------------------------------------------------

    def _get_or_create_groups(
        self,
        signature: str,
        screen_bytes: bytes,
        screen_w: int,
        screen_h: int,
    ) -> tuple:
        """Return (signature, groups) for this screen.

        On revisit: returns cached groups from DB.
        On first visit: runs OmniParser, creates groups, saves overview screenshot.
        """
        existing = self._element_group_repository.get_by_screen(self._current_run_id, signature)
        if existing:
            groups_from_db = [
                _Group(
                    db_id=eg.id,
                    bbox=tuple(json.loads(eg.bbox_json)["top_left"] + json.loads(eg.bbox_json)["bottom_right"]),
                    label=eg.label or "",
                    member_bboxes=json.loads(eg.member_bboxes_json) if eg.member_bboxes_json else [],
                )
                for eg in existing
            ]
            groups_from_db.sort(key=lambda g: (g.bbox[1], g.bbox[0]))
            return signature, groups_from_db

        elements = self._omni_parser_client.parse(screen_bytes)
        boxes = self._denormalize_elements(elements, screen_w, screen_h)
        boxes = self._expand_sub_elements(boxes, screen_bytes, screen_w, screen_h)
        carousels = [b for b in boxes if b.get("is_carousel")]
        self._emit_debug_log(
            f"OmniParser detected {len(boxes)} element(s) on screen {signature}"
            + (f" — {len(carousels)} carousel(s) detected (pink)" if carousels else "")
            + f": {[b['content'] or str(b['bbox']) for b in boxes]}"
        )
        if not boxes:
            return signature, []

        # Sort top-to-bottom, left-to-right by top-left corner of each bbox.
        boxes.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        groups: List[_Group] = []
        for box in boxes:
            bbox = box["bbox"]
            label = box.get("content") or ""
            bbox_json = json.dumps({
                "top_left": [bbox[0], bbox[1]],
                "bottom_right": [bbox[2], bbox[3]],
            })
            group_id = self._element_group_repository.create(ElementGroup(
                id=None,
                run_id=self._current_run_id,
                screen_signature=signature,
                bbox_json=bbox_json,
                member_bboxes_json=json.dumps([list(bbox)]),
                label=label,
                status="pending",
            ))
            groups.append(_Group(
                db_id=group_id,
                bbox=bbox,
                label=label,
                member_bboxes=[bbox],
                is_carousel=box.get("is_carousel", False),
            ))

        # Save 'raw boxes' overview (before any destination-based merging).
        self._save_raw_boxes_screenshot(screen_bytes, groups, signature)

        return signature, groups

    def _regroup_by_destination(
        self,
        signature: str,
        screen_bytes: bytes,
        destination_map: Dict[int, str],
    ) -> None:
        """After tapping all groups on a screen, merge groups that navigated to
        the same destination signature and save a 'merged groups' screenshot.

        destination_map: {group.db_id -> to_signature} for each navigated group.
        Groups that didn't navigate are left as-is.
        """
        if not destination_map:
            return

        existing = self._element_group_repository.get_by_screen(self._current_run_id, signature)
        if not existing:
            return

        # Bucket groups by destination.
        dest_to_ids: Dict[str, List[int]] = {}
        for eg in existing:
            dest = destination_map.get(eg.id)
            if dest:
                dest_to_ids.setdefault(dest, []).append(eg.id)

        # For each destination with >1 group, merge their bboxes.
        merged_groups: List[_Group] = []
        absorbed_ids: set = set()
        for dest, ids in dest_to_ids.items():
            if len(ids) <= 1:
                continue
            members = [eg for eg in existing if eg.id in ids]
            all_bboxes = []
            for eg in members:
                d = json.loads(eg.bbox_json)
                tl, br = d["top_left"], d["bottom_right"]
                all_bboxes.append((tl[0], tl[1], br[0], br[1]))
            merged_bbox = (
                min(b[0] for b in all_bboxes),
                min(b[1] for b in all_bboxes),
                max(b[2] for b in all_bboxes),
                max(b[3] for b in all_bboxes),
            )
            label = " / ".join(eg.label or "" for eg in members).strip(" /")
            # Update all member groups to "noise" in DB and absorb into one.
            for eg in members:
                self._element_group_repository.update_status(
                    eg.id, "noise", f"merged into destination group -> {dest}"
                )
                absorbed_ids.add(eg.id)
            # Create a new merged group.
            bbox_json = json.dumps({
                "top_left": [merged_bbox[0], merged_bbox[1]],
                "bottom_right": [merged_bbox[2], merged_bbox[3]],
            })
            member_bboxes_json = json.dumps([list(b) for b in all_bboxes])
            new_id = self._element_group_repository.create(ElementGroup(
                id=None,
                run_id=self._current_run_id,
                screen_signature=signature,
                bbox_json=bbox_json,
                member_bboxes_json=member_bboxes_json,
                label=label,
                status="navigated",
                outcome_reason=f"merged {len(ids)} groups with same dest {dest}",
                last_step_number=self._current_step_number,
            ))
            merged_groups.append(_Group(
                db_id=new_id,
                bbox=merged_bbox,
                label=label,
                member_bboxes=list(all_bboxes),
            ))

        # Build final group list for the after-screenshot: merged + unabsorbed.
        all_groups_after: List[_Group] = list(merged_groups)
        for eg in existing:
            if eg.id not in absorbed_ids:
                d = json.loads(eg.bbox_json)
                tl, br = d["top_left"], d["bottom_right"]
                all_groups_after.append(_Group(
                    db_id=eg.id,
                    bbox=(tl[0], tl[1], br[0], br[1]),
                    label=eg.label or "",
                    member_bboxes=[],
                ))

        n_merged = len([d for d in dest_to_ids.values() if len(d) > 1])
        self._emit_debug_log(
            f"Destination regrouping on screen {signature}: "
            f"{n_merged} destination(s) had duplicate groups merged. "
            f"{len(all_groups_after)} effective group(s) remain."
        )
        self._save_merged_groups_screenshot(screen_bytes, all_groups_after, signature)

    def _denormalize_elements(
        self, elements: List[Dict[str, Any]], screen_w: int, screen_h: int
    ) -> List[Dict[str, Any]]:
        """Convert OmniParser's normalized [0-1] bboxes to pixel coordinates,
        keeping only interactive elements with a usable bbox."""
        top_bar_px = int(self.config_manager.get("top_bar_height", 0) or 0)
        boxes = []
        for idx, el in enumerate(elements):
            bbox = el.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
            px = (
                int(x1 * screen_w),
                int(y1 * screen_h),
                int(x2 * screen_w),
                int(y2 * screen_h),
            )
            if px[2] <= px[0] or px[3] <= px[1]:
                continue
            # Skip elements whose top edge falls within the excluded status bar region.
            if top_bar_px > 0 and px[1] < top_bar_px:
                continue
            boxes.append({
                "id": idx,
                "bbox": px,
                "content": el.get("content", ""),
                "interactivity": el.get("interactivity", True),
                "is_carousel": False,  # set later by _probe_bbox_subregions if multiple destinations found
            })
        return boxes

    def _expand_sub_elements(
        self,
        boxes: List[Dict[str, Any]],
        screen_bytes: bytes,
        screen_w: int,
        screen_h: int,
    ) -> List[Dict[str, Any]]:
        """Expand wide container boxes that have no detected children by re-parsing their crop.

        Two-pass approach:
        1. Drop boxes whose center is contained by another box (already have children detected).
        2. For wide boxes (>50% screen width) with no children found in pass 1, crop and
           re-run OmniParser — capped at 3 extra parses per screen to avoid timeouts.
        """
        if not boxes:
            return boxes

        def _contains_center(outer, inner) -> bool:
            ox1, oy1, ox2, oy2 = outer["bbox"]
            ix1, iy1, ix2, iy2 = inner["bbox"]
            cx = (ix1 + ix2) / 2
            cy = (iy1 + iy2) / 2
            return ox1 < cx < ox2 and oy1 < cy < oy2

        # Pass 1: drop boxes that already have children in the full-screen parse.
        has_children = [False] * len(boxes)
        for i, outer in enumerate(boxes):
            for j, inner in enumerate(boxes):
                if i != j and _contains_center(outer, inner):
                    has_children[i] = True
                    break

        result: List[Dict[str, Any]] = []
        try:
            full_image = Image.open(BytesIO(screen_bytes)).convert("RGB")
        except Exception:
            return boxes

        reparse_budget = 3  # max extra OmniParser calls per screen

        for i, box in enumerate(boxes):
            if has_children[i]:
                # Container with known children — skip it, children are already in list.
                self._emit_debug_log(f"Skipping container box {box['bbox']} (children already detected)")
                continue

            x1, y1, x2, y2 = box["bbox"]
            width = x2 - x1
            is_wide = width > screen_w * 0.50

            # Pass 2: re-parse crop for wide childless boxes.
            if is_wide and reparse_budget > 0:
                try:
                    crop = full_image.crop((x1, y1, x2, y2))
                    buf = BytesIO()
                    crop.save(buf, format="PNG")
                    reparse_budget -= 1
                    sub_elements = self._omni_parser_client.parse(buf.getvalue())
                    crop_w, crop_h = x2 - x1, y2 - y1
                    sub_boxes = self._denormalize_elements(sub_elements, crop_w, crop_h)
                    translated = [
                        {**sb, "bbox": (x1 + sb["bbox"][0], y1 + sb["bbox"][1],
                                        x1 + sb["bbox"][2], y1 + sb["bbox"][3])}
                        for sb in sub_boxes
                    ]
                    if translated:
                        self._emit_debug_log(
                            f"Crop re-parse: wide box {box['bbox']} → {len(translated)} sub-element(s)"
                        )
                        result.extend(translated)
                        continue
                except Exception as e:
                    self._emit_debug_log(f"Crop re-parse failed for {box['bbox']}: {e}")

            result.append(box)

        return result if result else boxes

    # ------------------------------------------------------------------
    # Outcome classification
    # ------------------------------------------------------------------

    def _classify_outcome(
        self,
        pre_bytes: bytes,
        post_bytes: bytes,
        idle_bytes: Optional[bytes] = None,
    ) -> Tuple[str, str]:
        """Classify a tap outcome purely via pixel-diff heuristic — no LLM calls.

        `idle_bytes` is an optional second screenshot taken shortly after
        `post_bytes` with no interaction. Pixels that change between post and
        idle are background animation; subtracting them from the tap-diff
        prevents animated elements from being misclassified as in_place_change.
        """
        try:
            pre_img = Image.open(BytesIO(pre_bytes)).convert("RGB")
            post_img = Image.open(BytesIO(post_bytes)).convert("RGB")
            if pre_img.size != post_img.size:
                post_img = post_img.resize(pre_img.size)

            diff = ImageChops.difference(pre_img, post_img)
            diff_data = list(diff.getdata())

            # Build a per-pixel animation mask from idle drift, if available.
            anim_mask: set = set()
            if idle_bytes is not None:
                try:
                    idle_img = Image.open(BytesIO(idle_bytes)).convert("RGB")
                    if idle_img.size != post_img.size:
                        idle_img = idle_img.resize(post_img.size)
                    idle_diff = ImageChops.difference(post_img, idle_img)
                    anim_mask = {i for i, px in enumerate(idle_diff.getdata()) if sum(px) > 20}
                except Exception:
                    pass

            diff_pixels = sum(
                1 for i, px in enumerate(diff_data)
                if sum(px) > 30 and i not in anim_mask
            )
            total_pixels = pre_img.width * pre_img.height
            diff_ratio = diff_pixels / total_pixels if total_pixels else 0.0
        except Exception as e:
            logger.warning(f"Pixel diff failed: {e}")
            return "in_place_change", f"pixel diff failed: {e}"

        noise_note = f" (anim_masked={len(anim_mask)})" if anim_mask else ""
        if diff_ratio < _DIFF_NO_CHANGE_THRESHOLD:
            return "no_change", f"diff_ratio={diff_ratio:.4f}{noise_note}"
        if diff_ratio > _DIFF_NAVIGATED_THRESHOLD:
            return "navigated", f"diff_ratio={diff_ratio:.4f}{noise_note}"
        return "in_place_change", f"diff_ratio={diff_ratio:.4f}{noise_note}"

    # ------------------------------------------------------------------
    # Sub-element edge probing
    # ------------------------------------------------------------------

    def _handle_in_place_change(
        self,
        signature: str,
        trigger_group: _Group,
        pre_bytes: bytes,
        post_bytes: bytes,
        screen_w: int,
        screen_h: int,
        depth: int = 0,
    ) -> None:
        """Handle a tap that caused an in-place change (popup, dropdown, accordion).

        Runs OmniParser on the post-tap screenshot, finds boxes that are new
        (not present in the original element set), and taps each one. If a new
        box navigates away, records the edge and returns to base. If it causes
        another in-place change, recurses up to depth 2. Dismisses any overlay
        at the end by pressing Back.
        """
        if depth >= 2 or self._cancel_requested:
            return

        # Parse original boxes so we can diff against them.
        orig_elements = self._omni_parser_client.parse(pre_bytes)
        orig_boxes = self._denormalize_elements(orig_elements, screen_w, screen_h)
        orig_centers = {((b["bbox"][0] + b["bbox"][2]) // 2, (b["bbox"][1] + b["bbox"][3]) // 2) for b in orig_boxes}

        # Parse new state after the trigger tap.
        new_elements = self._omni_parser_client.parse(post_bytes)
        new_boxes = self._denormalize_elements(new_elements, screen_w, screen_h)

        # Find boxes whose center doesn't overlap any original box.
        def _in_any_orig(cx: int, cy: int) -> bool:
            for b in orig_boxes:
                x1, y1, x2, y2 = b["bbox"]
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    return True
            return False

        new_only = [b for b in new_boxes if not _in_any_orig(
            (b["bbox"][0] + b["bbox"][2]) // 2,
            (b["bbox"][1] + b["bbox"][3]) // 2,
        )]

        if not new_only:
            # Nothing new appeared — dismiss and return.
            self._adb.back()
            time.sleep(_SETTLE_DELAY_SECONDS)
            return

        self._emit_debug_log(
            f"In-place change: {len(new_only)} new element(s) appeared after tapping '{trigger_group.label}' (depth={depth})"
        )

        # Sort new elements top-to-bottom, left-to-right.
        new_only.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        for box in new_only:
            if self._cancel_requested:
                break

            bbox = box["bbox"]
            label = box.get("content") or f"popup@{bbox[0]},{bbox[1]}"

            tap_pre = self._take_screenshot_bytes()
            if tap_pre is None:
                continue

            self._adb.click(bbox)
            time.sleep(_SETTLE_DELAY_SECONDS)

            tap_post = self._take_screenshot_bytes()
            if tap_post is None:
                continue

            outcome, reason = self._classify_outcome(tap_pre, tap_post)
            self._current_step_number += 1
            self._record_step_log(
                action_type="tap_element",
                bbox=bbox,
                screenshot_path=self._save_step_screenshot(tap_post, bbox, f"popup_{self._current_step_number:04d}"),
                success=True,
                reasoning=reason,
                description=f"Popup/dropdown element '{label}' -> {outcome}",
            )

            if outcome == "navigated":
                to_sig = self._compute_screen_signature(tap_post)
                arrival_path = self._save_arrival_screenshot(tap_post, to_sig)
                self._record_navigation_edge(signature, to_sig, label, arrival_path, tuple(bbox))
                self._emit_debug_log(f"Popup element navigated: {signature} -> {to_sig} via '{label}'")
                self._return_to_base(signature)
                time.sleep(_SETTLE_DELAY_SECONDS)
                # Re-open the popup to continue tapping remaining new elements.
                self._adb.click(trigger_group.bbox)
                time.sleep(_SETTLE_DELAY_SECONDS)
                tap_post = self._take_screenshot_bytes() or tap_post

            elif outcome == "in_place_change":
                # Nested popup/dropdown — recurse.
                nested_pre = self._take_screenshot_bytes() or tap_pre
                self._handle_in_place_change(
                    signature, _Group(db_id=-1, bbox=tuple(bbox), label=label, member_bboxes=[]),
                    nested_pre, tap_post, screen_w, screen_h, depth=depth + 1,
                )

        # Dismiss the overlay by pressing Back.
        self._adb.back()
        time.sleep(_SETTLE_DELAY_SECONDS)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _take_screenshot_bytes(self) -> Optional[bytes]:
        """Capture a screenshot from the device and return raw PNG bytes."""
        tmp_path = os.path.join(self._screenshots_dir or ".", "_tmp_sweep_screenshot.png")
        try:
            os.makedirs(self._screenshots_dir or ".", exist_ok=True)
            result = self._adb.take_screenshot(tmp_path)
            if not result.success:
                logger.warning(f"Screenshot failed: {result.error_message}")
                return None
            with open(tmp_path, "rb") as f:
                data = f.read()
            return data
        except Exception as e:
            logger.warning(f"Failed to capture screenshot: {e}")
            return None
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Activity name fragments that are known generic containers hosting multiple
    # distinct screens (React Native host activities, WebView shells, etc.).
    # For these we append the UI title to disambiguate. For all other activities
    # the activity name itself is already unique to a single screen type.
    _GENERIC_ACTIVITY_FRAGMENTS = (
        "ReactActivity",
        "ReactActivityV2",
        "WebViewActivity",
        "WebActivity",
        "BrowserActivity",
        "ContainerActivity",
        "SinglePageActivity",  # only if it hosts multiple pages
    )

    def _compute_screen_signature(
        self,
        screen_bytes: bytes,
        coarse: bool = False,
        boxes: Optional[list] = None,
    ) -> str:
        """Compute a stable, unique screen signature.

        For most activities the activity name uniquely identifies the screen —
        use package/activity directly.

        For known generic container activities (React Native hosts, WebView shells)
        that serve many different screens, append the first stable UI title from
        the accessibility hierarchy to disambiguate.

        `coarse=True` always returns package/activity only (used for quick
        same-activity checks right after navigation).
        """
        package = self._adb.get_current_package() or "unknown"
        activity = self._adb.get_current_activity() or "unknown"
        base_sig = f"{package}/{activity}"

        if coarse:
            return base_sig

        # Only look up UI title for known generic container activities.
        is_generic = any(frag in activity for frag in self._GENERIC_ACTIVITY_FRAGMENTS)
        if not is_generic:
            return base_sig

        title = self._adb.get_screen_title() or ""
        safe_title = title.strip().replace("/", "|")[:60]
        if safe_title:
            return f"{base_sig}/{safe_title}"
        return base_sig

    def _emit_debug_log(self, message: str) -> None:
        if self._emit_step_phase_event is not None:
            self._emit_step_phase_event(
                "on_debug_log", self._current_run_id, self._current_step_number, message
            )
        logger.debug(message)

    def _record_navigation_edge(
        self, from_signature: str, to_signature: str, group_label: str,
        to_screenshot_path: Optional[str] = None,
        from_bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> None:
        """Record a directed navigation edge in the path graph."""
        if not self._db_manager or not self._current_run_id:
            return
        from_bbox_json = json.dumps(list(from_bbox)) if from_bbox else None
        try:
            conn = self._db_manager.get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO omni_sweep_edges "
                "(run_id, from_signature, to_signature, group_label, step_number, to_screenshot_path, from_bbox_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self._current_run_id,
                    from_signature,
                    to_signature,
                    group_label,
                    self._current_step_number,
                    to_screenshot_path,
                    from_bbox_json,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to record navigation edge: {e}")

    def _probe_bbox_subregions(
        self,
        group: "_Group",
        base_signature: str,
        known_to_sig: str,
        steps_completed: int,
        successful_actions: int,
        failed_actions: int,
        total_actions: int,
        destination_map: Dict[int, str],
    ) -> Tuple[int, int, int, int]:
        """Tap a grid of sample points within a bbox to detect multiple sub-elements.

        After the center tap already navigated somewhere, we tap the remaining
        sample points (thirds of width × thirds of height). If any point navigates
        to a *different* destination, we record it as a separate edge.
        Skips points that produce no_change or go to the same destination as center.
        """
        x1, y1, x2, y2 = group.bbox
        w = x2 - x1
        h = y2 - y1

        # Only probe if the bbox is large enough to plausibly contain multiple elements.
        if w < 60 or h < 40:
            return steps_completed, successful_actions, failed_actions, total_actions

        # Sample grid: left/center/right × top/center/bottom thirds.
        xs = [x1 + w // 4, x1 + w // 2, x1 + 3 * w // 4]
        ys = [y1 + h // 4, y1 + h // 2, y1 + 3 * h // 4]
        center = (x1 + w // 2, y1 + h // 2)

        seen_sigs = {known_to_sig}

        for py in ys:
            for px in xs:
                if (px, py) == center:
                    continue
                if self._cancel_requested:
                    break

                probe_bbox = (px - 4, py - 4, px + 4, py + 4)
                pre_bytes = self._take_screenshot_bytes()
                if pre_bytes is None:
                    continue

                self._adb.click(probe_bbox)
                time.sleep(_SETTLE_DELAY_SECONDS)
                post_bytes = self._take_screenshot_bytes()
                if post_bytes is None:
                    continue

                self._current_step_number += 1
                steps_completed += 1
                total_actions += 1

                outcome, reason = self._classify_outcome(pre_bytes, post_bytes)

                self._record_step_log(
                    action_type="probe_edge",
                    bbox=probe_bbox,
                    screenshot_path=self._save_step_screenshot(
                        pre_bytes, probe_bbox, f"probe_{self._current_step_number:04d}"
                    ),
                    success=True,
                    reasoning=reason,
                    description=f"Sub-probe at ({px},{py}) within '{group.label}' -> {outcome}",
                )

                if outcome == "navigated":
                    to_sig = self._compute_screen_signature(post_bytes)
                    if to_sig not in seen_sigs:
                        seen_sigs.add(to_sig)
                        probe_bbox = (px - 4, py - 4, px + 4, py + 4)
                        arrival_path = self._save_arrival_screenshot(post_bytes, to_sig)
                        label = f"{group.label} [sub@{px},{py}]"
                        self._record_navigation_edge(base_signature, to_sig, label, arrival_path, probe_bbox)
                        self._emit_debug_log(
                            f"Sub-probe found new destination: ({px},{py}) → {to_sig}"
                        )
                        successful_actions += 1
                    self._return_to_base(base_signature)
                    time.sleep(_SETTLE_DELAY_SECONDS)
                elif outcome == "no_change":
                    failed_actions += 1

        # If multiple distinct destinations found within this bbox → it's a carousel.
        if len(seen_sigs) > 1:
            self._update_group_status(base_signature, group, "navigated", f"carousel: {len(seen_sigs)} destinations")
            self._emit_debug_log(
                f"Carousel detected: bbox {group.bbox} has {len(seen_sigs)} distinct destinations"
            )

        return steps_completed, successful_actions, failed_actions, total_actions

    def _save_arrival_screenshot(self, screen_bytes: bytes, to_sig: str) -> Optional[str]:
        """Save the post-navigation screenshot as the thumbnail for the destination screen.

        Skips saving if a file for this signature already exists (first arrival wins).
        """
        if not self._screenshots_dir:
            return None
        try:
            sig_hash = to_sig.split("/")[-1] if "/" in to_sig else to_sig[:16]
            path = os.path.join(self._screenshots_dir, f"arrival_{sig_hash}.png")
            if not os.path.exists(path):
                os.makedirs(self._screenshots_dir, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(screen_bytes)
            return path
        except Exception as e:
            logger.debug(f"Failed to save arrival screenshot: {e}")
            return None

    def _navigate_back(self) -> None:
        self._adb.back()

    def _return_to_base(self, base_signature: str) -> None:
        """Navigate back to the base screen, pressing back as many times as needed.

        Handles confirmation dialogs and intermediate screens by looping until
        the current package/activity matches the base signature or we exhaust retries.
        Falls back to relaunching the app if we leave it entirely.
        """
        base_parts = base_signature.split("/")
        base_pkg = base_parts[0] if base_parts else self._app_package
        base_act = base_parts[1] if len(base_parts) > 1 else ""

        for attempt in range(5):
            self._adb.back()
            time.sleep(_SETTLE_DELAY_SECONDS)

            current_pkg = self._adb.get_current_package() or ""
            current_act = self._adb.get_current_activity() or ""

            if current_pkg != base_pkg:
                # Left the app — relaunch and done.
                self._emit_debug_log(
                    f"Back landed outside app ({current_pkg}/{current_act}) on attempt {attempt + 1}, "
                    f"relaunching {self._app_package}"
                )
                self._adb.launch_app(self._app_package)
                time.sleep(_SETTLE_DELAY_SECONDS * 2)
                return

            if current_act == base_act:
                # Back on the right activity.
                return

            self._emit_debug_log(
                f"Back attempt {attempt + 1}: still on {current_act}, expected {base_act} — pressing back again"
            )

        # Exhausted retries — relaunch as last resort.
        self._emit_debug_log(f"Could not return to base after 5 back presses, relaunching {self._app_package}")
        self._adb.launch_app(self._app_package)
        time.sleep(_SETTLE_DELAY_SECONDS * 2)

    def _get_group_status(self, signature: str, group: _Group) -> str:
        for eg in self._element_group_repository.get_by_screen(self._current_run_id, signature):
            if eg.id == group.db_id:
                return eg.status
        return "pending"

    def _update_group_status(self, signature: str, group: _Group, status: str, reason: str) -> None:
        self._element_group_repository.update_status(
            group.db_id, status, outcome_reason=reason, last_step_number=self._current_step_number
        )

    def _save_annotated_screenshot(
        self,
        screen_bytes: bytes,
        groups: List[_Group],
        filename_suffix: str,
        color: Tuple[int, int, int],
        action_type: str,
        description: str,
    ) -> None:
        """Save a screenshot with all group bboxes drawn in the given colour."""
        if not self._screenshots_dir or not self._step_log_repository:
            return
        try:
            image = Image.open(BytesIO(screen_bytes)).convert("RGB")
            draw = ImageDraw.Draw(image)
            for group in groups:
                left, top, right, bottom = group.bbox
                box_color = (255, 100, 200) if group.is_carousel else color
                draw.rectangle([left, top, right, bottom], outline=box_color, width=4)
                label_text = ("[carousel] " if group.is_carousel else "") + (group.label[:25] if group.label else "")
                if label_text:
                    draw.text((left + 4, top + 2), label_text, fill=box_color)
            os.makedirs(self._screenshots_dir, exist_ok=True)
            self._current_step_number += 1
            path = os.path.join(
                self._screenshots_dir,
                f"step_{self._current_step_number:04d}_{filename_suffix}.png",
            )
            image.save(path)
        except Exception as e:
            logger.debug(f"Failed to save annotated screenshot ({filename_suffix}): {e}")
            return
        self._record_step_log(
            action_type=action_type,
            bbox=None,
            screenshot_path=path,
            success=True,
            reasoning=None,
            description=description,
        )

    def _save_raw_boxes_screenshot(
        self, screen_bytes: bytes, groups: List[_Group], signature: str
    ) -> None:
        """Save overview with all raw OmniParser boxes (red) before any merging."""
        self._save_annotated_screenshot(
            screen_bytes,
            groups,
            filename_suffix="omni_raw",
            color=(30, 144, 255),
            action_type="omni_scan",
            description=f"OmniParser raw scan: {len(groups)} box(es) on {signature}",
        )

    def _save_merged_groups_screenshot(
        self, screen_bytes: bytes, groups: List[_Group], signature: str
    ) -> None:
        """Save overview after destination-based merging (green = merged groups)."""
        self._save_annotated_screenshot(
            screen_bytes,
            groups,
            filename_suffix="omni_merged",
            color=(0, 200, 0),
            action_type="omni_scan",
            description=(
                f"OmniParser merged groups: {len(groups)} effective group(s) on {signature}"
            ),
        )

    def _save_step_screenshot(
        self, screen_bytes: bytes, bbox: Optional[Tuple[int, int, int, int]], suffix: str
    ) -> Optional[str]:
        """Save an annotated screenshot for a single tap/probe step."""
        if not self._screenshots_dir:
            return None

        try:
            image = Image.open(BytesIO(screen_bytes)).convert("RGB")
            if bbox is not None:
                left, top, right, bottom = bbox
                left = max(0, min(left, image.width - 1))
                top = max(0, min(top, image.height - 1))
                right = max(0, min(right, image.width))
                bottom = max(0, min(bottom, image.height))
                draw = ImageDraw.Draw(image)
                draw.rectangle([left, top, right, bottom], outline=(30, 144, 255), width=8)

            os.makedirs(self._screenshots_dir, exist_ok=True)
            filename = f"step_{self._current_step_number:04d}_{suffix}.png"
            path = os.path.join(self._screenshots_dir, filename)
            image.save(path)
            return path
        except Exception as e:
            logger.debug(f"Failed to save step screenshot: {e}")
            return None

    def _record_step_log(
        self,
        action_type: str,
        bbox: Optional[Tuple[int, int, int, int]],
        screenshot_path: Optional[str],
        success: bool,
        reasoning: Optional[str],
        description: str,
    ) -> None:
        if not self._step_log_repository:
            return

        target_bbox_json = None
        if bbox is not None:
            left, top, right, bottom = bbox
            target_bbox_json = json.dumps({
                "top_left": [left, top],
                "bottom_right": [right, bottom],
            })

        try:
            self._step_log_repository.create_step_log(StepLog(
                id=None,
                run_id=self._current_run_id,
                step_number=self._current_step_number,
                timestamp=datetime.now(),
                from_screen_id=None,
                to_screen_id=None,
                action_type=action_type,
                action_description=description,
                target_bbox_json=target_bbox_json,
                input_text=None,
                execution_success=success,
                error_message=None,
                action_duration_ms=None,
                ai_response_time_ms=None,
                ai_reasoning=reasoning,
                screenshot_path=screenshot_path,
            ))
        except Exception as e:
            logger.debug(f"Failed to persist step log: {e}")
