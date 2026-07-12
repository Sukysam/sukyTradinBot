# syntax=docker/dockerfile:1
#
# Foundation image (Milestone 1). Builds and runs only `src/common` — the
# domain-neutral configuration/logging/interfaces/utilities package. It
# does NOT install or run regime-trader/ or backtest/: those depend on the
# `trading` extra (pandas, numpy, torch, transformers, hmmlearn, ta,
# alpaca-py) and have no packaged entrypoint yet. Wiring a real trading
# entrypoint into this image is out of scope for this milestone — see
# docs/engineering-handbook/00_MASTER_CHARTER.md Section 5 and
# docs/engineering-handbook/Architecture/Known Gaps.md.

FROM python:3.11-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import common" || exit 1

CMD ["python", "-m", "common"]
