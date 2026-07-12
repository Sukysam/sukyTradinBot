from __future__ import annotations

import json
import logging

import pytest

from common.__main__ import main


def test_main_logs_a_ready_message_and_does_not_raise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main()

    root = logging.getLogger()
    assert len(root.handlers) == 1  # configure_logging ran


def test_main_emits_valid_json_with_expected_fields(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    assert lines, "expected at least one log line on stdout"

    payload = json.loads(lines[-1])
    assert payload["message"] == "Foundation ready"
    assert payload["app_name"] == "regime-trader"
    assert "version" in payload
    assert "environment" in payload
