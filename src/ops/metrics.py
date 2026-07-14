"""Structured metrics: `Counter`/`Gauge` primitives, a `MetricsRegistry`
to hold them, and a text exporter.

Zero third-party dependencies, the same "pure stdlib" convention every
`ops` module follows -- no `prometheus_client` dependency. The text
`export_prometheus_text` writes is the Prometheus exposition format
(https://prometheus.io/docs/instrumenting/exposition_formats/), a
stable, widely-scraped plain-text format; writing it by hand avoids
pulling in a client library for what is, structurally, string
formatting over two simple counters.

`record_health_metrics` is the "Metrics -> PlatformHealth -> Exporter"
pipeline: it reads a `PlatformHealth` report and updates a
`MetricsRegistry` from it, so metrics never recompute health
independently -- `PlatformHealth` stays the single operational model
everything else reads.
"""

from __future__ import annotations

from ops.models import HealthStatus, PlatformHealth

_STATUS_VALUES: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 1.0,
    HealthStatus.DEGRADED: 0.5,
    HealthStatus.UNHEALTHY: 0.0,
}


class Counter:
    """A monotonically increasing metric. `inc` rejects a negative
    amount -- a counter that can decrease is a `Gauge`, not a
    `Counter`; conflating the two would make the exported metric type
    lie about what it represents."""

    def __init__(self, name: str, help_text: str = "") -> None:
        if not name:
            raise ValueError("name must not be empty")
        self.name = name
        self.help_text = help_text
        self._value = 0.0

    def inc(self, amount: float = 1.0) -> None:
        if amount < 0:
            raise ValueError(f"Counter.inc amount must be non-negative, got {amount!r}")
        self._value += amount

    @property
    def value(self) -> float:
        return self._value


class Gauge:
    """A metric that can move in either direction -- the natural shape
    for "current value of something" (a queue depth, a health-status
    encoding), as opposed to `Counter`'s "total number of times
    something happened"."""

    def __init__(self, name: str, help_text: str = "") -> None:
        if not name:
            raise ValueError("name must not be empty")
        self.name = name
        self.help_text = help_text
        self._value = 0.0

    def set(self, value: float) -> None:
        self._value = value

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class MetricsRegistry:
    """Holds every `Counter`/`Gauge` this process has registered.
    `counter`/`gauge` are get-or-create -- the same name always returns
    the same instance, so unrelated call sites recording the same
    metric never silently create two disconnected series."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}

    def counter(self, name: str, help_text: str = "") -> Counter:
        if name not in self._counters:
            self._counters[name] = Counter(name, help_text)
        return self._counters[name]

    def gauge(self, name: str, help_text: str = "") -> Gauge:
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, help_text)
        return self._gauges[name]

    @property
    def counters(self) -> tuple[Counter, ...]:
        return tuple(self._counters.values())

    @property
    def gauges(self) -> tuple[Gauge, ...]:
        return tuple(self._gauges.values())


def record_health_metrics(registry: MetricsRegistry, health: PlatformHealth) -> None:
    """Update `registry` from `health`: one gauge per check
    (`platform_health_check_<name>`, 1.0/0.0) plus one aggregate gauge
    (`platform_health_status`, 1.0/0.5/0.0 for healthy/degraded/
    unhealthy). Never constructs its own notion of health -- `health` is
    the only input."""
    registry.gauge(
        "platform_health_status", "Aggregate platform health (1=healthy, 0=unhealthy)"
    ).set(_STATUS_VALUES[health.status])
    for check in health.checks:
        registry.gauge(
            f"platform_health_check_{check.name}",
            f"Health of the {check.name} subsystem (1=healthy, 0=unhealthy)",
        ).set(1.0 if check.healthy else 0.0)


def export_prometheus_text(registry: MetricsRegistry) -> str:
    """Render every metric in `registry` as Prometheus exposition-format
    text."""
    lines: list[str] = []
    for counter in registry.counters:
        if counter.help_text:
            lines.append(f"# HELP {counter.name} {counter.help_text}")
        lines.append(f"# TYPE {counter.name} counter")
        lines.append(f"{counter.name} {counter.value}")
    for gauge in registry.gauges:
        if gauge.help_text:
            lines.append(f"# HELP {gauge.name} {gauge.help_text}")
        lines.append(f"# TYPE {gauge.name} gauge")
        lines.append(f"{gauge.name} {gauge.value}")
    return "\n".join(lines) + ("\n" if lines else "")


__all__ = [
    "Counter",
    "Gauge",
    "MetricsRegistry",
    "export_prometheus_text",
    "record_health_metrics",
]
