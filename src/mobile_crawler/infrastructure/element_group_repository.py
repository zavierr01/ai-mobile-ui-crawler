"""Repository for managing element groups discovered during OmniParser sweeps."""

from dataclasses import dataclass
from typing import List, Optional

from mobile_crawler.infrastructure.database import DatabaseManager


@dataclass
class ElementGroup:
    """Data class representing a group of UI elements on a screen."""
    id: Optional[int]
    run_id: int
    screen_signature: str
    bbox_json: str  # {"top_left": [x, y], "bottom_right": [x, y]} in pixels
    member_bboxes_json: Optional[str]  # original OmniParser boxes merged into this group
    label: Optional[str]  # OmniParser content/OCR text for the group
    status: str = "pending"  # pending | navigated | noise | dead | in_place
    outcome_reason: Optional[str] = None
    last_step_number: Optional[int] = None


class ElementGroupRepository:
    """Repository for CRUD operations on element_groups table."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize repository with database manager.

        Args:
            db_manager: DatabaseManager instance for crawler.db
        """
        self.db_manager = db_manager

    def create(self, group: ElementGroup) -> int:
        """Create a new element group and return its ID."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO element_groups (
                run_id, screen_signature, bbox_json, member_bboxes_json,
                label, status, outcome_reason, last_step_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            group.run_id,
            group.screen_signature,
            group.bbox_json,
            group.member_bboxes_json,
            group.label,
            group.status,
            group.outcome_reason,
            group.last_step_number,
        ))

        conn.commit()
        return cursor.lastrowid

    def get_by_screen(self, run_id: int, screen_signature: str) -> List[ElementGroup]:
        """Get all element groups for a given run and screen signature."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, run_id, screen_signature, bbox_json, member_bboxes_json,
                   label, status, outcome_reason, last_step_number
            FROM element_groups
            WHERE run_id = ? AND screen_signature = ?
            ORDER BY id
        """, (run_id, screen_signature))

        return [
            ElementGroup(
                id=row[0],
                run_id=row[1],
                screen_signature=row[2],
                bbox_json=row[3],
                member_bboxes_json=row[4],
                label=row[5],
                status=row[6],
                outcome_reason=row[7],
                last_step_number=row[8],
            )
            for row in cursor.fetchall()
        ]

    def update_status(
        self,
        group_id: int,
        status: str,
        outcome_reason: Optional[str] = None,
        last_step_number: Optional[int] = None,
    ) -> None:
        """Update the status (and optionally outcome reason / last step) of a group."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE element_groups
            SET status = ?, outcome_reason = ?, last_step_number = ?
            WHERE id = ?
        """, (status, outcome_reason, last_step_number, group_id))

        conn.commit()
