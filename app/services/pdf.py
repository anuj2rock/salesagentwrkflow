"""Render PDF artifacts from structured data using Jinja2 + WeasyPrint."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from ..schemas import WeatherReportPayload

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_pdf(payload: WeatherReportPayload) -> bytes:
    template = env.get_template("weather_report.html")
    html = template.render(payload=payload)
    return HTML(string=html).write_pdf()

