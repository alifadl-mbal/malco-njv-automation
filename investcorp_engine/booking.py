"""Classify statement lines and generate the proposed NJV journal entries.

Booking rules (confirmed against posted June and July 2026 NJVs):
1. Dividend distribution (income only): Dr cash / Cr dividend income.
2. Distribution with ROC and/or capital gain: Dr cash (total) /
   Cr change-in-cost (ROC part) / Cr income (dividends + gain).
   The income line absorbs any rounding residual (confirmed rule).
3. Dividend on a Malco Capital deal (split sheet supplied): ONE entry —
   Dr cash / Cr one line per family investor / Cr Capital M / Cr income.
4. Capital call netting: ONE month-end entry per investment,
   Dr Investments A/C / Cr cash, = sum of that month's subscription debits.
5. Trust profit: one entry per currency at month end, Dr cash / Cr income.
   A "Bank Profit Adjustment" debit books the reverse.

Everything that fails a check becomes an Exception and is EXCLUDED from the
upload file — the engine never drops or invents a line silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .config import (ACCOUNTS, CASH_BY_CURRENCY, FX_RATES,
                     ROUNDING_TOLERANCE, SPLIT_LINE_CURRENCY)
from .members import (CAPITAL_M_ACCOUNT, CAPITAL_M_NAME, MEMBERS_MAIN_ACCOUNT,
                      MEMBERS_MAIN_NAME, MEMBER_MASTER,
                      SPLIT_REQUIRED_PORTFOLIOS)
from .analysis import code_for, is_ambiguous
from . import holdings as _holdings
from .holdings import capital_m_share
from .parser import (Letter, SplitSheet, Statement, StatementLine,
                     match_split_sheet, normalize_name)


def r2(x: float) -> float:
    return round(x + 1e-9, 2)


@dataclass
class EntryLine:
    drcr: str                 # "Dr" | "Cr"
    account_key: str          # key into ACCOUNTS, or "" when explicit account given
    aed: float                # LC amount (what hits the ledger)
    fc: float                 # FC amount, in `currency`
    currency: str
    narration: str
    ex_main: str = ""         # explicit account (member lines)
    ex_sub: str = ""
    ex_name: str = ""
    info_fc: float = 0.0      # informational FC equivalent (AED-denominated lines)
    info_ccy: str = ""

    @property
    def main(self) -> str:
        return self.ex_main or ACCOUNTS[self.account_key][0]

    @property
    def sub(self) -> str:
        return self.ex_sub if self.ex_main else ACCOUNTS[self.account_key][1]

    @property
    def account_name(self) -> str:
        return self.ex_name or ACCOUNTS[self.account_key][2]


@dataclass
class Entry:
    ref: str                  # working reference, e.g. "E01"
    entry_date: date
    entry_type: str           # dividend | roc_distribution | split_dividend | netting | trust_profit
    analysis_name: str        # portfolio name ("" for trust profit)
    lines: list[EntryLine] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    source_lines: list[StatementLine] = field(default_factory=list)
    letter: Letter | None = None
    analysis_code: str = ""   # Orion Anly1, from the analysis master

    @property
    def dr_total(self) -> float:
        return r2(sum(l.aed for l in self.lines if l.drcr == "Dr"))

    @property
    def cr_total(self) -> float:
        return r2(sum(l.aed for l in self.lines if l.drcr == "Cr"))

    @property
    def balanced(self) -> bool:
        return abs(self.dr_total - self.cr_total) < ROUNDING_TOLERANCE

    @property
    def ok(self) -> bool:
        return self.balanced and all(ok for _, ok, _ in self.checks)


@dataclass
class ExceptionItem:
    severity: str             # "blocker" | "warning"
    title: str
    detail: str


@dataclass
class RunResult:
    month_label: str
    entries: list[Entry] = field(default_factory=list)
    exceptions: list[ExceptionItem] = field(default_factory=list)
    statement: Statement | None = None
    letters: list[Letter] = field(default_factory=list)
    split_sheets: list[SplitSheet] = field(default_factory=list)
    counterparty: str = "Investcorp"
    input_notes: list[str] = field(default_factory=list)   # what split inputs were used
    # statement lines that correctly produce no entry, id(line) -> reason
    no_entry: dict = field(default_factory=dict)

    @property
    def ok_entries(self) -> list[Entry]:
        return [e for e in self.entries if e.ok]


_SPLIT_REQUIRED = {normalize_name(p) for p in SPLIT_REQUIRED_PORTFOLIOS}


def fx(currency: str) -> float:
    return FX_RATES[currency]


def build_entries(stmt: Statement, letters: list[Letter],
                  split_sheets: list[SplitSheet] | None = None) -> RunResult:
    res = RunResult(month_label=stmt.month_label, statement=stmt, letters=letters,
                    split_sheets=list(split_sheets or []))
    letters_by_name: dict[str, Letter] = {}
    for lt in letters:
        letters_by_name.setdefault(lt.norm, lt)
    used_letters: set[str] = set()
    month_end = stmt.month_end()
    seq = 0

    def new_entry(**kw) -> Entry:
        nonlocal seq
        seq += 1
        e = Entry(ref=f"E{seq:02d}", **kw)
        res.entries.append(e)
        return e

    # ---- distributions ------------------------------------------------------
    for ln in stmt.lines:
        if ln.txn_type != "Distribution":
            continue
        rate = fx(ln.currency)
        cash_key = CASH_BY_CURRENCY.get(ln.currency)
        e = new_entry(entry_date=ln.date, entry_type="dividend",
                      analysis_name=ln.investment, source_lines=[ln])
        e.trace.append(
            f"Statement (Trust Account page), {ln.date:%d-%b-%y}: "
            f"“{ln.investment} — Distribution”, credit {ln.currency} {ln.credit:,.2f}")

        if cash_key is None:
            e.checks.append(("Cash account for currency", False,
                             f"no configured cash sub-account for {ln.currency}"))
            res.exceptions.append(ExceptionItem(
                "blocker", f"Unmapped currency {ln.currency}",
                f"Distribution {ln.investment} {ln.date}: no cash account configured."))
            continue

        lt = letters_by_name.get(normalize_name(ln.investment))
        if lt is None:
            e.checks.append(("Distribution letter found", False, "no letter in the pack"))
            res.exceptions.append(ExceptionItem(
                "blocker", f"No distribution letter for “{ln.investment}”",
                f"Statement shows {ln.currency} {ln.credit:,.2f} on {ln.date:%d-%b-%y} but no "
                f"matching letter was provided. Entry withheld pending the letter."))
            continue
        used_letters.add(lt.norm)
        e.letter = lt
        e.trace.append(
            f"Letter “{lt.path.name}”, Exhibit A: Dividends {lt.dividends:,.2f} · "
            f"ROC {lt.roc:,.2f} · Gain {lt.gain:,.2f} · Total {lt.total:,.2f}")

        match_ok = abs(lt.total - ln.credit) < 0.005
        e.checks.append(("Three-way match (letter = statement)", match_ok,
                         f"letter total {lt.total:,.2f} vs statement {ln.credit:,.2f}"))
        if not match_ok:
            res.exceptions.append(ExceptionItem(
                "blocker", f"Amount mismatch — {ln.investment}",
                f"Letter total {lt.total:,.2f} ≠ statement credit {ln.credit:,.2f} "
                f"({ln.date:%d-%b-%y}). Entry withheld."))
            continue

        cash_aed = r2(ln.credit * rate)
        # Narration follows the posted Orion convention (Aug 2026 sub-ledger):
        # dividend only -> "Dividend from X"; any ROC / gain -> "Distribution from X";
        # 100% ROC -> "Return of Capital from X". Every line of the entry carries it.
        if lt.dividends == 0 and lt.roc > 0 and lt.gain == 0:
            narr = f"Return of Capital from {ln.investment}"
        elif lt.roc > 0 or lt.gain > 0:
            narr = f"Distribution from {ln.investment}"
        else:
            narr = f"Dividend from {ln.investment}"
        e.lines.append(EntryLine("Dr", cash_key, cash_aed, ln.credit, ln.currency, narr))
        e.trace.append(f"Convert at fixed {rate}: {ln.credit:,.2f} × {rate} = AED {cash_aed:,.2f}")

        sheet = match_split_sheet(split_sheets or [], ln.investment)
        # split if the static list says so OR the Malco / Capital M table gives Capital M a share
        is_split = (normalize_name(ln.investment) in _SPLIT_REQUIRED
                    or capital_m_share(ln.investment) > 0)
        # A pure return of capital on a split holding gets the same treatment whether
        # or not a member list was supplied: the Malco / Capital M figures are exact,
        # the per-member allocation of a ROC is not yet known.
        if (is_split or sheet is not None) and lt.dividends == 0 and lt.roc > 0 \
                and capital_m_share(ln.investment) > 0:
            sheet = None
        if sheet is None and is_split:
            if lt.dividends == 0 and lt.roc > 0:
                # Pure return of capital on a split holding. Malco's share of the
                # ROC reduces cost (XC0004); the Capital M share belongs to the
                # family investors. The share comes from holdings.py (revised split).
                # Verified on NJV-2026080006: 61.00% -> change in cost
                # AED 256,968.77, 39.00% -> Capital M AED 164,291.50.
                share = capital_m_share(ln.investment)
                malco_fc = r2(lt.roc * (1 - share))
                malco_aed = r2(malco_fc * rate)
                capm_aed = r2(cash_aed - malco_aed)
                e.trace.append(
                    f"Capital M share {share:.2%} ({_holdings.AS_AT}): Malco "
                    f"{ln.currency} {malco_fc:,.2f} = AED {malco_aed:,.2f} → change in cost; "
                    f"Capital M AED {capm_aed:,.2f}")
                e.checks.append(("Capital M share of the ROC allocated to members", False,
                                 "member breakdown for a return of capital not yet confirmed"))
                res.exceptions.append(ExceptionItem(
                    "blocker", f"Return of capital on a split holding — {ln.investment}",
                    f"The {ln.date:%b %Y} distribution is 100% return of capital "
                    f"({ln.currency} {lt.roc:,.2f} = AED {cash_aed:,.2f}). Per the split table, "
                    f"Capital M holds {share:.2%} of this portfolio, so: Dr cash "
                    f"AED {cash_aed:,.2f}; Cr change in cost (Malco {1 - share:.2%}) "
                    f"AED {malco_aed:,.2f}; Cr Capital M members AED {capm_aed:,.2f}. "
                    f"The engine withholds the entry because how the Capital M part is "
                    f"allocated across the members is not yet confirmed — key it by hand "
                    f"using these three figures."))
            else:
                e.checks.append(("Split sheet present for a split deal", False,
                                 "portfolio requires a family split"))
                res.exceptions.append(ExceptionItem(
                    "blocker", f"Split sheet missing — {ln.investment}",
                    f"This portfolio is split across the family investors, but no split sheet "
                    f"was provided for {ln.date:%b %Y}. Booking it at entity level would credit "
                    f"the investors' share to income, so the entry is withheld — add the "
                    f"calculation sheet and run again."))
            continue

        if sheet is not None:
            if lt.roc > 0 or lt.gain > 0:
                e.checks.append(("Split + ROC combination", False,
                                 "split sheet on a ROC-bearing distribution — treatment unconfirmed"))
                res.exceptions.append(ExceptionItem(
                    "blocker", f"Split with ROC — {ln.investment}",
                    "A family split sheet was provided but the letter shows return of capital "
                    "/ gain. How ROC splits across members is not yet confirmed; entry withheld."))
                continue
            _apply_family_split(e, sheet, ln, lt, rate, narr, res)
            e.checks.append(("Entry balances Dr = Cr", e.balanced,
                             f"Dr {e.dr_total:,.2f} vs Cr {e.cr_total:,.2f}"))
            continue

        if lt.roc > 0 or lt.gain > 0:
            e.entry_type = "roc_distribution"
            roc_aed = r2(lt.roc * rate)
            income_fc = r2(lt.dividends + lt.gain)
            income_aed = r2(cash_aed - roc_aed)   # residual rounding -> income
            if lt.roc > 0:
                e.lines.append(EntryLine("Cr", "change_cost", roc_aed, lt.roc, ln.currency,
                                         narr))
                e.trace.append(f"ROC: {lt.roc:,.2f} × {rate} = AED {roc_aed:,.2f} → Change in cost")
            if income_aed > 0:
                inarr = (f"Gain on sale — {ln.investment}"
                         if lt.dividends == 0 and lt.gain > 0 else narr)
                e.lines.append(EntryLine("Cr", "div_income", income_aed, income_fc,
                                         ln.currency, inarr))
                e.trace.append(f"Income (dividends + gain, absorbs rounding): AED {income_aed:,.2f}")
        else:
            e.lines.append(EntryLine("Cr", "div_income", cash_aed, ln.credit, ln.currency, narr))

        e.checks.append(("Entry balances Dr = Cr", e.balanced,
                         f"Dr {e.dr_total:,.2f} vs Cr {e.cr_total:,.2f}"))

    # ---- capital call netting ----------------------------------------------
    subs: dict[tuple[str, str], list[StatementLine]] = {}
    for ln in stmt.lines:
        if ln.txn_type == "Subscription" and ln.debit:
            subs.setdefault((ln.investment, ln.currency), []).append(ln)
    for (inv, curr), lns in subs.items():
        rate = fx(curr)
        total_fc = r2(sum(l.debit for l in lns))
        total_aed = r2(total_fc * rate)
        cash_key = CASH_BY_CURRENCY[curr]
        desc = lns[0].description if lns else "Investment Capital Call"
        narr = f"{desc} for {inv}"
        e = new_entry(entry_date=month_end, entry_type="netting",
                      analysis_name=inv, source_lines=lns)
        for l in lns:
            e.trace.append(f"Statement {l.date:%d-%b-%y}: Subscription debit {curr} {l.debit:,.2f}")
        e.trace.append(f"Month total {curr} {total_fc:,.2f} × {rate} = AED {total_aed:,.2f} "
                       f"— booked as ONE month-end entry")
        e.lines.append(EntryLine("Dr", "investments", total_aed, total_fc, curr, narr))
        e.lines.append(EntryLine("Cr", cash_key, total_aed, total_fc, curr, narr))
        e.checks.append(("Sum of statement subscription debits", True,
                         f"{len(lns)} line(s) totalling {curr} {total_fc:,.2f}"))
        e.checks.append(("Entry balances Dr = Cr", e.balanced,
                         f"Dr {e.dr_total:,.2f} vs Cr {e.cr_total:,.2f}"))

    # ---- trust profit -------------------------------------------------------
    for ln in stmt.lines:
        if ln.txn_type != "Income Earned":
            continue
        rate = fx(ln.currency)
        cash_key = CASH_BY_CURRENCY.get(ln.currency)
        if cash_key is None:
            res.exceptions.append(ExceptionItem(
                "warning", f"Trust profit in unmapped currency {ln.currency}",
                f"{ln.description}: {ln.amount:,.2f} — no cash account configured."))
            continue
        amt_fc = ln.credit if ln.credit else ln.debit
        aed = r2(amt_fc * rate)
        ccy_word = {"EUR": "Euro"}.get(ln.currency, ln.currency)
        narr = f"Profit for {ln.date:%b-%Y} for {ccy_word} A/c"
        e = new_entry(entry_date=ln.date, entry_type="trust_profit",
                      analysis_name="", source_lines=[ln])
        e.trace.append(f"Statement {ln.date:%d-%b-%y}: {ln.description}, "
                       f"{'credit' if ln.credit else 'debit'} {ln.currency} {amt_fc:,.2f}")
        e.trace.append(f"Convert at fixed {rate}: {amt_fc:,.2f} × {rate} = AED {aed:,.2f}")
        if ln.credit:
            e.lines.append(EntryLine("Dr", cash_key, aed, amt_fc, ln.currency, narr))
            e.lines.append(EntryLine("Cr", "div_income", aed, amt_fc, ln.currency, narr))
        else:
            e.lines.append(EntryLine("Dr", "div_income", aed, amt_fc, ln.currency, ln.description))
            e.lines.append(EntryLine("Cr", cash_key, aed, amt_fc, ln.currency, ln.description))
        e.checks.append(("Entry balances Dr = Cr", e.balanced,
                         f"Dr {e.dr_total:,.2f} vs Cr {e.cr_total:,.2f}"))

    # ---- completeness -------------------------------------------------------
    for lt in letters:
        if lt.norm not in used_letters:
            res.exceptions.append(ExceptionItem(
                "warning", f"Letter with no statement line: “{lt.portfolio}”",
                f"“{lt.path.name}” shows a distribution of {lt.total:,.2f} "
                f"(date {lt.letter_date}) but no matching cash line is on this statement. "
                f"It may belong to another month or settle outside the trust account — "
                f"needs a human decision; no entry generated."))

    for curr, opening in stmt.opening.items():
        credits = sum(l.credit for l in stmt.lines if l.currency == curr)
        debits = sum(l.debit for l in stmt.lines if l.currency == curr)
        expected = r2(opening + credits - debits)
        closing = stmt.closing.get(curr)
        if closing is not None and abs(expected - closing) > 0.011:
            res.exceptions.append(ExceptionItem(
                "blocker", f"{curr} cash roll-forward break",
                f"Opening {opening:,.2f} + credits {credits:,.2f} - debits {debits:,.2f} "
                f"= {expected:,.2f}, but statement closing is {closing:,.2f}. "
                f"A statement line may have been mis-parsed."))

    # ---- analysis code (Orion Anly1) ----------------------------------------
    # Every portfolio entry needs a code for the upload file. A name the master
    # has never seen is withheld rather than uploaded without one.
    for e in res.entries:
        if not e.analysis_name:
            continue
        code = code_for(e.analysis_name)
        if code:
            e.analysis_code = code
            e.trace.append(f"Analysis code (Anly1): {code} — from the analysis master")
        elif e.ok:
            amb = is_ambiguous(e.analysis_name)
            e.checks.append(("Analysis code found", False,
                             f"“{e.analysis_name}” has more than one code in the master"
                             if amb else f"“{e.analysis_name}” is not in the analysis master"))
            res.exceptions.append(ExceptionItem(
                "blocker", f"No analysis code — {e.analysis_name}",
                f"“{e.analysis_name}” is not in the Orion analysis master, so the upload "
                f"line would have no Anly1. Add its code to investcorp_engine/analysis.py "
                f"(or add this spelling to ALIASES if the portfolio is listed under another "
                f"name) and run again."))

    res.entries.sort(key=lambda e: (e.entry_date, e.ref))
    return res


def _apply_family_split(e: Entry, sheet: SplitSheet, ln: StatementLine,
                        lt: Letter, rate: float, narr: str, res: RunResult) -> None:
    """Malco Capital layer: allocate a dividend pro-rata across the family
    investors per the split sheet, in ONE entry (replacing the manual
    two-step booking + reclass seen in the posted GL).

    Rule (verified vs NJV-2026070020 + NJV-2026070025 combined):
      member share = dividend x member investment / ORIGINAL investment
      'member'    -> Cr 10265/<sub>;  'capital_m' -> Cr 11221;
      'to_income' + Malco share + rounding residual -> Cr 30711 income.

    Credit-line denomination follows config.SPLIT_LINE_CURRENCY:
      "AED" (default, and how the posted entries are booked) — FC = LC, so
            every line's FC x rate reproduces its LC exactly; the member's
            FC-currency equivalent is carried as informational only.
      "FC"  — lines carry the received currency; the income line absorbs the
            FC residual so the FC column still foots, but a per-line
            FC x rate can differ from LC by a fil or two.
    """
    e.entry_type = "split_dividend"
    div_fc = lt.total

    # Split basis = the ORIGINAL investment. Preferred source is the letter's
    # Exhibit A "Investment Amount" (present on every letter, authoritative);
    # the sheet's own "Total Investment" cell is the fallback. The member
    # column must NOT be summed: on the current short sheet layout it totals
    # only the family's holding (150,000 of a 500,000 deal), which would
    # inflate every member's share more than threefold.
    if lt.investment_amount:
        basis, basis_src = lt.investment_amount, "letter Exhibit A “Investment Amount”"
    elif sheet.total_investment:
        basis, basis_src = sheet.total_investment, "split sheet “Total Investment”"
    else:
        basis, basis_src = 0.0, "unavailable"

    if not basis:
        e.checks.append(("Split basis available", False,
                         "no Investment Amount on the letter, no Total Investment on the sheet"))
        res.exceptions.append(ExceptionItem(
            "blocker", f"Split basis missing — {ln.investment}",
            "The family split needs the original investment amount, which was not found "
            "on the distribution letter (Exhibit A “Investment Amount”) or in the "
            "split sheet. Entry withheld."))
        e.lines.clear()
        return

    e.trace.append(
        f"Split sheet “{sheet.path.name}” ({len(sheet.members)} investor rows); "
        f"basis = original investment {basis:,.2f} from {basis_src} — member share "
        f"= dividend × investment ÷ {basis:,.0f}, at fixed {rate}")

    # The members' holdings should add up to Capital M's share of the deal.
    held = capital_m_share(ln.investment)
    to_capm = sum(m.inv_usd for m in sheet.members
                  if MEMBER_MASTER.get(m.code, ("member",))[0] in ("member", "capital_m"))
    implied = to_capm / basis
    gross = sum(m.inv_usd for m in sheet.members) / basis
    e.trace.append(f"Members hold {gross:.2%} of the investment ({implied:.2%} after Malco's own "
                   f"and transferred members); Malco / Capital M split gives Capital M "
                   f"{held:.2%} ({_holdings.AS_AT})")
    if held and abs(implied - held) > 0.005 and abs(gross - held) > 0.005:
        res.exceptions.append(ExceptionItem(
            "warning", f"Members ≠ Capital M share — {ln.investment}",
            f"The members in “{sheet.path.name}” hold USD {sum(m.inv_usd for m in sheet.members):,.2f} "
            f"of the USD {basis:,.0f} investment ({gross:.2%}; {implied:.2%} goes to Capital M "
            f"members after Malco's own and transferred members), but the Malco / Capital M "
            f"split gives Capital M {held:.2%}. Booked on the members as supplied — confirm "
            f"the member list is complete."))

    sheet_ok = sheet.dividend_fc is None or abs(sheet.dividend_fc - div_fc) < 0.005
    e.checks.append(("Split sheet dividend = letter/statement", sheet_ok,
                     f"sheet {sheet.dividend_fc if sheet.dividend_fc is not None else 'not stated'}"
                     f" vs {div_fc:,.2f}"))
    if not sheet_ok:
        res.exceptions.append(ExceptionItem(
            "blocker", f"Split sheet amount mismatch — {ln.investment}",
            f"Sheet dividend {sheet.dividend_fc} ≠ statement {div_fc:,.2f}. Entry withheld."))
        e.lines.clear()
        return

    aed_lines = (SPLIT_LINE_CURRENCY.upper() == "AED")
    cash_aed = r2(div_fc * rate)
    credited_aed = 0.0
    credited_fc = 0.0
    recompute_breaks: list[str] = []
    n_member_lines = 0

    for m in sheet.members:
        treat, sub, disp = MEMBER_MASTER.get(m.code, ("unknown", None, m.name))
        share_fc_raw = div_fc * m.inv_usd / basis if basis else 0.0
        share_aed = r2(share_fc_raw * rate)
        share_fc = r2(share_fc_raw)

        if m.sheet_div_aed and abs(share_aed - r2(m.sheet_div_aed)) > 0.011:
            recompute_breaks.append(f"{m.code} {share_aed:,.2f} vs sheet {m.sheet_div_aed:,.2f}")
        if treat == "unknown":
            res.exceptions.append(ExceptionItem(
                "blocker", f"Unknown member code {m.code}",
                f"“{m.name}” is not in the member master — confirm its Orion "
                f"treatment. Entry withheld."))
            e.checks.append(("Member master covers all codes", False, m.code))
            e.lines.clear()
            return
        if share_aed <= 0 or treat == "to_income":
            continue  # zero holders skip; transferred members fold into income

        if aed_lines:
            line_ccy, line_fc = "AED", share_aed
            info_fc, info_ccy = share_fc, ln.currency
        else:
            line_ccy, line_fc = ln.currency, share_fc
            info_fc, info_ccy = 0.0, ""

        if treat == "member":
            e.lines.append(EntryLine("Cr", "", share_aed, line_fc, line_ccy, narr,
                                     ex_main=MEMBERS_MAIN_ACCOUNT, ex_sub=sub or "",
                                     ex_name=f"{MEMBERS_MAIN_NAME} / {disp}",
                                     info_fc=info_fc, info_ccy=info_ccy))
        elif treat == "capital_m":
            e.lines.append(EntryLine("Cr", "", share_aed, line_fc, line_ccy,
                                     f"{narr} - {disp} ({m.code})",
                                     ex_main=CAPITAL_M_ACCOUNT, ex_sub="",
                                     ex_name=CAPITAL_M_NAME,
                                     info_fc=info_fc, info_ccy=info_ccy))
        credited_aed = r2(credited_aed + share_aed)
        credited_fc = r2(credited_fc + share_fc)
        n_member_lines += 1

    # The income line absorbs the residual in BOTH columns, so each column foots.
    income_aed = r2(cash_aed - credited_aed)
    if aed_lines:
        e.lines.append(EntryLine("Cr", "div_income", income_aed, income_aed, "AED", narr,
                                 info_fc=r2(div_fc - credited_fc), info_ccy=ln.currency))
    else:
        e.lines.append(EntryLine("Cr", "div_income", income_aed, r2(div_fc - credited_fc),
                                 ln.currency, narr))

    e.trace.append(
        f"{n_member_lines} investor lines credited AED {credited_aed:,.2f}; Malco share, "
        f"transferred members and rounding residual → income AED {income_aed:,.2f}. "
        + ("Credit lines are booked in AED (as the posted split entries are), so each line's "
           "FC × rate equals its LC exactly; the investor's FC equivalent is shown in the "
           "informational column."
           if aed_lines else
           "Credit lines carry the received currency; the income line absorbs the FC residual "
           "so the FC column foots, but a per-line FC × rate may differ from LC by a fil."))
    e.checks.append(("Per-member recomputation matches split sheet",
                     not recompute_breaks,
                     "all lines" if not recompute_breaks else "; ".join(recompute_breaks[:4])))

    # both columns must foot against the cash debit
    cr_fc = r2(sum(l.fc for l in e.lines if l.drcr == "Cr" and l.currency == ln.currency)
               + sum(l.info_fc for l in e.lines if l.drcr == "Cr" and l.info_ccy == ln.currency))
    e.checks.append(("FC column foots to the cash debit", abs(cr_fc - div_fc) < 0.011,
                     f"credits {cr_fc:,.2f} vs cash {div_fc:,.2f} {ln.currency}"))
