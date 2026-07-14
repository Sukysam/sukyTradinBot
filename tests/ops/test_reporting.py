"""Tests for `ops.reporting.generate_health_report`."""

from __future__ import annotations

from datetime import datetime, timezone

from ops.checks import configuration_check, market_data_check
from ops.health import evaluate_health
from ops.reporting import generate_health_report

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


class TestGenerateHealthReport:
    def test_report_includes_status_version_and_commit(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = generate_health_report(health)
        assert "HEALTHY" in report
        assert "0.12.0" in report
        assert "abc1234" in report

    def test_report_marks_passing_check_ok(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = generate_health_report(health)
        assert "[OK] configuration: ok" in report

    def test_report_marks_failing_check_fail(self) -> None:
        checks = [configuration_check(lambda: True), market_data_check(lambda: False)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = generate_health_report(health)
        assert "[FAIL] market_data: probe returned False" in report
