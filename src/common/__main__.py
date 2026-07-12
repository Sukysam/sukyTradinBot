"""Foundation smoke-test entrypoint: `python -m common`.

Loads settings, configures structured logging, and emits one log line
confirming the foundation is wired together correctly, then exits 0. This
is what the Docker image's default `CMD` runs (see `Dockerfile`) — it
exists so `docker build && docker run` produces verifiable evidence that
configuration and logging actually work end-to-end in the container, not
just in a developer's local virtualenv. It is not, and must not become, a
trading entrypoint — see docs/engineering-handbook/00_MASTER_CHARTER.md's
Milestone 1 scope.
"""

from __future__ import annotations

from common import Settings, __version__, configure_logging, get_logger


def main() -> None:
    settings = Settings()
    configure_logging(settings)
    logger = get_logger(__name__)
    logger.info(
        "Foundation ready",
        extra={
            "app_name": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
        },
    )


if __name__ == "__main__":
    main()
