"""Tests for OmniParserSweepService."""

import io
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PIL import Image

from mobile_crawler.domain.omniparser_sweep_service import OmniParserSweepService
from mobile_crawler.infrastructure.database import DatabaseManager
from mobile_crawler.infrastructure.run_repository import Run, RunRepository


class FakeConfigManager:
    def __init__(self, **overrides):
        self._values = {
            "omni_sweep_mode": "breadth",
            "ai_provider": None,
            "ai_model": None,
            "omniparser_backend": "local",
        }
        self._values.update(overrides)

    def get(self, key, default=None):
        return self._values.get(key, default)


@pytest.fixture
def db_manager_with_run(tmp_path):
    db_path = tmp_path / "test.db"
    db_manager = DatabaseManager(db_path)
    db_manager.create_schema()

    run_repo = RunRepository(db_manager)
    run_id = run_repo.create_run(Run(
        id=None,
        device_id="test_device",
        app_package="com.example.test",
        start_activity="com.example.test.MainActivity",
        start_time=datetime.now(),
        end_time=None,
        status="RUNNING",
        ai_provider=None,
        ai_model=None,
        total_steps=0,
        unique_screens=0,
    ))
    db_manager._test_run_id = run_id
    return db_manager


def _make_png_bytes(color, size=(100, 100)):
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def service(tmp_path, monkeypatch, db_manager_with_run):
    config = FakeConfigManager()
    svc = OmniParserSweepService(
        config_manager=config,
        ai_interaction_repository=None,
        device_id="test_device",
    )

    # Avoid real ADB / network calls.
    svc._adb = MagicMock()
    svc._adb._get_screen_size.return_value = (1000, 2000)
    svc._adb.get_current_package.return_value = "com.example.test"
    svc._adb.get_current_activity.return_value = "MainActivity"

    svc._omni_parser_client = MagicMock()

    monkeypatch.setattr(
        "mobile_crawler.domain.omniparser_sweep_service.DatabaseManager",
        lambda: db_manager_with_run,
    )

    screenshots_dir = tmp_path / "screenshots"
    svc.begin_step_tracking(
        run_id=db_manager_with_run._test_run_id,
        emit_step_phase_event=None,
        screenshots_dir=str(screenshots_dir),
    )
    return svc


def test_denormalize_elements_converts_to_pixels(service):
    elements = [
        {"bbox": [0.1, 0.2, 0.3, 0.4], "content": "Button A", "interactivity": True},
        {"bbox": [0.0, 0.0, 0.0, 0.0], "content": "degenerate", "interactivity": True},  # dropped
    ]

    boxes = service._denormalize_elements(elements, screen_w=1000, screen_h=2000)

    assert len(boxes) == 1
    box = boxes[0]
    assert box["bbox"] == (100, 400, 300, 800)
    assert box["content"] == "Button A"


def test_classify_outcome_no_change(service):
    pre = _make_png_bytes((255, 255, 255))
    post = _make_png_bytes((255, 255, 255))

    outcome, reason = service._classify_outcome(pre, post)

    assert outcome == "no_change"


def test_classify_outcome_navigated(service):
    pre = _make_png_bytes((255, 255, 255))
    post = _make_png_bytes((0, 0, 0))

    outcome, reason = service._classify_outcome(pre, post)

    assert outcome == "navigated"


def test_classify_outcome_ambiguous_band_returns_in_place(service):
    # Build an image where roughly 10% of pixels differ -- in the ambiguous band.
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    for x in range(10):
        for y in range(100):
            img.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    post = buf.getvalue()

    pre = _make_png_bytes((255, 255, 255), size=(100, 100))

    outcome, reason = service._classify_outcome(pre, post)

    # Ambiguous band (1-35%) -> in_place_change, no LLM call
    assert outcome == "in_place_change"
    assert "ambiguous" in reason


def test_get_or_create_groups_persists_and_reuses(service, db_manager_with_run):
    screen_bytes = _make_png_bytes((255, 255, 255), size=(1000, 2000))

    service._omni_parser_client.parse.return_value = [
        {"bbox": [0.0, 0.0, 0.1, 0.05], "content": "A", "interactivity": True},
        {"bbox": [0.5, 0.5, 0.6, 0.55], "content": "B", "interactivity": True},
    ]

    signature = "com.example.test/MainActivity/sig1"
    groups = service._get_or_create_groups(signature, screen_bytes, 1000, 2000)

    assert len(groups) == 2
    assert service._omni_parser_client.parse.call_count == 1

    # Second call should reuse persisted groups, not call OmniParser again.
    groups_again = service._get_or_create_groups(signature, screen_bytes, 1000, 2000)
    assert len(groups_again) == 2
    assert service._omni_parser_client.parse.call_count == 1


def test_compute_screen_signature_includes_package_and_activity(service):
    screen_bytes = _make_png_bytes((255, 255, 255), size=(1000, 2000))
    signature = service._compute_screen_signature(screen_bytes)

    assert signature.startswith("com.example.test/MainActivity/")
