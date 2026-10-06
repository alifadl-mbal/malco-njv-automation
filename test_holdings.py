"""Checks on the Malco / Capital M split table (holdings.py). No documents needed.

    python test_holdings.py
"""
import sys

from investcorp_engine.analysis import code_for, is_ambiguous
from investcorp_engine.holdings import PENDING, SPLIT, capital_m_share
from investcorp_engine.members import SPLIT_REQUIRED_PORTFOLIOS
from investcorp_engine.parser import normalize_name

fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    fails += 0 if cond else 1


print("== Malco / Capital M split ==")
investcorp = [(c, n, s) for c, n, cp, s in SPLIT if cp == "Investcorp"]
split = sorted(n for c, n, s in investcorp if capital_m_share(c) > 0)
check("Investcorp holdings with a Capital M share = SPLIT_REQUIRED_PORTFOLIOS",
      {normalize_name(n) for n in split} == {normalize_name(n) for n in SPLIT_REQUIRED_PORTFOLIOS},
      str(split))
check("every holding's code is in the analysis master and points back to it",
      all(code_for(n) == c for c, n, _, _ in SPLIT if not is_ambiguous(n)
          and code_for(n) is not None),
      str([(c, n, code_for(n)) for c, n, _, _ in SPLIT if code_for(n) not in (None, c)]))
missing = [(c, n) for c, n, cp, _ in SPLIT if cp == "Investcorp" and code_for(n) is None]
check("every Investcorp portfolio resolves to a code by name", not missing, str(missing))
s = capital_m_share("M00131794562")
malco = round(round(114_472.90 * (1 - s), 2) * 3.68, 2)
check("2019 US I&L share reproduces posted NJV-2026080006 change in cost", malco == 256_968.77,
      f"{s:.4%} -> AED {malco:,.2f}")
check("name and code give the same share", capital_m_share(
      "2019 US Industrial & Logistics Portfolio") == capital_m_share("M00131794562"))
check("Stepful rounding remnant treated as 100% Malco", capital_m_share("ZZ0000000062") == 0)
check("April EFG coupons are 100% Malco", capital_m_share("XS0911024635") == 0
      and capital_m_share("XS2701661303") == 0)
check("pending F-2 holdings stay guarded", all(capital_m_share(k) > 0 for k in PENDING),
      str(list(PENDING)))
check("ambiguous name never resolves to a code", code_for("Innoskel") is None)
print("\nALL CHECKS PASSED" if not fails else f"\n{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
