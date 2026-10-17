"""Investigation report PDF (ReportLab).

The report separates four kinds of content so readers cannot confuse them:
  1. Observed facts       - audit events and consent records, verbatim.
  2. System indicators    - output of documented detection rules.
  3. Investigator notes   - notes and findings written by people.
  4. Conclusions          - investigator conclusions, explicitly labelled.

Output is deterministic for identical inputs and generation time
(``invariant=1`` fixes the PDF document ID and creation date).
No credentials, keys, ciphertext or plaintext record content is included.
"""

import io
from collections import Counter
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PROJECT_TITLE = "ConsentGuard – Privacy-Centric User Consent and Data Access Management System"
INK = colors.HexColor("#1f2937")
ACCENT = colors.HexColor("#1d4ed8")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d1d5db")
HEAD_BG = colors.HexColor("#e8eefc")

LIMITATIONS = [
    "The audit trail is a local SHA-256 hash chain. It detects modification, deletion, insertion and reordering "
    "of stored events, but an actor with full control of the database and application could rewrite the entire "
    "chain. Compare the head hash printed below with independently stored copies to detect that.",
    "Events record what the application observed. They do not establish intent; a denied request may be caused "
    "by misconfiguration or user error.",
    "Detection rules are simple thresholds over linked evidence and can produce false positives and false negatives.",
    "This report covers only events explicitly linked to the case and consent records those events reference.",
    "All data in this demonstration system is synthetic.",
]


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=15, leading=19, textColor=INK, alignment=TA_CENTER),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=11, textColor=ACCENT, alignment=TA_CENTER,
                                   spaceAfter=2),
        "meta": ParagraphStyle("m", parent=base["Normal"], fontSize=8.5, textColor=MUTED, alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", parent=base["Heading2"], fontSize=12.5, textColor=ACCENT, spaceBefore=10,
                             spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base["Heading3"], fontSize=10.5, textColor=INK, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9, leading=12, textColor=INK),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=7.2, leading=9, textColor=INK),
        "label": ParagraphStyle("l", parent=base["Normal"], fontSize=8, leading=10, textColor=MUTED),
        "note": ParagraphStyle("n", parent=base["Normal"], fontSize=9, leading=12, textColor=INK, leftIndent=6,
                               borderPadding=4),
    }


def _p(text, style):
    return Paragraph(escape("" if text is None else str(text)).replace("\n", "<br/>"), style)


def _table(rows, widths, style_small, header=True):
    data = [[_p(c, style_small) for c in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), HEAD_BG))
    table.setStyle(TableStyle(commands))
    return table


def _kv(rows, s):
    return _table([[k, v] for k, v in rows], [45 * mm, 125 * mm], s["body"], header=False)


def _person(people, user_id):
    if user_id is None:
        return "-"
    p = people.get(user_id)
    return f"#{user_id} {p['username']} ({p['role']})" if p else f"#{user_id}"


