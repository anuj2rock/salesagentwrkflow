"""Render PDF artifacts from structured data using ReportLab only."""
from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..schemas import WeatherReportPayload
from .logging import RequestContext

logger = logging.getLogger(__name__)


def _format_float(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    text = f"{value:.1f}"
    if suffix:
        text = f"{text}{suffix}"
    return text


def _metadata_lines(payload: WeatherReportPayload) -> List[str]:
    request = payload.request
    location = request.location
    timeframe = request.timeframe
    metrics = ", ".join(request.metrics) if request.metrics else "-"
    generated_at = datetime.utcnow().isoformat()

    lines = [
        "Weather report summary",
        f"Location: {location.name} ({location.latitude}, {location.longitude})",
        f"Timeframe: {timeframe.start} → {timeframe.end} ({timeframe.days} days)",
        f"Units: {request.units.title()}",
        f"Metrics: {metrics}",
        f"Dataset source: {payload.dataset.source}",
        f"Generated: {generated_at}",
    ]
    return lines


def _build_table(payload: WeatherReportPayload) -> Table:
    headers = ["Date", "Max temp", "Min temp", "Precip. prob."]
    units_suffix = "°C" if payload.request.units == "metric" else "°F"
    table_data: List[List[str]] = [headers]
    for row in payload.dataset.data:
        table_data.append(
            [
                row.date.isoformat(),
                _format_float(row.temperature_max, units_suffix),
                _format_float(row.temperature_min, units_suffix),
                _format_float(row.precipitation_probability, "%"),
            ]
        )

    table = Table(table_data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1faee")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1d3557")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#edf2f4")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ]
        )
    )
    return table


def render_pdf(payload: WeatherReportPayload, context: RequestContext | None = None) -> bytes:
    location_name = payload.request.location.name
    if context:
        context.info(
            logger,
            "rendering weather report pdf",
            event="pdf.render_start",
            location=location_name,
        )
    else:
        logger.info("rendering weather report pdf", extra={"location": location_name})

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=36,
        leftMargin=36,
        topMargin=48,
        bottomMargin=36,
        title=f"Weather report - {location_name}",
        author="Weather Agent POC",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Metadata", parent=styles["Normal"], leading=14))

    story: List[object] = []
    story.append(Paragraph("Weather report", styles["Title"]))
    for line in _metadata_lines(payload):
        story.append(Paragraph(line, styles["Metadata"]))
    story.append(Spacer(1, 18))

    story.append(Paragraph(payload.narrative.title, styles["Heading2"]))
    story.append(Paragraph(payload.narrative.summary, styles["BodyText"]))
    story.append(Spacer(1, 18))

    story.append(Paragraph("Daily metrics", styles["Heading3"]))
    story.append(_build_table(payload))

    try:
        doc.build(story)
        pdf_bytes = buffer.getvalue()
    except Exception:
        if context:
            context.exception(logger, "pdf render failed", event="pdf.render_failed", location=location_name)
        else:
            logger.exception("pdf render failed", extra={"location": location_name})
        raise
    finally:
        buffer.close()

    if context:
        context.info(
            logger,
            "pdf render complete",
            event="pdf.render_success",
            location=location_name,
            bytes=len(pdf_bytes),
        )
    else:
        logger.info("pdf render complete", extra={"location": location_name, "bytes": len(pdf_bytes)})
    return pdf_bytes
