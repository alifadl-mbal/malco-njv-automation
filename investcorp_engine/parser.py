"""Parse the Investcorp monthly statement (Trust Account page), the
per-event distribution letters, and the family-split calculation sheets.

The PDFs are machine-generated with a clean text layer, so extraction is
layout-preserving text (see pdftext.py — pure Python, no external binaries)
plus column-aware line parsing. No OCR.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

from .pdftext import pdf_text   # pure-Python, layout-preserving (no Poppler)


# --------------------------------------------------------------------------- helpers

def normalize_name(name: str) -> str:
    """Normalize a portfolio name for matching (analysis NAME is the key)."""
    n = name.lower().strip()
    for suf in (" - repp",):
        if n.endswith(suf):
            n = n[: -len(suf)]
    n = n.replace("&", " and ")          # "&" and "and" are the same name
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


AMOUNT_RE = re.compile(r"[$€£]?\s?\(?\d[\d,]*\.\d{2}\)?")


def to_float(tok: str) -> float:
    neg = "(" in tok
    v = float(re.sub(r"[^\d.]", "", tok))
    return -v if neg else v


# --------------------------------------------------------------------------- statement

@dataclass
class StatementLine:
    date: date
    txn_type: str          # Balance | Distribution | Subscription | Income Earned
    investment: str        # portfolio / "Trust Account"
    description: str
    currency: str
    debit: float = 0.0
    credit: float = 0.0
    balance: float | None = None
    raw: str = ""

    @property
    def amount(self) -> float:
        return self.credit if self.credit else self.debit


@dataclass
class Statement:
    path: Path
    month_label: str = ""
    lines: list[StatementLine] = field(default_factory=list)
    opening: dict = field(default_factory=dict)   # currency -> float
    closing: dict = field(default_factory=dict)

    def month_end(self) -> date:
        ds = [l.date for l in self.lines]
        return max(ds) if ds else date.today()


DATE_RE = re.compile(r"^\s*(\d{2}-\w{3}-\d{2})\b")


def _split_type(rest: str) -> tuple[str, str] | None:
    for t in ("Income Earned", "Distribution", "Subscription", "Balance"):
        if rest.lstrip().startswith(t):
            return t, rest.lstrip()[len(t):]
    return None


def parse_statement(path: Path) -> Statement:
    text = pdf_text(path)
    stmt = Statement(path=path)
    m = re.search(r"Investment Statement\s*-\s*(\w+ \d{4})", text)
    if m:
        stmt.month_label = m.group(1)

    idx = text.find("Trust Account Statement")
    section = text[idx:] if idx >= 0 else text

    currency = None
    header_cols: dict[str, int] = {}
    rows: list[dict] = []
    fragments: list[tuple[int, str]] = []

    for lineno, rawline in enumerate(section.splitlines()):
        line = rawline.rstrip("\n")
        cm = re.match(r"\s*(USD|EUR|GBP|SAR)\s+Transactions", line)
        if cm:
            currency = cm.group(1)
            header_cols = {}
            continue
        if currency is None:
            continue
        if "Debit" in line and "Credit" in line and "Balance" in line:
            header_cols = {
                "debit": line.index("Debit"),
                "credit": line.index("Credit"),
                "balance": line.index("Balance"),
            }
            continue

        dm = DATE_RE.match(line)
        if not dm:
            frag = line.strip()
            if frag and not AMOUNT_RE.search(frag) and len(frag) < 60 \
               and not frag.startswith(("Generated On", "Please contact", "Account(s)",
                                        "Starting Balance", "Total Debits", "Total Credits",
                                        "Ending Balance", "Reporting Fx", "1", "2", "3")) \
               and "Transactions" not in frag and "PRIVATE" not in frag:
                fragments.append((lineno, frag))
            continue

        d = datetime.strptime(dm.group(1), "%d-%b-%y").date()
        rest = line[dm.end():]
        ts = _split_type(rest)
        if ts is None:
            continue
        txn_type, tail = ts

        amounts = [(mt.group(0), mt.start() + (len(line) - len(tail)))
                   for mt in AMOUNT_RE.finditer(tail)]
        debit = credit = 0.0
        balance = None
        for tok, pos in amounts:
            val = to_float(tok)
            if header_cols:
                dists = {k: abs(pos - v) for k, v in header_cols.items()}
                col = min(dists, key=dists.get)
            else:
                col = "balance"
            if col == "debit":
                debit = val
            elif col == "credit":
                credit = val
            else:
                balance = val

        text_part = tail
        if amounts:
            text_part = tail[:AMOUNT_RE.search(tail).start()]
        text_part = re.sub(r"\s+", " ", text_part).strip()

        investment, description = "", text_part
        for anchor in ("Distribution", "Investment Capital Call", "Profit For",
                       "Bank Profit", "Opening Balance", "Closing Balance"):
            ai = text_part.find(anchor)
            if ai > 0:
                investment = text_part[:ai].strip()
                description = text_part[ai:].strip()
                break
            if ai == 0:
                investment = ""
                description = text_part
                break

        rows.append(dict(lineno=lineno, date=d, txn_type=txn_type, investment=investment,
                         description=description, currency=currency,
                         debit=debit, credit=credit, balance=balance, raw=line.strip()))

    # merge wrapped-name fragments onto the adjacent dated row
    rows_by_line = {r["lineno"]: r for r in rows}
    for lineno, frag in fragments:
        below = rows_by_line.get(lineno + 1)
        above = rows_by_line.get(lineno - 1)
        txn = ("Distribution", "Subscription")
        if below is not None and below["txn_type"] in txn and not below["investment"]:
            below["investment"] = frag
        elif above is not None and above["txn_type"] in txn:
            above["investment"] = f"{above['investment']} {frag}".strip()
        elif below is not None and below["txn_type"] in txn:
            below["investment"] = f"{frag} {below['investment']}".strip()

    for r in rows:
        txn_type, description = r["txn_type"], r["description"]
        if txn_type == "Balance":
            if "Opening" in description and r["balance"] is not None:
                stmt.opening[r["currency"]] = r["balance"]
            if "Closing" in description and r["balance"] is not None:
                stmt.closing[r["currency"]] = r["balance"]
            continue
        investment = r["investment"]
        if txn_type == "Income Earned":
            investment = investment or "Trust Account"
        stmt.lines.append(StatementLine(
            date=r["date"], txn_type=txn_type, investment=investment,
            description=description, currency=r["currency"],
            debit=r["debit"], credit=r["credit"], balance=r["balance"], raw=r["raw"]))
    return stmt


# --------------------------------------------------------------------------- letters

@dataclass
class Letter:
    path: Path
    portfolio: str
    letter_date: date | None
    dividends: float = 0.0
    roc: float = 0.0
    gain: float = 0.0
    total: float = 0.0
    investment_amount: float = 0.0   # Exhibit A "Investment Amount" = split basis

    @property
    def norm(self) -> str:
        return normalize_name(self.portfolio)


def _first_amount(line: str) -> float | None:
    m = AMOUNT_RE.search(line)
    return to_float(m.group(0)) if m else None


def parse_letter(path: Path) -> Letter | None:
    text = pdf_text(path)
    name = None
    m = re.search(r"DISTRIBUTION PROCEEDS FROM\s*\n\s*(.+?)\s*\n", text)
    if m:
        name = m.group(1).strip()
    if not name or "As of" in name:
        m = re.search(r"Subject:\s*(.+?)(?:\s*-\s*)?Investment Distribution", text)
        if m:
            name = m.group(1).strip().rstrip("-").strip()
    if not name:
        return None

    dm = re.search(r"^\s*(\w+ \d{1,2}, \d{4})", text, re.M)
    ldate = None
    if dm:
        try:
            ldate = datetime.strptime(dm.group(1), "%B %d, %Y").date()
        except ValueError:
            pass

    letter = Letter(path=path, portfolio=name, letter_date=ldate)
    block = text
    bi = text.find("Distribution Summary")
    if bi >= 0:
        block = text[bi: bi + 1500]
    for label, attr in (("Dividends", "dividends"),
                        (r"Return of Capital", "roc"),
                        (r"Capital Gain", "gain"),
                        (r"Total Distribution", "total")):
        lm = re.search(label + r"[^\n]*", block)
        if lm:
            v = _first_amount(lm.group(0))
            if v is not None:
                setattr(letter, attr, v)
    if not letter.total:
        letter.total = round(letter.dividends + letter.roc + letter.gain, 2)

    # Exhibit A "Investment Amount" — the ORIGINAL investment, which is the
    # basis for the family split (verified vs posted July NJVs).
    am = re.search(r"Investment Amount[^\n]*", text)
    if am:
        v = _first_amount(am.group(0))
        if v:
            letter.investment_amount = v
    return letter


def parse_letters(folder, exclude: Path | None = None) -> list[Letter]:
    """Letters from a folder, or from an explicit list of PDF paths."""
    letters = []
    paths = sorted(folder.glob("*.pdf")) if isinstance(folder, Path) else list(folder)
    for p in paths:
        if exclude is not None and p.resolve() == Path(exclude).resolve():
            continue
        try:
            lt = parse_letter(p)
        except Exception:
            lt = None
        if lt and (lt.total or lt.dividends or lt.roc or lt.gain):
            letters.append(lt)
    return letters


def find_statement(folder: Path) -> Path:
    for p in sorted(folder.glob("*.pdf")):
        if "statement" in p.name.lower():
            return p
    raise FileNotFoundError("No 'Investment Statement' PDF found in input folder")


# --------------------------------------------------------------------------- split sheets

@dataclass
class SplitMember:
    code: str
    name: str
    inv_usd: float
    sheet_div_fc: float = 0.0
    sheet_div_aed: float = 0.0


_NOISE_TOKENS = {"portfolio", "the", "of", "and", "&", "investment", "investments",
                 "distribution", "calculation", "repp", "llc", "ltd", "limited"}


@dataclass
class SplitSheet:
    path: Path
    portfolio: str
    dividend_fc: float | None
    total_investment: float           # 0.0 when the sheet does not state it
    members: list[SplitMember] = field(default_factory=list)
    basis_source: str = "sheet"       # "sheet" | "filename-only sheet" | "members master …"
    code: str = ""                    # Orion analysis code, when known

    @property
    def norm(self) -> str:
        return normalize_name(self.portfolio)

    @property
    def portfolio_tokens(self) -> set[str]:
        return {t for t in normalize_name(self.portfolio).split()
                if t not in _NOISE_TOKENS}


def parse_split_sheet(path: Path) -> SplitSheet | None:
    """Parse a family-split calculation workbook.

    Two layouts are supported, both keyed on rows whose first cell is a CM code:
      * full  — code | name | inv(AED) | inv(USD) | div(FC) | div(AED),
                plus a "Dividend Received" / "Total Investment" header block
      * short — code | name | investment(USD)   (the current format: no
                portfolio, no dividend, no total; those come from the letter
                and the statement, which is where they are authoritative)
    """
    try:
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_path(str(path))
    except Exception:
        return None

    for sheet_name in wb.sheet_names:
        rows = wb.get_sheet_by_name(sheet_name).to_python(skip_empty_area=False)
        member_rows = [r for r in rows
                       if r and isinstance(r[0], str)
                       and re.fullmatch(r"CM\d{4}", str(r[0]).strip())]
        if not member_rows:
            continue

        width = max((len(r) for r in member_rows), default=0)
        numeric_cols = [c for c in range(2, width)
                        if any(isinstance(r[c], (int, float)) for r in member_rows
                               if len(r) > c)]
        if not numeric_cols:
            continue
        # full layout: inv(AED), inv(USD), div(FC), div(AED) -> USD is col 3
        # short layout: a single numeric column -> that is the investment
        inv_col = 3 if len(numeric_cols) >= 4 else numeric_cols[0]
        div_fc_col = 4 if len(numeric_cols) >= 4 else None
        div_aed_col = 5 if len(numeric_cols) >= 4 else None

        portfolio, dividend, total_inv = None, None, None
        for r in rows:
            texts = [c for c in r if isinstance(c, str)]
            nums = [c for c in r if isinstance(c, (int, float))]
            joined = " ".join(texts)
            if portfolio is None:
                for t in texts:
                    if "Portfolio" in t and not t.strip().startswith(("Dividend", "Total")):
                        portfolio = t.strip()
                        break
            if "Dividend Received" in joined and nums:
                dividend = float(nums[0])
            if "Total Investment" in joined and nums:
                total_inv = float(nums[0])

        def cell(r, i):
            v = r[i] if (i is not None and len(r) > i) else None
            return float(v) if isinstance(v, (int, float)) else 0.0

        members = [SplitMember(code=str(r[0]).strip(),
                               name=str(r[1] or "").strip() if len(r) > 1 else "",
                               inv_usd=cell(r, inv_col),
                               sheet_div_fc=cell(r, div_fc_col),
                               sheet_div_aed=cell(r, div_aed_col))
                   for r in member_rows]

        source = "sheet"
        if portfolio is None:
            # short layout: the portfolio is only in the file name
            stem = re.sub(r"[_\-]+", " ", path.stem)   # separators first, so \b works
            stem = re.sub(r"(?i)\b(calculation|dividend|split|copy|final|draft)\b", " ", stem)
            stem = re.sub(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
                          " ", stem)
            portfolio = re.sub(r"\s+", " ", stem).strip()
            source = "filename-only sheet"

        return SplitSheet(path=path, portfolio=portfolio, dividend_fc=dividend,
                          total_investment=float(total_inv or 0.0),
                          members=members, basis_source=source)
    return None


def parse_split_sheets(folder: Path) -> list[SplitSheet]:
    sheets = []
    for p in sorted(list(folder.glob("*.xlsx")) + list(folder.glob("*.xls"))):
        s = parse_split_sheet(p)
        if s and s.members:
            sheets.append(s)
    return sheets


def match_split_sheet(sheets: list[SplitSheet], portfolio: str) -> SplitSheet | None:
    """Find the split sheet belonging to a statement portfolio.

    Exact normalized match first; otherwise the sheet whose distinctive tokens
    are contained in (or contain) the portfolio's tokens — this handles a
    filename-derived name such as "2019 US Industrial Logistics" against the
    statement's "2019 US Industrial & Logistics Portfolio". An ambiguous match
    is rejected so the engine never guesses between two portfolios.
    """
    target_norm = normalize_name(portfolio)
    from .analysis import code_for          # local import: analysis imports parser
    target_code = code_for(portfolio)
    if target_code:
        by_code = [s for s in sheets if s.code and s.code == target_code]
        if len(by_code) == 1:
            return by_code[0]
        if len(by_code) > 1:
            return None
    for s in sheets:
        if s.norm == target_norm:
            return s

    target_tokens = {t for t in target_norm.split() if t not in _NOISE_TOKENS}
    hits = []
    for s in sheets:
        st = s.portfolio_tokens
        if st and (st <= target_tokens or target_tokens <= st):
            hits.append(s)
    return hits[0] if len(hits) == 1 else None