def build_case_report(*, case, events, consents, indicators, thresholds, integrity, notes, people,
                      generated_at, generated_by):
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Investigation report {case.case_number}", author="ConsentGuard", subject=PROJECT_TITLE,
        creator="ConsentGuard", invariant=1,
    )

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9 * mm, f"{case.case_number} – generated {generated_at} – synthetic demo data")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    story = [
        _p(PROJECT_TITLE, s["title"]),
        _p("Digital-Forensics Investigation Report", s["subtitle"]),
        _p(f"Generated {generated_at} (UTC) by {_person(people, generated_by)}", s["meta"]),
        Spacer(1, 6 * mm),
    ]

    # 1. Case overview
    times = [e.timestamp for e in events]
    scope_from = case.scope_start.strftime("%Y-%m-%dT%H:%M:%SZ") if case.scope_start else (min(times) if times else "-")
    scope_to = case.scope_end.strftime("%Y-%m-%dT%H:%M:%SZ") if case.scope_end else (max(times) if times else "-")
    story += [_p("1. Case overview", s["h1"]), _kv([
        ("Case identifier", case.case_number),
        ("Title", case.title),
        ("Status", case.status),
        ("Lead investigator", _person(people, case.investigator_id)),
        ("Opened", case.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("Closed", case.closed_at.strftime("%Y-%m-%dT%H:%M:%SZ") if case.closed_at else "-"),
        ("Description", case.description or "-"),
    ], s)]

    # 2. Scope and method
    story += [_p("2. Investigation scope and method", s["h1"]), _kv([
        ("Time range examined", f"{scope_from}  to  {scope_to}"),
        ("Evidence items", f"{len(events)} audit events linked to the case"),
        ("Consent records", f"{len(consents)} consent(s) referenced by the evidence"),
        ("Detection thresholds", ", ".join(f"{k}={v}" for k, v in sorted(thresholds.items()))),
        ("Method", "Events were selected by the investigator, verified against the audit hash chain, ordered by "
                   "UTC timestamp and evaluated with the documented detection rules R1-R7."),
    ], s)]

    # 3. Observed facts: summary
    story.append(_p("3. Observed facts", s["h1"]))
    story.append(_p("The following sections reproduce recorded events and consent records without interpretation.",
                    s["label"]))
    story.append(_p("3.1 Summary of observed events", s["h2"]))
    if events:
        counts = Counter((e.event_type, e.outcome) for e in events)
        rows = [["Event type", "Outcome", "Count"]] + [[t, o, str(n)] for (t, o), n in sorted(counts.items())]
        story.append(_table(rows, [80 * mm, 50 * mm, 40 * mm], s["small"]))
    else:
        story.append(_p("No events are linked to this case.", s["body"]))

    # 3.2 Timeline
    story.append(_p("3.2 Chronological timeline", s["h2"]))
    if events:
        rows = [["UTC timestamp", "Seq / Event ID", "Event", "Actor", "Resource", "Outcome / reason", "Consent"]]
        for e in events:
            details = e.details
            resource = f"{e.resource_type or '-'}:{e.resource_id or '-'}"
            if details.get("purpose"):
                resource += f"\npurpose={details['purpose']}"
            if details.get("category"):
                resource += f"\ncategory={details['category']}"
            rows.append([e.timestamp, f"#{e.seq}\n{e.event_id}", e.event_type, _person(people, e.actor_id),
                         resource, f"{e.outcome}\n{e.reason_code or ''}", f"#{e.consent_id}" if e.consent_id else "-"])
        story.append(_table(rows, [27 * mm, 33 * mm, 25 * mm, 24 * mm, 27 * mm, 22 * mm, 13 * mm], s["small"]))

    # 3.3 Consents
    story.append(_p("3.3 Associated consent records and history", s["h2"]))
    if consents:
        for c in consents:
            hist = [["Version", "Change", "Status", "Categories", "Expires", "Changed at", "By"]]
            for v in c.versions:
                hist.append([str(v.version), v.change_type, v.status, ", ".join(v.categories),
                             v.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ") if v.expires_at else "-",
                             v.changed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "system" if v.changed_by is None else _person(people, v.changed_by)])
            story.append(KeepTogether([
                _p(f"Consent #{c.id}: {_person(people, c.subject_id)} → {_person(people, c.recipient_id)}; "
                   f"purpose {c.purpose}; current status {c.status}", s["body"]),
                Spacer(1, 1.5 * mm),
                _table(hist, [14 * mm, 18 * mm, 18 * mm, 34 * mm, 28 * mm, 28 * mm, 30 * mm], s["small"]),
                Spacer(1, 3 * mm),
            ]))
    else:
        story.append(_p("No consent records are referenced by the linked events.", s["body"]))

    # 4. Indicators
    story.append(_p("4. System-generated indicators", s["h1"]))
    story.append(_p("Indicators are produced by documented rules. They are leads for assessment, not proof of "
                    "malicious activity.", s["label"]))
    if indicators:
        for ind in indicators:
            story.append(KeepTogether([
                _p(f"[{ind['rule_id']} {ind['rule_code']}] {ind['title']} – severity {ind['severity']}", s["h2"]),
                _p(ind["explanation"], s["body"]),
                _p(f"Observed from {ind['first_seen']} to {ind['last_seen']}. Supporting events: "
                   + ", ".join(f"#{seq} ({eid})" for seq, eid in zip(ind["event_seqs"], ind["event_ids"])), s["small"]),
            ]))
    else:
        story.append(_p("No detection rule was triggered by the linked events.", s["body"]))

    # 5. Integrity
    story.append(_p("5. Audit-integrity verification", s["h1"]))
    story.append(_kv([
        ("Result", "VALID – no integrity findings" if integrity["valid"] else
         f"INVALID – {len(integrity['findings'])} finding(s)"),
        ("Checked at", integrity["checked_at"]),
        ("Events in chain", str(integrity["event_count"])),
        ("Chain head", f"seq {integrity['head_seq']}  SHA-256 {integrity['head_hash']}"),
    ], s))
    story.append(_p("Record the chain head hash outside the system: a later verification that no longer contains "
                    "this head with this hash indicates the log was rewritten or truncated.", s["label"]))
    if integrity["findings"]:
        rows = [["Finding", "Seq", "Event ID", "Message"]] + [
            [f["type"], str(f["seq"]), f.get("event_id") or "-", f["message"]] for f in integrity["findings"][:50]]
        story.append(_table(rows, [35 * mm, 12 * mm, 50 * mm, 73 * mm], s["small"]))

    # 6/7. Investigator notes and conclusions
    def note_block(title, items, empty):
        block = [_p(title, s["h1"])]
        if not items:
            block.append(_p(empty, s["body"]))
        for n in items:
            block.append(_p(f"{n.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')} – {_person(people, n.author_id)} "
                            f"({n.note_type})", s["label"]))
            block.append(_p(n.content, s["note"]))
            block.append(Spacer(1, 2 * mm))
        return block

    story += note_block("6. Investigator notes and findings",
                        [n for n in notes if n.note_type in ("note", "finding")],
                        "No investigator notes or findings were recorded.")
    story += note_block("7. Investigator conclusions",
                        [n for n in notes if n.note_type == "conclusion"],
                        "No conclusion has been recorded. The case should not be treated as concluded.")

    # 8. Limitations
    story.append(_p("8. Limitations", s["h1"]))
    for item in LIMITATIONS:
        story.append(_p("• " + item, s["body"]))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
