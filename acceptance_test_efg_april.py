"""Acceptance test — EFG Bank, April 2026.

    python acceptance_test_efg_april.py "C:\\path\\to\\EFG Apr"

The folder holds EFG's "Account Statement Report" for April 2026. Ground truth
is the posted GL (ZF_F_T_DETAIL_BI, exported 28-Sep-2026), embedded below:
NJV-2026040009, 040010 and 040011, every line. The 02-Apr principal pair
(USD 1,850,000 out and in) has no posted entry and must produce none.
"""
from __future__ import annotations

import sys
from pathlib import Path

from investcorp_engine.__main__ import run

# (doc, seq): (main, sub, anly1, currency, Dr/Cr, LC, FC, narration) — as posted
POSTED = {
    ("2026040009", 1): ("40840", "", "", "USD", "Dr", 29136.36, 7917.49,
                        "MISCELLANEOUS DEBITS DC260928400001003 SETTLEMENT RM-2026-17"),
    ("2026040009", 2): ("10269", "XC0002", "", "USD", "Cr", 29136.36, 7917.49,
                        "MISCELLANEOUS DEBITS DC260928400001003 SETTLEMENT RM-2026-17"),
    ("2026040010", 1): ("10269", "XC0002", "XS0911024635", "USD", "Dr", 27931.20, 7590.00,
                        "COUPONS DIARSC/26093/05026 5.06 SAUDI ELECTRICITY REG-S 8.4.43 INTEREST RATE 5.06%"),
    ("2026040010", 2): ("30711", "MCI0002", "XS0911024635", "USD", "Cr", 27931.20, 7590.00,
                        "COUPONS DIARSC/26093/05026 5.06 SAUDI ELECTRICITY REG-S 8.4.43 INTEREST RATE 5.06%"),
    ("2026040011", 1): ("10269", "XC0002", "XS2701661303", "USD", "Dr", 107870.00, 29312.50,
                        "COUPONS DIARSC/26097/05580 8.375 ALPHA STAR 12.04.27 INTEREST RATE 8.375%"),
    ("2026040011", 2): ("30711", "MCI0002", "XS2701661303", "USD", "Cr", 107870.00, 29312.50,
                        "COUPONS DIARSC/26097/05580 8.375 ALPHA STAR 12.04.27 INTEREST RATE 8.375%"),
}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else Path("out_efg_april")
    res, xls, pdf = run(src, out)

    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
        if not cond:
            fails += 1

    print(f"== EFG April acceptance, {src} ==")
    check("counterparty detected as EFG", res.counterparty == "EFG", res.counterparty)
    check("5 statement lines read", len(res.statement.lines) == 5, f"{len(res.statement.lines)}")
    check("roll-forward: initial + credits - debits = closing",
          not any("roll-forward" in x.title for x in res.exceptions))
    check("3 entries, none withheld", len(res.ok_entries) == 3 and not res.exceptions,
          f"{len(res.ok_entries)} ready; {[x.title for x in res.exceptions]}")
    check("principal rollover pair: no entry, both lines explained", len(res.no_entry) == 2)

    got = []
    for e in res.ok_entries:
        for l in e.lines:
            got.append((l.main, l.sub or "", e.analysis_code, l.currency, l.drcr,
                        round(l.aed, 2), round(l.fc, 2), l.narration))
    want = [v for _, v in sorted(POSTED.items())]
    for w in want:
        check(f"posted line {w[0]}/{w[1] or '-'} {w[4]} {w[5]:,.2f} {w[2] or ''}".rstrip(),
              w in got, "" if w in got else "not generated exactly")
    check("no extra lines", len(got) == len(want), f"{len(got)} vs {len(want)}")

    from investcorp_engine.orion_upload import HEADER
    from python_calamine import CalamineWorkbook
    rows = CalamineWorkbook.from_path(str(xls)).get_sheet_by_name("Sheet1").to_python()
    check("upload header = JV_UPLOAD_TEMPLATE", [str(x) for x in rows[0]] == HEADER)
    check("upload: 6 rows in 3 documents", len(rows) - 1 == 6
          and len({r[0] for r in rows[1:]}) == 3)

    print(f"\nOrion upload: {xls}\nValidation:   {pdf}")
    print("ALL CHECKS PASSED" if not fails else f"{fails} FAILURE(S)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
