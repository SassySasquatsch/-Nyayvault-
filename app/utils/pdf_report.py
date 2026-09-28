"""Generates a real PDF chain-of-custody report for a case, using reportlab.

This is one of the few frontend "buttons" that gets a genuinely functional
backend implementation end-to-end: click Generate Report -> server builds an
actual PDF from live DB data -> frontend downloads it.
"""
import io
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import settings
from app.models import Case


def build_case_report(case: Case) -> Path:
    out_path = settings.REPORTS_DIR / f"{case.number}.pdf"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "NVTitle", parent=styles["Title"], fontSize=18, spaceAfter=4
    )
    meta_style = ParagraphStyle(
        "NVMeta", parent=styles["Normal"], textColor=colors.HexColor("#555555")
    )

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"NyayVault Evidence Report — {case.number}",
    )

    story = [
        Paragraph("NyayVault — Digital Evidence Report", title_style),
        Paragraph(f"{case.number} &mdash; {case.title}", styles["Heading2"]),
        Paragraph(
            f"Case status: <b>{case.status.value.upper()}</b> &nbsp;|&nbsp; "
            f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M:%S')}",
            meta_style,
        ),
        Spacer(1, 10 * mm),
        Paragraph("Evidence Items", styles["Heading3"]),
    ]

    table_data = [["Name", "Type", "Uploader", "Uploaded", "Status", "SHA-256"]]
    for d in case.documents:
        table_data.append(
            [
                Paragraph(d.name, styles["Normal"]),
                d.type.value,
                d.uploader.full_name if d.uploader else "—",
                d.uploaded_at.strftime("%d %b %Y %H:%M") if d.uploaded_at else "—",
                d.status.value,
                Paragraph(d.hash_sha256, styles["Code"] if "Code" in styles else styles["Normal"]),
            ]
        )

    if len(table_data) == 1:
        story.append(Paragraph("No evidence has been uploaded to this case yet.", styles["Normal"]))
    else:
        tbl = Table(table_data, repeatRows=1, colWidths=[95, 40, 65, 60, 50, 160])
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12233d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6f8")]),
                ]
            )
        )
        story.append(tbl)

    story.append(Spacer(1, 10 * mm))
    story.append(
        Paragraph(
            "This report is system-generated from the chain-of-custody records held "
            "by NyayVault at the time of generation. Hash values reflect the state "
            "recorded at upload and/or the most recent integrity check.",
            meta_style,
        )
    )

    doc.build(story)
    return out_path


def _make_overlay(page_width: float, page_height: float, lines: list[str]) -> "canvas.Canvas":
    """Builds a single-page reportlab canvas holding a translucent, tiled
    watermark: one diagonal repeat centred on the page plus a small
    single-line footer stamp, so the mark survives cropping/screenshots of
    any one region of the page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    c.saveState()
    c.setFillColor(colors.HexColor("#b00020"))
    c.setFillAlpha(0.14)
    c.translate(page_width / 2, page_height / 2)
    c.rotate(45)
    c.setFont("Helvetica-Bold", 13)
    line_gap = 26
    total_h = line_gap * len(lines)
    for i, line in enumerate(lines):
        y = total_h / 2 - i * line_gap
        c.drawCentredString(0, y, line)
    c.restoreState()

    # Small, less obtrusive footer repeat so the mark is legible even if the
    # diagonal stamp is cropped out of a screenshot.
    c.saveState()
    c.setFillColor(colors.HexColor("#b00020"))
    c.setFillAlpha(0.55)
    c.setFont("Helvetica", 6.5)
    c.drawString(10, 8, " | ".join(lines))
    c.restoreState()

    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def stamp_pdf_watermark(source_path: Path, watermark_lines: list[str]) -> io.BytesIO:
    """Returns an in-memory copy of the PDF at `source_path` with a
    translucent security watermark baked into every page.

    The stored evidence file on disk is opened read-only and never touched --
    this only ever writes to the BytesIO buffer that's returned, which the
    caller streams straight to the client. Callers are responsible for
    building `watermark_lines` from the *current request's* user/IP/time so
    every download carries a distinct, traceable stamp.
    """
    reader = PdfReader(str(source_path))
    writer = PdfWriter()

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_buf = _make_overlay(width, height, watermark_lines)
        overlay_reader = PdfReader(overlay_buf)
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    # Carry over document metadata but flag that this copy is a stamped
    # render, distinct from the immutable stored original.
    try:
        if reader.metadata:
            writer.add_metadata(reader.metadata)
    except Exception:
        pass
    writer.add_metadata({"/NyayVaultWatermarked": "true"})

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out
