from __future__ import annotations

import logging

from fastapi import FastAPI

from src.core.database import get_engine
from src.core.settings import settings


_TRACING_CONFIGURED = False


def setup_tracing(app: FastAPI) -> bool:
    global _TRACING_CONFIGURED
    if _TRACING_CONFIGURED or not settings.otel_enabled:
        return False

    logger = logging.getLogger("src.core.tracing")

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "deployment.environment": settings.app_env,
            }
        )
        tracer_provider = TracerProvider(resource=resource)

        exporter = ConsoleSpanExporter()
        if settings.otel_exporter_otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
                insecure=settings.otel_exporter_otlp_insecure,
            )

        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(tracer_provider)

        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
        SQLAlchemyInstrumentor().instrument(engine=get_engine())
        RequestsInstrumentor().instrument()
        _TRACING_CONFIGURED = True
        logger.info("tracing_enabled")
        return True
    except Exception as exc:
        logger.warning("tracing_not_configured: %s", str(exc))
        return False
