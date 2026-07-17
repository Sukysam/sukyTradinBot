"""`compose_pipeline` -- folds a first-stage `handle_bar` and any number
of `handle_frame` stages into one `on_bar`-compatible callable. See
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md
and
docs/engineering-handbook/Architecture/ADR/ADR-033-Runtime-Paper-Execution-Design.md.

Every emitter's `handle_bar`/`handle_frame` takes and returns a
`RuntimeFrame` (or `None` to mean "stop here, nothing to pass on") --
composing the runtime is then just folding those functions in order,
not injecting a "next hook" callback into every emitter's constructor.
`MarketDataLoop.on_bar` itself is typed `Callable[[Bar], None]`; the
composed callable this returns satisfies that exactly by discarding
whatever the final stage returns -- nothing downstream of `on_bar`
needs the frame back, each stage already did its own logging/metrics/
error-handling before returning it.

`PipelineResult` is a separate, optional reporting channel layered on
top of that: it wraps (never replaces) the `RuntimeFrame` a single
`on_bar` call produced, plus which named stage the run reached and
whether it succeeded. A caller that wants one place to observe runtime
status -- for structured logging, replay diagnostics, or operational
metrics spanning the whole pipeline rather than one emitter at a time
-- supplies `stage_names`/`on_result` to `compose_pipeline`; a caller
that does not care (every `build_*_loop` before Phase G) gets the
exact same behavior as before, since both parameters default to
no-ops.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Optional

from app.frame import RuntimeFrame
from app.runtime import BarCallback
from market_data.models import Bar

# `Optional[...]`, not `RuntimeFrame | None` -- this is a runtime type
# alias assignment, not an annotation, so `from __future__ import
# annotations` doesn't defer it; `X | None` as a plain expression needs
# Python 3.10+, and this project supports 3.9 (see pyproject.toml).
FrameStage = Callable[[RuntimeFrame], Optional[RuntimeFrame]]


@dataclass(frozen=True)
class PipelineResult:
    """The runtime status of one `on_bar` call through `compose_pipeline`.

    `frame` is the last successfully-produced `RuntimeFrame` -- for a
    short-circuit or a raised exception, that is the frame going *into*
    whichever stage stopped the pipeline (still useful for diagnostics:
    it carries everything every earlier stage already enriched it
    with), not the `None` that stage returned or the exception it
    raised. `frame` is `None` only in the one case where there is
    nothing to report at all: `handle_bar` itself returning `None`
    before any `RuntimeFrame` ever existed. `completed_stage` names
    whichever stage the run reached: the stage that finished the
    pipeline (`success=True`), the stage that short-circuited it by
    returning `None` (`success=False`, `error=None` -- an ordinary,
    expected stop, same as every stage's own ordinary-skip logging), or
    the stage that raised (`success=False`, `error` set to `str(exc)`
    -- the exception itself is still re-raised after this is reported,
    so `MarketDataLoop`'s own existing safety net still catches and
    logs it; this is a reporting hook, not a second error-handling
    layer).
    """

    frame: RuntimeFrame | None
    completed_stage: str
    success: bool
    error: str | None = None


ResultSink = Callable[[PipelineResult], None]


def compose_pipeline(
    handle_bar: Callable[[Bar], RuntimeFrame | None],
    *stages: FrameStage,
    stage_names: Sequence[str] = (),
    on_result: ResultSink | None = None,
) -> BarCallback:
    """`handle_bar` builds the first `RuntimeFrame` (or returns `None`
    if it couldn't -- e.g. a feature-computation failure); each
    subsequent stage in `stages` runs only if the previous one returned
    a frame, short-circuiting the rest of the chain otherwise. A stage
    raising is not caught for control-flow purposes here --
    `MarketDataLoop._poll_symbol`'s own try/except around calling
    `on_bar` remains the safety net that keeps the loop alive (logs
    `on_bar_callback_failed`, never stops the loop); every *expected*
    failure mode inside a stage (a computation/inference/decision/
    arbitration error) is already caught by that stage itself and
    turned into a `None` return, not an exception. `on_result`, if
    given, is still notified before a raised exception is re-raised,
    so a genuinely unexpected failure is reported the same way an
    ordinary one is.

    `stage_names`, if given, must have exactly `len(stages) + 1`
    entries -- one for `handle_bar`'s own stage, then one per entry in
    `stages`, in order. Omitted (the default for every `build_*_loop`
    before Phase G), stages are named positionally (`stage_0`,
    `stage_1`, ...) and `on_result` is never called since it also
    defaults to `None`.
    """
    names = list(stage_names) if stage_names else [f"stage_{i}" for i in range(len(stages) + 1)]
    if len(names) != len(stages) + 1:
        raise ValueError(
            f"stage_names must have exactly {len(stages) + 1} entries "
            f"(len(stages) + 1), got {len(names)}"
        )

    def _report(
        frame: RuntimeFrame | None, stage_index: int, success: bool, error: str | None = None
    ) -> None:
        if on_result is not None:
            on_result(
                PipelineResult(
                    frame=frame, completed_stage=names[stage_index], success=success, error=error
                )
            )

    def _on_bar(bar: Bar) -> None:
        frame: RuntimeFrame | None = handle_bar(bar)
        if frame is None:
            _report(None, 0, False)
            return

        stage_index = 0
        for stage in stages:
            stage_index += 1
            previous_frame = frame
            try:
                frame = stage(frame)
            except Exception as exc:
                _report(previous_frame, stage_index, False, str(exc))
                raise
            if frame is None:
                _report(previous_frame, stage_index, False)
                return

        _report(frame, stage_index, True)

    return _on_bar


__all__ = ["FrameStage", "PipelineResult", "ResultSink", "compose_pipeline"]
