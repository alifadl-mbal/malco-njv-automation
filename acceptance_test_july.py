"""Acceptance test — July 2026 (Malco Capital family split).

Point it at the folder holding July's Investcorp pack (statement PDF,
distribution letter PDFs, split calculation workbook):

    python acceptance_test_july.py "C:\\path\\to\\Jul"

July was keyed by hand in two documents — the booking NJV-2026070020 and the
reclass NJV-2026070025. The engine produces the net position in one entry, so
the test compares against the NET of those two, which is embedded below.
"""
from __future__ import annotations

import sys
from pathlib import Path

from investcorp_engine import config
from investcorp_engine.__main__ import run

# Net of NJV-2026070020 + NJV-2026070025, per (main account, sub account).
# Dr positive, Cr negative, AED.
POSTED_SPLIT = {
    ("10259", "XC0002"): 8865.67,
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
SPLIT_PORTFOLIO_HINT = "industrial"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = Path(argv[1])
    if not src.exists():
        print(f"Folder not found: {src}")
        return 2
    out = Path(argv[2]) if len(argv) > 2 else Path("out_july")
    res, xlsx, pdf = run(src, out)

    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
        if not cond:
            fails += 1

    print(f"== July acceptance, {src} (SPLIT_LINE_CURRENCY={config.SPLIT_LINE_CURRENCY}) ==")
    check("statement parsed", bool(res.statement.lines),
          f"{len(res.statement.lines)} line(s)")
    check("split sheet found and matched", bool(res.split_sheets),
          f"{len(res.split_sheets)} sheet(s)")
    check("no blocker exceptions",
          not [x for x in res.exceptions if x.severity == "blocker"],
          "; ".join(x.title for x in res.exceptions if x.severity == "blocker"))

    split = [e for e in res.ok_entries
             if SPLIT_PORTFOLIO_HINT in (e.analysis_name or "").lower()]
    check("the split entry was generated", len(split) == 1,
          f"{len(split)} candidate(s)")
    if not split:
        print(f"\n{fails} FAILURE(S)")
        return 1
    e = split[0]

    got = {}
    for l in e.lines:
        k = (l.main, l.sub or "")
        got[k] = round(got.get(k, 0.0) + (l.aed if l.drcr == "Dr" else -l.aed), 2)

    mismatch = [f"{k[0]}/{k[1] or '-'} got {got.get(k, 0.0):,.2f} want {v:,.2f}"
                for k, v in POSTED_SPLIT.items() if abs(got.get(k, 0.0) - v) >= 0.005]
    extra = [k for k in got if k not in POSTED_SPLIT]
    check(f"all {len(POSTED_SPLIT)} posted lines reproduced in AED", not mismatch,
          "; ".join(mismatch[:4]))
    check("no extra lines invented", not extra, str(extra[:4]))
    check("entry balances", e.balanced, f"Dr {e.dr_total:,.2f} / Cr {e.cr_total:,.2f}")
    check("every check on the entry passed", all(ok for _, ok, _ in e.checks),
          "; ".join(n for n, ok, _ in e.checks if not ok))

    for other in res.ok_entries:
        if other is e:
            continue
        check(f"{other.ref} balances", other.balanced,
              f"Dr {other.dr_total:,.2f} / Cr {other.cr_total:,.2f}")

    print(f"\nOrion upload: {xlsx}\nValidation:   {pdf}")
    print("ALL CHECKS PASSED" if not fails else f"{fails} FAILURE(S)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
