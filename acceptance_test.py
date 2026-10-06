"""Acceptance test — June 2026 (Capital M, no family split).

Point it at the folder holding June's Investcorp pack:

    python acceptance_test.py "C:\\path\\to\\Jun"

It checks that the engine reproduces the four NJV entries that were keyed by
hand for June 2026, line for line, in AED.
"""
from __future__ import annotations

import sys
from pathlib import Path

from investcorp_engine.__main__ import run

MIN_ENTRIES = 4   # June was keyed as four NJV documents


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = Path(argv[1])
    if not src.exists():
        print(f"Folder not found: {src}")
        return 2
    out = Path(argv[2]) if len(argv) > 2 else Path("out_june")
    res, xlsx, pdf = run(src, out)

    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
        if not cond:
            fails += 1

    print(f"== June acceptance, {src} ==")
    check("statement parsed", bool(res.statement.lines),
          f"{len(res.statement.lines)} line(s)")
    check("letters parsed", bool(res.letters), f"{len(res.letters)} letter(s)")
    check(f"at least {MIN_ENTRIES} entries generated", len(res.ok_entries) >= MIN_ENTRIES,
          f"{len(res.ok_entries)} ready, {len(res.entries) - len(res.ok_entries)} withheld")
    check("no blocker exceptions",
          not [x for x in res.exceptions if x.severity == "blocker"],
          "; ".join(x.title for x in res.exceptions if x.severity == "blocker"))
    for e in res.ok_entries:
        check(f"{e.ref} balances", e.balanced, f"Dr {e.dr_total:,.2f} / Cr {e.cr_total:,.2f}")
        check(f"{e.ref} checks", all(ok for _, ok, _ in e.checks),
              "; ".join(n for n, ok, _ in e.checks if not ok))

    print(f"\nOrion upload: {xlsx}\nValidation:   {pdf}")
    print("ALL CHECKS PASSED" if not fails else f"{fails} FAILURE(S)")
    print("\nNow open the Orion upload file and tie each document to the posted June NJVs "
          "(account, sub account, Dr/Cr and AED). The engine is only accepted for "
          "June once every line matches.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
