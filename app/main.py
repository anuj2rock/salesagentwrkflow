"""FastAPI application implementing the weather-report POC."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .schemas import ProviderSpec, WeatherPromptRequest, WeatherReportPayload
from .services.interpreter import build_prompt_interpreter
from .services.narrative import NarrativeService
from .services.pdf import render_pdf
from .services.provider_registry import provider_registry
from .services.weather_api import WeatherAPIClient

logger = logging.getLogger(__name__)

app = FastAPI(title="Weather Agent POC", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request.headers.get("x-correlation-id", uuid.uuid4().hex)
    logger.warning(
        "request validation failed",
        extra={"request_id": request_id, "path": str(request.url.path), "errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "request_id": request_id})


@app.post("/api/weather-report", response_class=Response)
async def weather_report(request: WeatherPromptRequest) -> Response:
    request_id = uuid.uuid4().hex
    logger.info("weather_report request received", extra={"request_id": request_id})
    interpreter = build_prompt_interpreter()
    spec = await interpreter.interpret(request.prompt)
    logger.info(
        "prompt interpreted",
        extra={
            "request_id": request_id,
            "location": spec.location.name,
            "timeframe": f"{spec.timeframe.start}->{spec.timeframe.end}",
            "metrics": spec.metrics,
            "units": spec.units,
        },
    )

    weather_client = WeatherAPIClient()
    try:
        dataset = await weather_client.fetch_daily_metrics(
            location=spec.location,
            timeframe_start=spec.timeframe.start,
            timeframe_end=spec.timeframe.end,
            metrics=spec.metrics,
            units=spec.units,
        )
        logger.info(
            "weather dataset fetched",
            extra={
                "request_id": request_id,
                "location": spec.location.name,
                "days": len(dataset.data),
                "source": dataset.source,
            },
        )
    except Exception as exc:  # pragma: no cover - network error handling
        logger.exception(
            "weather data fetch failed",
            extra={"request_id": request_id, "location": spec.location.name},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    narrative_service = NarrativeService()
    narrative = await narrative_service.generate(dataset, tone=spec.narrative_tone)
    logger.info(
        "narrative generated",
        extra={"request_id": request_id, "narrative_preview": narrative.summary[:80]},
    )
    payload = WeatherReportPayload(request=spec, dataset=dataset, narrative=narrative)
    try:
        pdf_bytes = render_pdf(payload)
    except Exception as exc:  # pragma: no cover - PDF generation safety net
        logger.exception(
            "pdf generation failed",
            extra={
                "request_id": request_id,
                "location": spec.location.name,
                "timeframe": f"{spec.timeframe.start}->{spec.timeframe.end}",
            },
        )
        raise HTTPException(status_code=500, detail="Failed to generate PDF") from exc

    logger.info(
        "pdf generated",
        extra={"request_id": request_id, "pdf_size_bytes": len(pdf_bytes)},
    )

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

