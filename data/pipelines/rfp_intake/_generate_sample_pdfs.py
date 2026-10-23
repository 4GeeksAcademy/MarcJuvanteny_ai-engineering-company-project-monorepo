"""Genera los 3 PDF de muestra de `CONTEXT9.md` Sección 4 -- no existían en
este repo (mismo patrón que el resto de esta sesión: el material de
referencia del curso no llegó al monorepo del estudiante). Script de
desarrollo, corrido una vez para producir `rfp-requests/trackflow/*.pdf`
-- no es parte del pipeline en sí (no se importa desde ningún otro
módulo)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "rfp-requests" / "trackflow"
OUT_DIR.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
body = ParagraphStyle("body", parent=styles["Normal"], spaceAfter=10, leading=15)
heading = ParagraphStyle("heading", parent=styles["Heading2"], spaceBefore=14, spaceAfter=8)
title = styles["Title"]


def _build(filename: str, blocks: list[tuple[str, str]]) -> None:
    doc = SimpleDocTemplate(str(OUT_DIR / filename), pagesize=LETTER, topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    story = []
    for kind, text in blocks:
        if kind == "title":
            story.append(Paragraph(text, title))
            story.append(Spacer(1, 0.25 * inch))
        elif kind == "heading":
            story.append(Paragraph(text, heading))
        else:
            story.append(Paragraph(text, body))
    doc.build(story)


# --- trackflow-request-1.pdf: RFP formal, ModaViva (España), warehouse+reverse ---

moda_viva = [
    ("title", "Request for Proposal — Servicios de Logística"),
    (
        "body",
        "ModaViva S.L. es una marca de moda femenina con sede en Zaragoza, España, con operación "
        "de e-commerce en crecimiento en el mercado ibérico. Estamos evaluando proveedores de "
        "logística de almacenamiento y gestión de devoluciones para externalizar estas operaciones "
        "a partir del próximo trimestre.",
    ),
    ("heading", "1. Datos del solicitante"),
    ("body", "Cliente: ModaViva S.L."),
    ("body", "País de origen: España"),
    ("body", "Sector: Moda y accesorios (e-commerce)"),
    ("heading", "2. Servicios solicitados"),
    (
        "body",
        "Solicitamos una propuesta para los siguientes servicios: almacenamiento de inventario "
        "(warehousing) y gestión de devoluciones (reverse logistics). ModaViva ya cuenta con un "
        "acuerdo vigente con su propio transportista de última milla para el mercado español, por "
        "lo que NO se solicita servicio de last mile en esta propuesta.",
    ),
    ("heading", "3. Volumen estimado"),
    (
        "body",
        "El volumen estimado es de 3.200 pedidos al mes, con picos estacionales de hasta 5.000 "
        "pedidos durante las campañas de rebajas de enero y julio.",
    ),
    ("heading", "4. Devoluciones"),
    (
        "body",
        "El sector moda tiene una tasa de devolución elevada (aproximadamente 18% del volumen). "
        "Necesitamos un proceso de gestión de devoluciones ágil, con tiempos de procesamiento "
        "claros, para poder reponer inventario a la venta lo antes posible.",
    ),
    ("heading", "5. Plazo y presupuesto de referencia"),
    (
        "body",
        "Fecha límite para recibir propuestas: 15 de noviembre de 2026. Presupuesto de referencia: "
        "entre 8.000 EUR y 12.000 EUR mensuales, sujeto a los términos finales de la propuesta.",
    ),
    (
        "body",
        "Quedamos a la espera de su propuesta detallada, incluyendo costos por pallet/SKU, tiempos "
        "de onboarding, y SLA de procesamiento de devoluciones.",
    ),
]

# --- trackflow-request-2.pdf: RFP informal, Luna Cosmetics (LA), warehouse+lastmile ---

luna_cosmetics = [
    ("title", "RE: Logistics partnership inquiry"),
    (
        "body",
        "Hi TrackFlow team,",
    ),
    (
        "body",
        "Hope you're doing well! We're Luna Cosmetics, a growing skincare and beauty brand based in "
        "Los Angeles. We currently handle our own warehousing and last mile delivery in-house, but "
        "we're scaling fast and it's becoming a headache to manage ourselves.",
    ),
    (
        "body",
        "We're looking to outsource both warehousing and last mile delivery for our US operations. "
        "We're doing about 5,000 orders a month right now and growing. Could you send over some "
        "info on pricing and how onboarding would work?",
    ),
    (
        "body",
        "A few things that matter to us: we ship a lot of glass bottles so careful handling matters, "
        "and our customers expect fast delivery (most of our competitors offer 2-3 day shipping). "
        "We'd want to know what carriers you work with for the LA area and nearby states.",
    ),
    (
        "body",
        "We don't really need help with returns processing for now, we handle that ourselves with a "
        "small team.",
    ),
    (
        "body",
        "Let us know what you need from us to put together a proposal. Thanks so much!",
    ),
    ("body", "Luna Cosmetics team"),
]

# --- trackflow-request-3.pdf: inválido, pitch de tarifas de carrier ---

carrier_pitch = [
    ("title", "FastShip Carriers — Preferred Rate Partnership Proposal"),
    (
        "body",
        "Dear TrackFlow Partnerships Team,",
    ),
    (
        "body",
        "FastShip Carriers is a regional last-mile delivery network currently expanding our footprint "
        "across the West Coast and Southwest United States. We are reaching out to introduce our "
        "services and explore a preferred-rate partnership with TrackFlow.",
    ),
    (
        "heading", "Why partner with FastShip Carriers"),
    (
        "body",
        "We offer highly competitive per-package rates for last-mile delivery, with volume-based "
        "discounts starting at 500 packages per month. Our network covers Los Angeles, San Diego, "
        "Phoenix, and Las Vegas, with same-day and next-day delivery options.",
    ),
    (
        "heading", "Proposed rate structure"),
    (
        "body",
        "We would like to offer TrackFlow our standard carrier rate card, with preferred pricing "
        "tiers based on your shipment volume commitments. We're confident our rates are more "
        "competitive than your current last-mile providers.",
    ),
    (
        "body",
        "We'd love to schedule a call to discuss how FastShip Carriers could become one of your "
        "preferred last-mile partners. Please let us know your availability.",
    ),
    ("body", "Best regards,"),
    ("body", "Business Development, FastShip Carriers"),
]


if __name__ == "__main__":
    _build("trackflow-request-1.pdf", moda_viva)
    _build("trackflow-request-2.pdf", luna_cosmetics)
    _build("trackflow-request-3.pdf", carrier_pitch)
    print(f"PDFs generados en {OUT_DIR}")
