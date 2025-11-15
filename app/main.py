"""FastAPI application implementing the weather-report POC."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .schemas import WeatherPromptRequest, WeatherReportPayload
from .services.interpreter import PromptInterpreter
from .services.narrative import build_narrative
from .services.pdf import render_pdf
from .services.weather_api import WeatherAPIClient

app = FastAPI(title="Weather Agent POC", version="0.1.0")


@app.post("/api/weather-report", response_class=Response)
async def weather_report(request: WeatherPromptRequest) -> Response:
    interpreter = PromptInterpreter()
    spec = await interpreter.interpret(request.prompt)

    weather_client = WeatherAPIClient()
    try:
        dataset = await weather_client.fetch_daily_metrics(
            location=spec.location,
            timeframe_start=spec.timeframe.start,
            timeframe_end=spec.timeframe.end,
            metrics=spec.metrics,
            units=spec.units,
        )
    except Exception as exc:  # pragma: no cover - network error handling
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    narrative = build_narrative(dataset)
    payload = WeatherReportPayload(request=spec, dataset=dataset, narrative=narrative)
    pdf_bytes = render_pdf(payload)

    return Response(content=pdf_bytes, media_type="application/pdf")

