"""Tests for `ops.metrics`: `Counter`, `Gauge`, `MetricsRegistry`,
`record_health_metrics`, and `export_prometheus_text`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ops.metrics import (
    Counter,
    Gauge,
    MetricsRegistry,
    export_prometheus_text,
    record_health_metrics,
)
from ops.models import HealthCheckResult, PlatformHealth, classify_status

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _result(**overrides: object) -> HealthCheckResult:
    defaults: dict[str, object] = {
        "name": "configuration",
        "healthy": True,
        "detail": "ok",
        "checked_at": T0,
    }
    defaults.update(overrides)
    return HealthCheckResult(**defaults)  # type: ignore[arg-type]


def _health(checks: tuple[HealthCheckResult, ...]) -> PlatformHealth:
    return PlatformHealth(
        status=classify_status(checks),
        checks=checks,
        timestamp=T0,
        version="0.12.0",
        git_commit="abc1234",
    )


class TestCounter:
    def test_starts_at_zero(self) -> None:
        assert Counter("requests_total").value == 0.0

    def test_inc_increases_value(self) -> None:
        counter = Counter("requests_total")
        counter.inc()
        counter.inc(2.0)
        assert counter.value == 3.0

    def test_rejects_negative_increment(self) -> None:
        counter = Counter("requests_total")
        with pytest.raises(ValueError, match="non-negative"):
            counter.inc(-1.0)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Counter("")


class TestGauge:
    def test_starts_at_zero(self) -> None:
        assert Gauge("queue_depth").value == 0.0

    def test_set_replaces_value(self) -> None:
        gauge = Gauge("queue_depth")
        gauge.set(5.0)
        assert gauge.value == 5.0

    def test_inc_and_dec(self) -> None:
        gauge = Gauge("queue_depth")
        gauge.inc(3.0)
        gauge.dec(1.0)
        assert gauge.value == 2.0

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Gauge("")


class TestMetricsRegistry:
    def test_counter_is_get_or_create(self) -> None:
        registry = MetricsRegistry()
        first = registry.counter("requests_total")
        second = registry.counter("requests_total")
        assert first is second

    def test_gauge_is_get_or_create(self) -> None:
        registry = MetricsRegistry()
        first = registry.gauge("queue_depth")
        second = registry.gauge("queue_depth")
        assert first is second

    def test_counters_and_gauges_reflect_registered_metrics(self) -> None:
        registry = MetricsRegistry()
        registry.counter("requests_total")
        registry.gauge("queue_depth")
        assert [c.name for c in registry.counters] == ["requests_total"]
        assert [g.name for g in registry.gauges] == ["queue_depth"]


class TestRecordHealthMetrics:
    def test_records_aggregate_status_gauge(self) -> None:
        registry = MetricsRegistry()
        health = _health((_result(),))
        record_health_metrics(registry, health)
        assert registry.gauge("platform_health_status").value == 1.0

    def test_records_degraded_status_as_half(self) -> None:
        registry = MetricsRegistry()
        health = _health((_result(healthy=True), _result(healthy=False, name="market_data")))
        record_health_metrics(registry, health)
        assert registry.gauge("platform_health_status").value == 0.5

    def test_records_unhealthy_status_as_zero(self) -> None:
        registry = MetricsRegistry()
        health = _health((_result(healthy=False),))
        record_health_metrics(registry, health)
        assert registry.gauge("platform_health_status").value == 0.0

    def test_records_one_gauge_per_check(self) -> None:
        registry = MetricsRegistry()
        health = _health((_result(healthy=True), _result(healthy=False, name="market_data")))
        record_health_metrics(registry, health)
        assert registry.gauge("platform_health_check_configuration").value == 1.0
        assert registry.gauge("platform_health_check_market_data").value == 0.0


class TestExportPrometheusText:
    def test_empty_registry_exports_empty_string(self) -> None:
        assert export_prometheus_text(MetricsRegistry()) == ""

    def test_exports_counter_type_and_value(self) -> None:
        registry = MetricsRegistry()
        registry.counter("requests_total", "Total requests").inc(5.0)
        text = export_prometheus_text(registry)
        assert "# HELP requests_total Total requests" in text
        assert "# TYPE requests_total counter" in text
        assert "requests_total 5.0" in text

    def test_exports_gauge_type_and_value(self) -> None:
        registry = MetricsRegistry()
        registry.gauge("queue_depth", "Current queue depth").set(2.0)
        text = export_prometheus_text(registry)
        assert "# HELP queue_depth Current queue depth" in text
        assert "# TYPE queue_depth gauge" in text
        assert "queue_depth 2.0" in text

    def test_omits_help_line_when_no_help_text(self) -> None:
        registry = MetricsRegistry()
        registry.counter("requests_total")
        registry.gauge("queue_depth")
        text = export_prometheus_text(registry)
        assert "# HELP" not in text
