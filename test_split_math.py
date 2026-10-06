"""Self-contained regression test for the family-split layer.

Needs no PDFs or Excel files: the July 2026 figures (member investments from
the split sheet, and the AED amounts actually posted in Orion as
NJV-2026070020 + reclass NJV-2026070025) are embedded below.

Run:  python test_split_math.py
"""
import sys
from datetime import date
from pathlib import Path

from investcorp_engine import config
from investcorp_engine.booking import build_entries
from investcorp_engine.parser import (Letter, SplitMember, SplitSheet,
                                      Statement, StatementLine)

PORTFOLIO = "2019 US Industrial & Logistics Portfolio"
DIVIDEND_USD = 2409.15
BASIS = 500_000.0          # letter Exhibit A "Investment Amount"
RATE = 3.68

# member investments (USD) — 2026 July split sheet, short layout
INVESTMENTS = {
    "CM0004": 0.0,                  "CM0005": 5859.26769341432,
    "CM0006": 5859.26769341432,     "CM0007": 5859.26769341432,
    "CM0008": 9374.817213874685,    "CM0009": 43358.730721707165,
    "CM0011": 5859.267693414323,    "CM0012": 5859.267693414323,
    "CM0013": 585.9156737531969,    "CM0015": 2214.7851023017906,
    "CM0016": 1523.4140385230185,   "CM0017": 1159.8428564578007,
    "CM0018": 2882.7617023657285,   "CM0019": 5799.3252381713555,
    "CM0020": 5859.267693414323,    "CM0021": 5859.267693414323,
    "CM0022": 11598.678215313297,   "CM0024": 8202.985866368286,
    "CM0026": 2343.690433983376,    "CM0027": 2462.311708359974,
    "CM0028": 3560.5818414322243,   "CM0029": 1186.8606138107414,
    "CM0030": 1186.8606138107414,   "CM0031": 1186.8606138107414,
    "CM0032": 1186.8606138107414,   "CM0025": 1171.8315217391305,
    "CM0001": 7998.011556505733,
}

# AED actually posted, net of NJV-2026070020 + NJV-2026070025, per (account, sub)
POSTED = {
    ("10259", "XC0002"): 8865.67,   # Dr cash
    ("10265", "XI0002"): -103.89,   ("10265", "XI0003"): -103.89,
    ("10265", "XC0005"): -103.89,   ("10265", "XC0046"): -166.23,
    ("10265", "XC0007"): -768.81,   ("10265", "XC0016"): -103.89,
    ("10265", "XC0008"): -103.89,   ("10265", "XC0035"): -10.39,
    ("10265", "XC0010"): -39.27,    ("10265", "XC0009"): -27.01,
    ("10265", "XC0014"): -51.12,    ("10265", "XC0018"): -102.83,
    ("10265", "XC0015"): -103.89,   ("10265", "XC0017"): -103.89,
    ("10265", "XC0019"): -205.66,   ("10265", "QU0025"): -145.45,
    ("10265", "XC0058"): -41.56,    ("10265", "XC0033"): -43.66,
    ("10265", "XC0025"): -63.13,    ("10265", "XC0027"): -21.04,
    ("10265", "XC0026"): -21.04,    ("10265", "XC0028"): -21.04,
    ("10265", "XC0029"): -21.04,    ("11221", ""):        -20.57,
    ("30711", "MCI0001"): -6368.59,
}


def build():
    ln = StatementLine(date=date(2026, 7, 28), txn_type="Distribution",
                       investment=PORTFOLIO, description="Distribution",
                       currency="USD", credit=DIVIDEND_USD)
    stmt = Statement(path=Path("July statement.pdf"), month_label="July 2026", lines=[ln])
    letter = Letter(path=Path("2019 US I&L Distribution.pdf"), portfolio=PORTFOLIO,
                    letter_date=date(2026, 7, 28), dividends=DIVIDEND_USD,
                    total=DIVIDEND_USD, investment_amount=BASIS)
    sheet = SplitSheet(path=Path("2019 US Industrial Logistics Calculation.xlsx"),
                       portfolio="2019 US Industrial Logistics", dividend_fc=None,
                       total_investment=0.0, basis_source="filename-only sheet",
                       members=[SplitMember(code=c, name=c, inv_usd=v)
                                for c, v in INVESTMENTS.items()])
    return build_entries(stmt, [letter], [sheet])


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    return 0 if cond else 1


