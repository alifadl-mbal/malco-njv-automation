"""Self-contained checks of the EFG guards (no PDF needed).

    python test_efg_rules.py
"""
import sys
from datetime import date
from pathlib import Path

from investcorp_engine.efg import build_efg_entries
from investcorp_engine.parser import Statement, StatementLine


def line(d, typ, isin, desc, dr=0.0, cr=0.0):
    return StatementLine(date=date(2026, 5, d), txn_type=typ, investment=isin,
                         description=desc, currency="USD", debit=dr, credit=cr)


fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    fails += 0 if cond else 1


st = Statement(path=Path("synthetic.pdf"), month_label="May 2026", lines=[
    line(5, "Coupon", "XS2471859251", "COUPONS ARADA 8.125%", cr=24375.00),          # 100% Capital M
    line(6, "Coupon", "XS2124942595", "COUPONS DAR AL ARKAN 6.875%", cr=20625.00),   # 83.33% Capital M
    line(7, "Coupon", "XS9999999999", "COUPONS UNKNOWN", cr=100.00),                 # not in master
    line(8, "Coupon", "XS2311313378", "COUPONS ARABIAN CENTRES 5.625%", cr=6187.50), # 100% Malco
    line(9, "Principal out", "", "PRINCIPAL PAYMENT LD/1", dr=500000.00),           # unpaired
    line(10, "Other", "", "SECURITIES PURCHASE 100 SHARES", dr=12000.00),            # no rule
])
res = build_efg_entries(st)
titles = [x.title for x in res.exceptions]
print("== EFG guards ==")
check("Arada (100% Capital M) coupon withheld", any("Arada" in t or "ARADA" in t for t in titles), str(titles))
check("Dar Al Arkan 6.875% (83% Capital M) coupon withheld",
      any("6.875" in t for t in titles), str(titles))
check("unknown ISIN withheld", any("XS9999999999" in t for t in titles))
check("unpaired principal withheld", any("Unpaired principal" in t for t in titles))
check("unrecognised line withheld", any("Unrecognised" in t for t in titles))
ok = res.ok_entries
check("only the 100%-Malco coupon is booked", len(ok) == 1 and ok[0].analysis_code == "XS2311313378",
      str([e.analysis_code for e in ok]))
print("\nALL CHECKS PASSED" if not fails else f"\n{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
