"""Render PDF artifacts from structured data using Jinja2 + ReportLab."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..schemas import WeatherReportPayload

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

_METADATA_TEMPLATE = env.get_template("weather_report.txt.j2")


def _format_float(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    text = f"{value:.1f}"
    if suffix:
        text = f"{text}{suffix}"
    return text


def _metadata_lines(payload: WeatherReportPayload) -> List[str]:
    rendered = _METADATA_TEMPLATE.render(payload=payload, generated_at=datetime.utcnow().isoformat())
    return [line.strip() for line in rendered.splitlines() if line.strip()]


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


def render_pdf(payload: WeatherReportPayload) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=36,
        leftMargin=36,
        topMargin=48,
        bottomMargin=36,
        title=f"Weather report - {payload.request.location.name}",
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

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