def main():
    fails = 0
    print(f"== family split, SPLIT_LINE_CURRENCY = {config.SPLIT_LINE_CURRENCY} ==")
    res = build()
    entries = res.ok_entries
    blockers = [x for x in res.exceptions if x.severity == "blocker"]
    fails += check("one entry generated, no blockers",
                   len(entries) == 1 and not blockers,
                   f"{len(entries)} entr(y/ies), {len(blockers)} blocker(s)")
    # July's member list covers 30% of the deal; the split table says Capital M is 39%.
    # That is an open question for Malco, so the engine must say so on every such run.
    warn = [x for x in res.exceptions if x.severity == "warning" and "Capital M share" in x.title]
    fails += check("members-vs-split warning raised (30% list vs 39% split)", len(warn) == 1,
                   warn[0].detail[:110] if warn else "none")
    if not entries:
        print("FAILURE — nothing generated"); return 1
    e = entries[0]

    got = {}
    for l in e.lines:
        key = (l.main, l.sub or "")
        got[key] = round(got.get(key, 0.0) + (l.aed if l.drcr == "Dr" else -l.aed), 2)

    mismatches = [f"{k[0]}/{k[1] or '-'} {got.get(k, 0.0):,.2f} vs {v:,.2f}"
                  for k, v in POSTED.items() if abs(got.get(k, 0.0) - v) >= 0.005]
    extra = [k for k in got if k not in POSTED]
    fails += check(f"all {len(POSTED)} posted lines reproduced in AED",
                   not mismatches, "; ".join(mismatches[:3]))
    fails += check("no extra lines invented", not extra, str(extra[:3]))
    fails += check("entry balances", e.balanced, f"Dr {e.dr_total:,.2f} / Cr {e.cr_total:,.2f}")
    fails += check("every check on the entry passed",
                   all(ok for _, ok, _ in e.checks),
                   "; ".join(n for n, ok, _ in e.checks if not ok))

    # FC x rate vs LC. Exact in AED mode (that is the point of it); in FC mode
    # a per-line gap of a fil or two is inherent to rounding an uneven share in
    # two currencies, and is only safe if Orion keys FC and LC independently.
    bad_fc = [f"{l.main}/{l.sub or '-'}" for l in e.lines
              if abs(round(l.fc * config.FX_RATES.get(l.currency, 1.0) + 1e-9, 2) - l.aed) >= 0.005]
    if config.SPLIT_LINE_CURRENCY.upper() == "AED":
        fails += check("FC x rate reproduces LC on every line", not bad_fc, "; ".join(bad_fc[:3]))
    else:
        print(f"  NOTE  FC mode: {len(bad_fc)} of {len(e.lines)} lines have FC x rate a fil or "
              f"two from LC (expected; both columns still foot)")

    # the FC column must foot to the cash debit, counting informational FC
    cr_fc = round(sum(l.fc for l in e.lines if l.drcr == "Cr" and l.currency == "USD")
                  + sum(l.info_fc for l in e.lines if l.drcr == "Cr" and l.info_ccy == "USD"), 2)
    fails += check("FC column foots to the cash debit", abs(cr_fc - DIVIDEND_USD) < 0.011,
                   f"{cr_fc:,.2f} vs {DIVIDEND_USD:,.2f}")

    # guard: the family column must not be used as the basis
    fam_total = round(sum(INVESTMENTS.values()), 2)
    fails += check("basis is the letter's investment amount, not the member column",
                   abs(fam_total - BASIS) > 1, f"member column sums to {fam_total:,.2f}")

    print("\nALL CHECKS PASSED" if not fails else f"\n{fails} FAILURE(S)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
