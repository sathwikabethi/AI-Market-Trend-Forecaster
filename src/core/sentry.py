from __future__ import annotations

import os


def setup_sentry() -> bool:
    """Optional Sentry initialization.

    This is intentionally best-effort and dependency-optional:
    - If `SENTRY_DSN` is not set, it stays disabled.
    - If `sentry_sdk` isn't installed, it stays disabled.
    """

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except Exception:
        return False

    integrations = []
    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        integrations.append(FastApiIntegration())
    except Exception:
        pass

    traces_sample_rate_raw = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0").strip()
    try:
        traces_sample_rate = float(traces_sample_rate_raw)
    except Exception:
        traces_sample_rate = 0.0

    environment = os.environ.get("APP_ENV", "development")
    release = os.environ.get("SERVICE_VERSION", "")

    try:
        sentry_sdk.init(
            dsn=dsn,
            integrations=integrations,
            traces_sample_rate=max(0.0, min(1.0, traces_sample_rate)),
            environment=environment,
            release=release or None,
        )
        return True
    except Exception:
        return False

