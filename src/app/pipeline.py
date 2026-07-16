"""`compose_pipeline` -- folds a first-stage `handle_bar` and any number
of `handle_frame` stages into one `on_bar`-compatible callable. See
docs/engineering-handbook/Architecture/ADR/ADR-031-Signal-Orchestration-Design.md.

Every emitter's `handle_bar`/`handle_frame` takes and returns a
`RuntimeFrame` (or `None` to mean "stop here, nothing to pass on") --
composing the runtime is then just folding those functions in order,
not injecting a "next hook" callback into every emitter's constructor.
`MarketDataLoop.on_bar` itself is typed `Callable[[Bar], None]`; the
composed callable this returns satisfies that exactly by discarding
whatever the final stage returns -- nothing downstream of `on_bar`
needs the frame back, each stage already did its own logging/metrics/
error-handling before returning it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from app.frame import RuntimeFrame
from app.runtime import BarCallback
from market_data.models import Bar

# `Optional[...]`, not `RuntimeFrame | None` -- this is a runtime type
# alias assignment, not an annotation, so `from __future__ import
# annotations` doesn't defer it; `X | None` as a plain expression needs
# Python 3.10+, and this project supports 3.9 (see pyproject.toml).
FrameStage = Callable[[RuntimeFrame], Optional[RuntimeFrame]]


def compose_pipeline(
    handle_bar: Callable[[Bar], RuntimeFrame | None],
    *stages: FrameStage,
) -> BarCallback:
    """`handle_bar` builds the first `RuntimeFrame` (or returns `None`
    if it couldn't -- e.g. a feature-computation failure); each
    subsequent stage in `stages` runs only if the previous one returned
    a frame, short-circuiting the rest of the chain otherwise. A stage
    raising is not caught here -- `MarketDataLoop._poll_symbol`'s own
    try/except around calling `on_bar` is the existing safety net for
    that (logs `on_bar_callback_failed`, never stops the loop); every
    *expected* failure mode inside a stage (a computation/inference/
    decision/arbitration error) is already caught by that stage itself
    and turned into a `None` return, not an exception.
    """

    def _on_bar(bar: Bar) -> None:
        frame: RuntimeFrame | None = handle_bar(bar)
        for stage in stages:
            if frame is None:
                return
            frame = stage(frame)

    return _on_bar


__all__ = ["FrameStage", "compose_pipeline"]
