"""Acceptance test — August 2026 (Capital M, plus one unresolved ROC).

    python acceptance_test_august.py "C:\\path\\to\\Aug"

Ground truth is the posted sub-ledger for account 10259, 01-Aug to 31-Aug-2026
(NJV-2026080001 .. 2026080010), embedded below. Only account 10259 was exported,
so the income and investor credits are not checked here — the cash debits and
the change-in-cost credits are.

NJV-2026080006 (2019 US Industrial & Logistics, 100% return of capital) is
deliberately NOT expected: the engine withholds it. Posted was Dr cash
421,260.27 with only 256,968.77 credited to change in cost; the remaining
164,291.50 went to an account outside this export. Until that is confirmed the
entry is keyed by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

from investcorp_engine.__main__ import run

# (main, sub) -> {narration fragment: signed AED, Dr positive}
# Narrations exactly as posted in Orion (sub-ledger 10259, Aug 2026)
POSTED_CASH = {            # 10259 / XC0002, USD cash account
    "Dividend from Eastern Living Properties Portfolio":      10001.50,
    "Distribution from Credit Opportunity Portfolio IV":      47472.00,
    "Dividend from Sunbelt Multifamily Portfolio":             4521.87,
    "Dividend from 2022 Residential Properties Portfolio":    13913.38,
    "Dividend from US Student Housing IV Portfolio":          29682.00,
    "Distribution from Credit Opportunity Portfolio VIII":    80592.00,
    "Dividend from US National Industrial Portfolio II":      12038.46,
    "Profit for Aug-2026 for USD A/c":                          855.78,
}
POSTED_CASH_EUR = {        # 10259 / XC00023, EUR cash account
    "Profit for Aug-2026 for Euro A/c":                          33.03,
}
POSTED_CHANGE_IN_COST = {  # 10259 / XC0004, credits
    "Distribution from Credit Opportunity Portfolio IV":      34224.00,
    "Distribution from Credit Opportunity Portfolio VIII":    52765.16,
}
EXPECTED_ANLY1 = {
    "Eastern Living Properties Portfolio": "Investcorp2",
    "Credit Opportunity Portfolio IV": "M00138314710",
    "Sunbelt Multifamily Portfolio": "M00141485003",
    "2022 Residential Properties Portfolio": "M00168424083",
    "US Student Housing IV Portfolio": "INVESTCORP11",
    "Credit Opportunity Portfolio VIII": "Investcorp5",      # NOT INVESTCORP5
    "US National Industrial Portfolio II": "M00155699669",
}
WITHHELD_HINT = "industrial & logistics"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = Path(argv[1])
    if not src.exists():
        print(f"Folder not found: {src}")
        return 2
    out = Path(argv[2]) if len(argv) > 2 else Path("out_august")
    res, xlsx, pdf = run(src, out)

    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
        if not cond:
            fails += 1

    def amount(sub, fragment, drcr):
        total = 0.0
        for e in res.ok_entries:
            for l in e.lines:
                if l.sub == sub and l.drcr == drcr and l.narration == fragment:
                    total += l.aed
        return round(total, 2)

    print(f"== August acceptance, {src} ==")
    check("statement parsed, 10 lines", len(res.statement.lines) == 10,
          f"{len(res.statement.lines)}")
    check("8 letters parsed", len(res.letters) == 8, f"{len(res.letters)}")
    check("9 entries ready", len(res.ok_entries) == 9, f"{len(res.ok_entries)}")

    for frag, want in POSTED_CASH.items():
        got = amount("XC0002", frag, "Dr")
        check(f"cash Dr {frag}", abs(got - want) < 0.005, f"{got:,.2f} vs {want:,.2f}")
    for frag, want in POSTED_CASH_EUR.items():
        got = amount("XC00023", frag, "Dr")
        check(f"cash Dr {frag}", abs(got - want) < 0.005, f"{got:,.2f} vs {want:,.2f}")
    for frag, want in POSTED_CHANGE_IN_COST.items():
        got = amount("XC0004", frag, "Cr")
        check(f"change in cost Cr {frag}", abs(got - want) < 0.005, f"{got:,.2f} vs {want:,.2f}")

    for e in res.ok_entries:
        check(f"{e.ref} balances", e.balanced, f"Dr {e.dr_total:,.2f} / Cr {e.cr_total:,.2f}")
        check(f"{e.ref} checks", all(ok for _, ok, _ in e.checks),
              "; ".join(n for n, ok, _ in e.checks if not ok))

    for e in res.ok_entries:
        if e.analysis_name:
            want = EXPECTED_ANLY1.get(e.analysis_name)
            check(f"{e.ref} Anly1 {e.analysis_code}", e.analysis_code == want,
                  f"want {want}")

    # the Orion upload file: template header, text cells, one Doc No per entry, balanced
    from investcorp_engine.orion_upload import HEADER
    from python_calamine import CalamineWorkbook
    up = out / f"NJV Upload - {res.month_label}.xls"
    rows = CalamineWorkbook.from_path(str(up)).get_sheet_by_name("Sheet1").to_python()
    check("upload header = JV_UPLOAD_TEMPLATE", [str(x) for x in rows[0]] == HEADER)
    body = rows[1:]
    check("upload has one row per journal line", len(body) == sum(len(e.lines) for e in res.ok_entries),
          f"{len(body)} rows")
    H = HEADER
    docs = {}
    for r in body:
        d = docs.setdefault(r[H.index("Doc No")], [0.0, 0.0])
        d[0 if r[H.index("Dr/Cr")] == "Dr" else 1] += float(r[H.index("LC Amt")])
    check("upload: every document balances in LC", all(abs(a - b) < 0.005 for a, b in docs.values()),
          f"{len(docs)} documents")

    withheld = [x for x in res.exceptions if WITHHELD_HINT in x.title.lower()]
    check("the pure-ROC entry is withheld, not booked", len(withheld) == 1,
          "; ".join(x.title for x in res.exceptions))
    # the withheld entry's figures, from the F-2 Capital M share, equal what was posted
    x = withheld[0].detail if withheld else ""
    check("pure-ROC split = posted NJV-2026080006 (change in cost 256,968.77)",
          "AED 256,968.77" in x and "AED 164,291.50" in x, x[:90])
    check("nothing else is withheld", len(res.exceptions) == 1,
          "; ".join(x.title for x in res.exceptions))

    print(f"\nOrion upload: {xlsx}\nValidation:   {pdf}")
    print("ALL CHECKS PASSED" if not fails else f"{fails} FAILURE(S)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
