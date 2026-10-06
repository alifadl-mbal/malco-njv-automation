"""Generate the validation report (PDF) — the accountant's audit trail.

For every proposed entry: which document each number came from, the
calculation applied, the resulting Dr/Cr lines, and the checks passed.
Ends with the exceptions needing a decision.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .booking import Entry, RunResult
from .config import FX_RATES

ACCENT = colors.HexColor("#0E7C66")
ACCENT_SOFT = colors.HexColor("#E2F0EC")
INK = colors.HexColor("#1C2B33")
INK_SOFT = colors.HexColor("#46595F")
LINE = colors.HexColor("#D8DDD8")
OK = colors.HexColor("#0A5C4C")
BAD = colors.HexColor("#9C3D2E")

_ss = getSampleStyleSheet()
S = {
    "eyebrow": ParagraphStyle("eyebrow", parent=_ss["Normal"], fontName="Helvetica-Bold",
                              fontSize=7.5, textColor=ACCENT, spaceAfter=4, leading=10),
    "title": ParagraphStyle("title", parent=_ss["Title"], fontName="Helvetica-Bold",
                            fontSize=19, textColor=INK, alignment=TA_LEFT,
                            spaceAfter=4, leading=23),
    "sub": ParagraphStyle("sub", parent=_ss["Normal"], fontSize=9, textColor=INK_SOFT,
                          leading=13, spaceAfter=10),
    "h2": ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold",
                         fontSize=12, textColor=INK, spaceBefore=14, spaceAfter=6, leading=15),
    "body": ParagraphStyle("body", parent=_ss["Normal"], fontSize=9, textColor=INK,
                           leading=13.5, spaceAfter=6),
    "small": ParagraphStyle("small", parent=_ss["Normal"], fontSize=8, textColor=INK_SOFT,
                            leading=11.5),
    "cell": ParagraphStyle("cell", parent=_ss["Normal"], fontSize=8.5, textColor=INK, leading=12),
}
S["cellb"] = ParagraphStyle("cellb", parent=S["cell"], fontName="Helvetica-Bold")
S["cellr"] = ParagraphStyle("cellr", parent=S["cell"], alignment=TA_RIGHT)
S["mono"] = ParagraphStyle("mono", parent=S["cell"], fontName="Courier", fontSize=8)
S["ok"] = ParagraphStyle("ok", parent=S["cell"], textColor=OK, fontName="Helvetica-Bold")
S["bad"] = ParagraphStyle("bad", parent=S["cell"], textColor=BAD, fontName="Helvetica-Bold")


def P(t, s="cell"):
    return Paragraph(t, S[s])


def tbl(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT))
    t.setStyle(TableStyle(style))
    return t


TYPE_LABEL = {
    "dividend": "Dividend",
    "roc_distribution": "Distribution with ROC / gain",
    "split_dividend": "Dividend with family split (Malco Capital)",
    "netting": "Capital call netting",
    "trust_profit": "Trust profit",
    "coupon": "Sukuk / bond coupon",
    "loan_interest": "Loan interest settlement",
}


def _entry_section(e: Entry, n: int):
    parts = [Paragraph(
        f"{n} · Entry {e.ref} — {e.analysis_name or 'Trust account'} "
        f"({TYPE_LABEL.get(e.entry_type, e.entry_type)}, {e.entry_date:%d-%b-%Y})", S["h2"])]

    rows = [[P("<b>Step</b>", "cellb"), P("<b>Detail</b>", "cellb")]]
    for t in e.trace:
        rows.append([P("Source / calc"), P(t)])
    for name, ok, detail in e.checks:
        rows.append([P("Check"), P(f"{name}: {detail} — {'PASS' if ok else 'FAIL'}",
                                   "ok" if ok else "bad")])
    parts.append(tbl(rows, [24 * mm, 150 * mm]))
    parts.append(Spacer(1, 3))

    erows = [[P("<b>Dr/Cr</b>", "cellb"), P("<b>Account</b>", "cellb"),
              P("<b>LC (AED)</b>", "cellb"), P("<b>FC</b>", "cellb"),
              P("<b>Narration</b>", "cellb")]]
    for l in e.lines:
        fc_txt = f"{l.fc:,.2f} {l.currency}"
        if l.info_fc:
            fc_txt += f"<br/><font size=7 color='#5C6B70'>({l.info_fc:,.2f} {l.info_ccy} info)</font>"
        erows.append([P(l.drcr), P(f"{l.main} / {l.sub} — {l.account_name}", "mono"),
                      P(f"{l.aed:,.2f}", "cellr"), P(fc_txt, "cellr"), P(l.narration)])
    parts.append(tbl(erows, [12 * mm, 74 * mm, 22 * mm, 26 * mm, 40 * mm]))
    parts.append(Paragraph(
        f"Balance: Dr {e.dr_total:,.2f} = Cr {e.cr_total:,.2f} "
        f"{'✓' if e.balanced else '— BREAK'}", S["small"]))
    parts.append(Spacer(1, 6))
    return KeepTogether(parts)


def write_validation_report(res: RunResult, out_path: Path) -> Path:
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Validation Report — {res.counterparty} {res.month_label}")
    story = []
    story.append(Paragraph("MALCO CAPITAL INVESTMENTS · STATEMENT AUTOMATION", S["eyebrow"]))
    story.append(Paragraph(f"Validation Report — {res.counterparty}, {res.month_label}", S["title"]))
    story.append(Paragraph(
        "Auto-generated audit trail for the proposed journal entries. Every figure is traced "
        "to its source document with the calculation shown, so the reviewer can approve "
        "without opening the source files.", S["sub"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT, spaceAfter=10))

    stmt = res.statement
    blockers = [x for x in res.exceptions if x.severity == "blocker"]
    warnings = [x for x in res.exceptions if x.severity == "warning"]
    all_balanced = all(e.balanced for e in res.ok_entries)
    fxs = " · ".join(f"{c} {r}" for c, r in FX_RATES.items() if c != "AED")

    summary = [
        [P("<b>Check</b>", "cellb"), P("<b>Result</b>", "cellb")],
        [P("Statement cash lines processed"),
         P(f"{len(stmt.lines)} — none skipped"
           + (f" ({len(res.no_entry)} correctly need no entry)" if res.no_entry else ""), "ok")],
        [P("Proposed journal entries generated"),
         P(f"{len(res.ok_entries)} ready to key"
           + (f" ({len(res.entries) - len(res.ok_entries)} withheld — see Exceptions)"
              if len(res.entries) != len(res.ok_entries) else ""),
           "ok" if len(res.entries) == len(res.ok_entries) else "bad")],
        [P("Every entry balances (Dr = Cr)"),
         P("Yes" if all_balanced else "NO — see entries below", "ok" if all_balanced else "bad")],
        [P("Exchange rates applied (fixed)"), P(fxs, "ok")],
        [P("Exceptions requiring a decision"),
         P("None" if not res.exceptions
           else f"{len(blockers)} blocker(s), {len(warnings)} warning(s) — see final section",
           "ok" if not res.exceptions else "bad")],
    ]
    for note in res.input_notes:
        summary.append([P("Split inputs used"), P(note)])
    story.append(Paragraph("1 · Month at a glance", S["h2"]))
    story.append(tbl(summary, [95 * mm, 79 * mm]))

    story.append(Paragraph("2 · Statement line → entry mapping", S["h2"]))
    mrows = [[P("<b>Date</b>", "cellb"), P("<b>Statement line</b>", "cellb"),
              P("<b>Curr</b>", "cellb"), P("<b>Amount</b>", "cellb"), P("<b>Entry</b>", "cellb")]]
    entry_by_line = {}
    for e in res.entries:
        for sl in e.source_lines:
            entry_by_line[id(sl)] = e
    for ln in stmt.lines:
        e = entry_by_line.get(id(ln))
        if e is None and id(ln) in res.no_entry:
            status = P(res.no_entry[id(ln)], "cell")
        elif e is None:
            status = P("withheld — see Exceptions", "bad")
        elif not e.ok:
            status = P(f"{e.ref} — withheld (failed check)", "bad")
        else:
            status = P(f"{e.ref} ({TYPE_LABEL.get(e.entry_type, '')})", "mono")
        label = f"{ln.investment} — {ln.description}" if ln.investment else ln.description
        mrows.append([P(f"{ln.date:%d-%b}"), P(label), P(ln.currency),
                      P(f"{ln.amount:,.2f}", "cellr"), status])
    story.append(tbl(mrows, [14 * mm, 78 * mm, 12 * mm, 22 * mm, 48 * mm]))

    for i, e in enumerate(res.ok_entries, start=3):
        story.append(_entry_section(e, i))

    story.append(Paragraph("Exceptions — human decision needed", S["h2"]))
    if not res.exceptions:
        story.append(Paragraph("None this month.", S["body"]))
    else:
        xrows = [[P("<b>Severity</b>", "cellb"), P("<b>Item</b>", "cellb"),
                  P("<b>Detail</b>", "cellb")]]
        for x in res.exceptions:
            xrows.append([P(x.severity.upper(), "bad" if x.severity == "blocker" else "cellb"),
                          P(x.title), P(x.detail)])
        story.append(tbl(xrows, [20 * mm, 52 * mm, 102 * mm]))

    doc.build(story)
    return out_path
