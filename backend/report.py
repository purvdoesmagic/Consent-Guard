"""Creates the PDF report for an investigation case (using ReportLab)."""

import io
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


IST = timedelta(hours=5, minutes=30)  # Indian Standard Time = UTC + 5:30


def ist(value):
    """Turn a UTC time (datetime or ISO text) into readable Indian time."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value[:19])
    return (value + IST).strftime("%d %b %Y, %I:%M %p")


def make_pdf(case, chain, names, investigator):
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)

    def text(value, style=styles["BodyText"]):
        return Paragraph(escape(str(value or "")), style)

    story = [
        Paragraph(f"ConsentGuard investigation report: case #{case.id}", styles["Title"]),
        text(f"Title: {case.title}"),
        text(f"Investigator: {investigator}"),
        text(f"Opened: {ist(case.created_at)} IST"),
        Spacer(1, 10),
        Paragraph("Description", styles["Heading2"]),
        text(case.description or "-"),
        Paragraph("Log entries linked to this case", styles["Heading2"]),
    ]

    rows = [["#", "Time (IST)", "Who", "Action", "Result", "Reason"]]
    for e in case.logs:
        rows.append([e.id, ist(e.time), names.get(e.user_id, "-"), e.action, e.result, e.reason or ""])
    if len(rows) == 1:
        rows.append(["-", "No entries linked yet", "", "", "", ""])
    table = Table([[text(c, small) for c in row] for row in rows], colWidths=[25, 95, 70, 75, 50, 140], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3ECF0")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [table, Spacer(1, 10)]

    story += [
        Paragraph("Investigator notes and conclusion", styles["Heading2"]),
        text(case.notes or "-"),
        Paragraph("Log integrity check", styles["Heading2"]),
        text(f"Result: {'VALID - no changes found' if chain['valid'] else 'INVALID - the log was changed'}"),
        text(f"Entries checked: {chain['count']}"),
        text(f"Last hash (keep this as a reference): {chain['last_hash']}", small),
        Spacer(1, 10),
        text("Note: alerts are leads, not proof. This report shows only what the system recorded.", small),
    ]

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, title=f"Case {case.id} report").build(story)
    return buffer.getvalue()
