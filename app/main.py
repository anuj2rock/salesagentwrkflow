"""FastAPI application implementing the weather-report POC."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .schemas import ProviderSpec, WeatherPromptRequest, WeatherReportPayload
from .services.interpreter import build_prompt_interpreter
from .services.logging import RequestContext, request_log_store
from .services.narrative import NarrativeService
from .services.pdf import render_pdf
from .services.provider_registry import provider_registry
from .services.providers import ProviderClientFactory, ProviderRequestError

logger = logging.getLogger(__name__)

app = FastAPI(title="Weather Agent POC", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request.headers.get("x-correlation-id", uuid.uuid4().hex)
    context = RequestContext(request_id=request_id)
    context.warning(
        logger,
        "request validation failed",
        event="request.validation_error",
        path=str(request.url.path),
        errors=exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "request_id": request_id})


@app.post("/api/weather-report", response_class=Response)
async def weather_report(request: WeatherPromptRequest, provider_id: str | None = Query(default=None)) -> Response:
    context = RequestContext()
    context.info(
        logger,
        "weather_report request received",
        event="spec.ingestion",
        provider_override=provider_id,
    )
    interpreter = build_prompt_interpreter()
    interpreter_name = interpreter.__class__.__name__
    context.with_interpreter(interpreter_name)
    context.info(logger, "prompt interpreter selected", event="interpreter.choice", interpreter_type=interpreter_name)
    spec = await interpreter.interpret(request.prompt, context=context)
    provider_choice = provider_id or request.provider_id or spec.provider_id or "open-meteo"
    spec = spec.model_copy(
        update={
            "provider_id": provider_choice,
            "reference_id": spec.reference_id or context.request_id,
        }
    )
    context.with_provider(spec.provider_id)
    context.info(
        logger,
        "prompt interpreted",
        event="spec.normalized",
        location=spec.location.name,
        timeframe=f"{spec.timeframe.start}->{spec.timeframe.end}",
        metrics=spec.metrics,
        units=spec.units,
    )

    factory = ProviderClientFactory()
    try:
        provider_client = factory.get_client(spec.provider_id or "open-meteo")
        dataset = await provider_client.fetch(spec, context=context)
        context.info(
            logger,
            "weather dataset fetched",
            event="provider.dataset_ready",
            location=spec.location.name,
            days=len(dataset.data),
            source=dataset.source,
        )
    except HTTPException:
        raise
    except ProviderRequestError as exc:
        context.warning(
            logger,
            "provider rejected request",
            event="provider.rejected",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - network error handling
        context.exception(
            logger,
            "weather data fetch failed",
            event="provider.fetch_failed",
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    narrative_service = NarrativeService()
    narrative = await narrative_service.generate(dataset, tone=spec.narrative_tone, context=context)
    context.info(
        logger,
        "narrative generated",
        event="narrative.generated",
        narrative_preview=narrative.summary[:80],
    )
    payload = WeatherReportPayload(request=spec, dataset=dataset, narrative=narrative)
    try:
        pdf_bytes = render_pdf(payload, context=context)
    except Exception as exc:  # pragma: no cover - PDF generation safety net
        context.exception(
            logger,
            "pdf generation failed",
            event="pdf.render_failed",
            location=spec.location.name,
            timeframe=f"{spec.timeframe.start}->{spec.timeframe.end}",
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to generate PDF") from exc

    return Response(content=pdf_bytes, media_type="application/pdf")


@app.post("/api/providers")
async def upsert_provider(spec: ProviderSpec) -> dict:
    request_id = uuid.uuid4().hex
    logger.info(
        "provider spec upsert requested",
        extra={"request_id": request_id, "provider_id": spec.provider_id},
    )
    try:
        stored = provider_registry.upsert(spec)
    except Exception as exc:  # pragma: no cover - defensive persistence logging
        logger.exception(
            "provider spec upsert failed",
            extra={"request_id": request_id, "provider_id": spec.provider_id},
        )
        raise HTTPException(status_code=500, detail="Failed to store provider spec") from exc

    logger.info(
        "provider spec upserted",
        extra={
            "request_id": request_id,
            "provider_id": spec.provider_id,
            "version": spec.version,
            "endpoint_count": len(spec.endpoints),
        },
    )
    return stored.sanitized_dict()


@app.get("/api/providers/{provider_id}")
async def get_provider(provider_id: str) -> dict:
    request_id = uuid.uuid4().hex
    logger.info(
        "provider spec lookup",
        extra={"request_id": request_id, "provider_id": provider_id},
    )
    spec = provider_registry.get(provider_id)
    if not spec:
        logger.info(
            "provider spec not found",
            extra={"request_id": request_id, "provider_id": provider_id},
        )
        raise HTTPException(status_code=404, detail="Provider not found")

    logger.info(
        "provider spec retrieved",
        extra={
            "request_id": request_id,
            "provider_id": provider_id,
            "version": spec.version,
            "endpoint_count": len(spec.endpoints),
        },
    )
    return spec.sanitized_dict()


@app.get("/api/requests/{request_id}/logs")
async def get_request_logs(request_id: str) -> dict:
    """Developer-facing helper to inspect the recorded milestones."""

    return {"request_id": request_id, "logs": request_log_store.get(request_id)}

