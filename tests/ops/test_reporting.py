"""Tests for `ops.reporting.generate_health_report` and
`generate_diagnostic_report`."""

from __future__ import annotations

from datetime import datetime, timezone

from ops.checks import configuration_check, market_data_check
from ops.diagnostics import build_diagnostic_report
from ops.health import evaluate_health
from ops.models import DeploymentInfo, PlatformInfo, RuntimeContext
from ops.reporting import generate_diagnostic_report, generate_health_report

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _runtime() -> RuntimeContext:
    info = PlatformInfo(
        version="0.12.0", git_commit="abc1234", build_time=T0, python_version="3.9.6"
    )
    return RuntimeContext(platform_info=info, environment="production", startup_time=T0)


def _deployment(**overrides: object) -> DeploymentInfo:
    defaults: dict[str, object] = {
        "version": "0.12.0",
        "git_commit": "abc1234",
        "build_time": T0,
        "deployment_environment": "production",
        "deployment_id": "deploy-001",
    }
    defaults.update(overrides)
    return DeploymentInfo(**defaults)  # type: ignore[arg-type]


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


class TestGenerateDiagnosticReport:
    def test_report_includes_version_and_environment(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = build_diagnostic_report(_runtime(), health)
        text = generate_diagnostic_report(report)
        assert "0.12.0" in text
        assert "abc1234" in text
        assert "production" in text

    def test_report_notes_missing_deployment_tracking(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = build_diagnostic_report(_runtime(), health)
        text = generate_diagnostic_report(report)
        assert "no deployment tracking available" in text

    def test_report_includes_deployment_id_when_present(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = build_diagnostic_report(_runtime(), health, deployment=_deployment())
        text = generate_diagnostic_report(report)
        assert "deploy-001" in text

    def test_report_shows_none_when_rollback_target_unset(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = build_diagnostic_report(_runtime(), health, deployment=_deployment())
        text = generate_diagnostic_report(report)
        assert "rollback_target: (none)" in text

    def test_report_shows_rollback_target_when_set(self) -> None:
        checks = [configuration_check(lambda: True)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        deployment = _deployment(rollback_target="deploy-000")
        report = build_diagnostic_report(_runtime(), health, deployment=deployment)
        text = generate_diagnostic_report(report)
        assert "rollback_target: deploy-000" in text

    def test_report_includes_health_checks(self) -> None:
        checks = [configuration_check(lambda: True), market_data_check(lambda: False)]
        health = evaluate_health(checks, version="0.12.0", git_commit="abc1234")
        report = build_diagnostic_report(_runtime(), health)
        text = generate_diagnostic_report(report)
        assert "[FAIL] market_data" in text
