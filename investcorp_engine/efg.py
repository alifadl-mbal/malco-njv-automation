"""EFG Bank — account statement parser and booking rules.

Statement: "Account Statement Report" PDF from EFG (one page per month so far),
account 5089261210, USD. Columns: Value date | Date | Description | ISIN |
Debit | Credit | Balance. Newest line first; long descriptions wrap onto the
lines above and below the dated row.

Booking rules, reverse-engineered from the posted NJVs (ZF_F_T_DETAIL_BI):

  COUPONS ... with an ISIN, credit        NJV-2026040010 / 040011
      Dr 10269/XC0002 cash                 USD, Anly1 = ISIN
      Cr 30711/MCI0002 dividend (EFG)      USD, Anly1 = ISIN
  MISCELLANEOUS DEBITS ... SETTLEMENT     NJV-2026040009 / 060003
      Dr 40840 financial expenses          USD, no Anly1
      Cr 10269/XC0002 cash                 USD, no Anly1
  PRINCIPAL PAYMENT (debit) + PRINCIPAL (credit), same day, same amount
      loan rollover — nets to zero, no entry (not in the posted GL)

Narration = the statement description, verbatim. Anything else — a coupon on a
sukuk Capital M part-owns, a security sale or purchase, an unpaired principal —
is withheld as an exception.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from .analysis import name_for_code
from .booking import Entry, EntryLine, ExceptionItem, RunResult, r2
from .config import FX_RATES
from . import holdings as _holdings
from .holdings import capital_m_share, is_pending
from .parser import Statement, StatementLine

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
AMT_RE = re.compile(r"^-?[\d,]+\.\d{2}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def is_efg_statement(path: Path) -> bool:
    try:
        with pdfplumber.open(str(path)) as pdf:
            t = pdf.pages[0].extract_text() or ""
    except Exception:
        return False
    return "Account Statement Report" in t and "IBAN" in t


def _amount(s: str) -> float:
    return float(s.replace(",", ""))


def _lines(page):
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False,
                               x_tolerance=1.5, y_tolerance=2.0)
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= 2.5:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def parse_efg_statement(path: Path) -> Statement:
    stmt = Statement(path=path)
    currency = "USD"
    start = end = None
    lines = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            lines.extend(_lines(page))

    # header facts and column positions
    cols = {}
    for ln in lines:
        text = " ".join(w["text"] for w in ln)
        m = re.search(r"IBAN .*\((\w{3})\)", text)
        if m:
            currency = m.group(1)
        m = re.search(r"Start:\s*(\d{2}/\d{2}/\d{4})", text)
        if m:
            start = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        m = re.search(r"End:\s*(\d{2}/\d{2}/\d{4})", text)
        if m:
            end = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        names = [w["text"] for w in ln]
        if "Description" in names and "Debit" in names and "Credit" in names:
            for w in ln:
                cols.setdefault(w["text"], w)
    if not cols:
        raise ValueError("EFG statement: column header row (Description / Debit / Credit) not found")
    x_desc = cols["Description"]["x0"] - 3
    x_isin = cols["ISIN"]["x0"] - 3
    right = {"debit": cols["Debit"]["x1"], "credit": cols["Credit"]["x1"],
             "balance": cols["(USD)"]["x1"] if "(USD)" in cols else cols["Balance"]["x1"]}
    head_top = cols["Description"]["top"]

    dated, loose = [], []
    for ln in lines:
        top = ln[0]["top"]
        if top <= head_top + 2:
            continue
        text = " ".join(w["text"] for w in ln)
        if "balance on" in text:
            amt = [w for w in ln if AMT_RE.match(w["text"])]
            if amt:
                v = _amount(amt[-1]["text"])
                if "Closing" in text:
                    stmt.closing[currency] = v
                elif "Initial" in text or "Opening" in text:
                    stmt.opening[currency] = v
            continue
        if text.startswith("All figures") or "Bank accepts no liability" in text \
                or "document or its contents" in text:
            continue
        dates = [w for w in ln if w["x0"] < x_desc and DATE_RE.match(w["text"])]
        desc = " ".join(w["text"] for w in ln if x_desc <= w["x0"] < x_isin)
        if dates:
            isin = next((w["text"] for w in ln if x_isin <= w["x0"] < right["debit"] - 60
                         and ISIN_RE.match(w["text"])), "")
            amts = {}
            for w in ln:
                if w["x0"] >= x_isin and AMT_RE.match(w["text"]):
                    col = min(right, key=lambda k: abs(right[k] - w["x1"]))
                    amts[col] = _amount(w["text"])
            dated.append({"top": top, "date": dates[-1]["text"], "value_date": dates[0]["text"],
                          "desc": [desc] if desc else [], "isin": isin, **amts})
        elif desc:
            loose.append({"top": top, "text": desc})

    # wrapped descriptions: each loose line belongs to the nearest dated row
    for fr in loose:
        if not dated:
            break
        row = min(dated, key=lambda d: abs(d["top"] - fr["top"]))
        if fr["top"] < row["top"]:
            row.setdefault("pre", []).append(fr)
        else:
            row.setdefault("post", []).append(fr)
    for d in dated:
        parts = [f["text"] for f in sorted(d.get("pre", []), key=lambda f: f["top"])]
        parts += d["desc"]
        parts += [f["text"] for f in sorted(d.get("post", []), key=lambda f: f["top"])]
        d["description"] = " ".join(parts).strip()

    for d in sorted(dated, key=lambda d: -d["top"]):      # statement is newest-first
        dt = datetime.strptime(d["date"], "%d/%m/%Y").date()
        stmt.lines.append(StatementLine(
            date=dt, txn_type=_txn_type(d["description"], d.get("credit"), d.get("debit")),
            investment=d["isin"], description=d["description"], currency=currency,
            debit=d.get("debit", 0.0) or 0.0, credit=d.get("credit", 0.0) or 0.0,
            balance=d.get("balance"), raw=d["description"]))
    ref = start or (stmt.lines[0].date if stmt.lines else date.today())
    stmt.month_label = f"{ref:%B %Y}"
    stmt.period = (start, end)
    return stmt


def _txn_type(desc: str, credit, debit) -> str:
    u = desc.upper()
    if u.startswith("COUPONS") and credit:
        return "Coupon"
    if u.startswith("MISCELLANEOUS DEBITS") and "SETTLEMENT" in u and debit:
        return "Loan interest"
    if u.startswith("PRINCIPAL PAYMENT") and debit:
        return "Principal out"
    if u.startswith("PRINCIPAL") and credit:
        return "Principal in"
    return "Other"


def build_efg_entries(stmt: Statement) -> RunResult:
    res = RunResult(month_label=stmt.month_label, statement=stmt, counterparty="EFG")
    rate = FX_RATES[stmt.lines[0].currency] if stmt.lines else FX_RATES["USD"]
    seq = 0

    def new_entry(**kw) -> Entry:
        nonlocal seq
        seq += 1
        e = Entry(ref=f"E{seq:02d}", **kw)
        res.entries.append(e)
        return e

    # principal rollovers: pair an outflow with an inflow of the same amount, same day
    outs = [l for l in stmt.lines if l.txn_type == "Principal out"]
    ins = [l for l in stmt.lines if l.txn_type == "Principal in"]
    for o in outs:
        match = next((i for i in ins if i.date == o.date and abs(i.credit - o.debit) < 0.005), None)
        if match:
            ins.remove(match)
            why = (f"No entry — loan rollover: principal repaid and redrawn on "
                   f"{o.date:%d-%b}, {o.currency} {o.debit:,.2f} each way")
            res.no_entry[id(o)] = why
            res.no_entry[id(match)] = why
        else:
            res.exceptions.append(ExceptionItem(
                "blocker", f"Unpaired principal payment {o.date:%d-%b-%y}",
                f"{o.description}: {o.currency} {o.debit:,.2f} out with no matching "
                f"principal in on the same day. Not a rollover — needs a human decision."))
    for i in ins:
        res.exceptions.append(ExceptionItem(
            "blocker", f"Unpaired principal receipt {i.date:%d-%b-%y}",
            f"{i.description}: {i.currency} {i.credit:,.2f} in with no matching principal "
            f"payment on the same day. Not a rollover — needs a human decision."))

    for ln in stmt.lines:
        aed = r2(ln.amount * FX_RATES[ln.currency])
        if ln.txn_type == "Coupon":
            name = name_for_code(ln.investment) or ""
            e = new_entry(entry_date=ln.date, entry_type="coupon",
                          analysis_name=name or ln.investment, source_lines=[ln])
            e.analysis_code = ln.investment
            e.trace.append(f"Statement {ln.date:%d-%b-%y}: {ln.description} — ISIN "
                           f"{ln.investment}, credit {ln.currency} {ln.credit:,.2f}")
            e.trace.append(f"Convert at fixed {FX_RATES[ln.currency]}: {ln.credit:,.2f} × "
                           f"{FX_RATES[ln.currency]} = AED {aed:,.2f}")
            e.checks.append(("ISIN in the analysis master", bool(name),
                             name or f"{ln.investment} is not in analysis.py"))
            if not name:
                res.exceptions.append(ExceptionItem(
                    "blocker", f"Unknown ISIN {ln.investment}",
                    f"Coupon {ln.currency} {ln.credit:,.2f} on {ln.date:%d-%b-%y}: the ISIN is "
                    f"not in the Orion analysis master. Add it to analysis.py and run again."))
                continue
            share = capital_m_share(ln.investment)
            pending = is_pending(ln.investment)
            src = ("F-2 at 31-Dec-2025; not in the revised split — to confirm"
                   if pending else _holdings.AS_AT)
            e.checks.append(("Held 100% by Malco", share == 0,
                             f"Capital M share {share:.2%} ({src})"))
            if share:
                res.exceptions.append(ExceptionItem(
                    "blocker", f"Coupon on a Capital M holding — {name}",
                    f"Capital M holds {share:.2%} of {ln.investment} ({src}), so "
                    f"{'part' if share < 1 else 'all'} of this {ln.currency} {ln.credit:,.2f} "
                    f"coupon belongs to the family investors. How it is booked to them is not "
                    f"yet confirmed — entry withheld; key it by hand."))
                continue
            e.lines.append(EntryLine("Dr", "efg_cash", aed, ln.credit, ln.currency, ln.description))
            e.lines.append(EntryLine("Cr", "efg_income", aed, ln.credit, ln.currency, ln.description))
        elif ln.txn_type == "Loan interest":
            # display name only: Anly1 stays blank (analysis_code is never set here)
            e = new_entry(entry_date=ln.date, entry_type="loan_interest",
                          analysis_name="EFG loan — interest settlement", source_lines=[ln])
            e.trace.append(f"Statement {ln.date:%d-%b-%y}: {ln.description}, debit "
                           f"{ln.currency} {ln.debit:,.2f}")
            e.trace.append(f"Convert at fixed {FX_RATES[ln.currency]}: {ln.debit:,.2f} × "
                           f"{FX_RATES[ln.currency]} = AED {aed:,.2f}")
            e.lines.append(EntryLine("Dr", "fin_exp", aed, ln.debit, ln.currency, ln.description))
            e.lines.append(EntryLine("Cr", "efg_cash", aed, ln.debit, ln.currency, ln.description))
        elif ln.txn_type in ("Principal out", "Principal in"):
            continue
        else:
            res.exceptions.append(ExceptionItem(
                "blocker", f"Unrecognised EFG line {ln.date:%d-%b-%y}",
                f"“{ln.description}” ({ln.currency} {ln.amount:,.2f}) is not a coupon, a "
                f"loan-interest settlement or a principal rollover — the engine has no rule "
                f"for it yet. Entry withheld."))
            continue
        e.checks.append(("Entry balances Dr = Cr", e.balanced,
                         f"Dr {e.dr_total:,.2f} vs Cr {e.cr_total:,.2f}"))

    for curr, opening in stmt.opening.items():
        credits = sum(l.credit for l in stmt.lines if l.currency == curr)
        debits = sum(l.debit for l in stmt.lines if l.currency == curr)
        expected = r2(opening + credits - debits)
        closing = stmt.closing.get(curr)
        if closing is not None and abs(expected - closing) > 0.011:
            res.exceptions.append(ExceptionItem(
                "blocker", f"{curr} cash roll-forward break",
                f"Initial {opening:,.2f} + credits {credits:,.2f} - debits {debits:,.2f} = "
                f"{expected:,.2f}, but the statement closes at {closing:,.2f}. "
                f"A line may have been mis-read."))

    res.entries.sort(key=lambda e: (e.entry_date, e.ref))
    for n, e in enumerate(res.entries, start=1):   # renumber in date order
        e.ref = f"E{n:02d}"
    return res
