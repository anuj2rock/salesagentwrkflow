"""FastAPI application implementing the weather-report POC."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from .schemas import WeatherPromptRequest, WeatherReportPayload
from .services.interpreter import build_prompt_interpreter
from .services.narrative import NarrativeService
from .services.pdf import render_pdf
from .services.providers import ProviderClientFactory, ProviderRequestError

logger = logging.getLogger(__name__)

app = FastAPI(title="Weather Agent POC", version="0.1.0")


@app.post("/api/weather-report", response_class=Response)
async def weather_report(request: WeatherPromptRequest, provider_id: str | None = Query(default=None)) -> Response:
    request_id = uuid.uuid4().hex
    logger.info("weather_report request received", extra={"request_id": request_id})
    interpreter = build_prompt_interpreter()
    spec = await interpreter.interpret(request.prompt)
    provider_choice = provider_id or request.provider_id or spec.provider_id or "open-meteo"
    spec = spec.model_copy(
        update={
            "provider_id": provider_choice,
            "reference_id": spec.reference_id or request_id,
        }
    )
    logger.info(
        "prompt interpreted",
        extra={
            "request_id": request_id,
            "provider_id": spec.provider_id,
            "location": spec.location.name,
            "timeframe": f"{spec.timeframe.start}->{spec.timeframe.end}",
            "metrics": spec.metrics,
            "units": spec.units,
        },
    )

    factory = ProviderClientFactory()
    try:
        provider_client = factory.get_client(spec.provider_id or "open-meteo")
        dataset = await provider_client.fetch(spec)
        logger.info(
            "weather dataset fetched",
            extra={
                "request_id": request_id,
                "provider_id": spec.provider_id,
                "location": spec.location.name,
                "days": len(dataset.data),
                "source": dataset.source,
            },
        )
    except HTTPException:
        raise
    except ProviderRequestError as exc:
        logger.warning(
            "provider rejected request",
            extra={"request_id": request_id, "provider_id": spec.provider_id},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - network error handling
        logger.exception(
            "weather data fetch failed",
            extra={
                "request_id": request_id,
                "provider_id": spec.provider_id,
                "location": spec.location.name,
            },
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

