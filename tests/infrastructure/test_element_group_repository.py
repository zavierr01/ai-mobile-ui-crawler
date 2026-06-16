"""Tests for ElementGroupRepository."""

import json

import pytest
from datetime import datetime

from mobile_crawler.infrastructure.database import DatabaseManager
from mobile_crawler.infrastructure.element_group_repository import ElementGroup, ElementGroupRepository
from mobile_crawler.infrastructure.run_repository import RunRepository, Run


@pytest.fixture
def db_manager_with_run(tmp_path):
    db_path = tmp_path / "test.db"
    db_manager = DatabaseManager(db_path)
    db_manager.create_schema()

    run_repo = RunRepository(db_manager)
    sample_run = Run(
        id=None,
        device_id="test_device_123",
        app_package="com.example.test",
        start_activity="com.example.test.MainActivity",
        start_time=datetime.now(),
        end_time=None,
        status="RUNNING",
        ai_provider="anthropic",
        ai_model="claude-sonnet-4-5-20250929",
        total_steps=0,
        unique_screens=0
    )
    run_id = run_repo.create_run(sample_run)
    db_manager._test_run_id = run_id
    return db_manager


@pytest.fixture
def repo(db_manager_with_run):
    return ElementGroupRepository(db_manager_with_run)


def _bbox_json(left, top, right, bottom):
    return json.dumps({"top_left": [left, top], "bottom_right": [right, bottom]})


def test_create_and_get_by_screen(repo, db_manager_with_run):
    run_id = db_manager_with_run._test_run_id
    signature = "com.example.test/MainActivity/abc123"

    group_id = repo.create(ElementGroup(
        id=None,
        run_id=run_id,
        screen_signature=signature,
        bbox_json=_bbox_json(10, 20, 100, 50),
        member_bboxes_json=json.dumps([[10, 20, 100, 50]]),
        label="Search button",
        status="pending",
    ))

    assert group_id > 0

    groups = repo.get_by_screen(run_id, signature)
    assert len(groups) == 1
    assert groups[0].id == group_id
    assert groups[0].label == "Search button"
    assert groups[0].status == "pending"
    assert json.loads(groups[0].bbox_json) == {"top_left": [10, 20], "bottom_right": [100, 50]}


def test_get_by_screen_filters_by_signature(repo, db_manager_with_run):
    run_id = db_manager_with_run._test_run_id

    repo.create(ElementGroup(
        id=None, run_id=run_id, screen_signature="screen_a",
        bbox_json=_bbox_json(0, 0, 10, 10), member_bboxes_json=None, label="A",
    ))
    repo.create(ElementGroup(
        id=None, run_id=run_id, screen_signature="screen_b",
        bbox_json=_bbox_json(0, 0, 10, 10), member_bboxes_json=None, label="B",
    ))

    groups_a = repo.get_by_screen(run_id, "screen_a")
    groups_b = repo.get_by_screen(run_id, "screen_b")

    assert [g.label for g in groups_a] == ["A"]
    assert [g.label for g in groups_b] == ["B"]


def test_update_status(repo, db_manager_with_run):
    run_id = db_manager_with_run._test_run_id
    signature = "screen_x"

    group_id = repo.create(ElementGroup(
        id=None, run_id=run_id, screen_signature=signature,
        bbox_json=_bbox_json(0, 0, 10, 10), member_bboxes_json=None, label="Item",
    ))

    repo.update_status(group_id, "navigated", outcome_reason="went to detail page", last_step_number=3)

    groups = repo.get_by_screen(run_id, signature)
    assert groups[0].status == "navigated"
    assert groups[0].outcome_reason == "went to detail page"
    assert groups[0].last_step_number == 3
