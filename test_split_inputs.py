"""How family-split inputs are read — no statement PDFs needed.

    python test_split_inputs.py [path/to/Split_revised.xlsx]

Uses templates/Family Split Master.xlsx and the July 2026 2019 US I&L dividend
(posted NJV-2026070020 + 070025, the same fixture as test_split_math.py).
"""
import sys
import tempfile
from pathlib import Path

import xlwt

from investcorp_engine import holdings
from investcorp_engine.booking import build_entries
from investcorp_engine.split_master import read_split_inputs
from test_split_math import DIVIDEND_USD, INVESTMENTS, POSTED, build as build_fixture

HERE = Path(__file__).parent
MASTER = HERE / "templates" / "Family Split Master.xlsx"
fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    fails += 0 if cond else 1


def july(sheets, table=None):
    """Re-run the July dividend with the given member lists."""
    base = build_fixture()                       # gives the statement + letter objects
    stmt, letters = base.statement, base.letters
    with holdings.using(table) if table else _null():
        return build_entries(stmt, letters, sheets)


class _null:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def posted_match(res):
    e = next((e for e in res.ok_entries if e.entry_type == "split_dividend"), None)
    if not e:
        return False, "no split entry"
    got = {}
    for l in e.lines:
        k = (l.main, l.sub or "")
        got[k] = round(got.get(k, 0.0) + (l.aed if l.drcr == "Dr" else -l.aed), 2)
    bad = [k for k, v in POSTED.items() if abs(got.get(k, 0) - v) >= 0.005]
    return (not bad and len(got) == len(POSTED)), f"{len(POSTED) - len(bad)}/{len(POSTED)} lines"


def xls(path, sheets):
    wb = xlwt.Workbook()
    for name, rows in sheets.items():
        ws = wb.add_sheet(name)
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                ws.write(i, j, v)
    wb.save(str(path))
    return path


tmp = Path(tempfile.mkdtemp())
members_2019 = [("M00131794562", "2019 US Industrial & Logistics Portfolio", cm, "", v)
                for cm, v in INVESTMENTS.items()]
hdr = ("Analysis Code", "Portfolio", "CM Code", "Investor", "Investment (USD)")

print("== 1. the master workbook (templates/Family Split Master.xlsx) ==")
inp = read_split_inputs([MASTER])
check("read: 1 member list, 45-holding split table, no problems",
      len(inp.sheets) == 1 and len(inp.holdings or {}) == 45 and not inp.problems,
      f"{len(inp.sheets)} list(s), {len(inp.holdings or {})} holdings, {inp.problems}")
ok, d = posted_match(july(inp.sheets, inp.holdings))
check("July dividend from the master = posted NJV-2026070020+025", ok, d)

print("== 2. many investments in one Members sheet ==")
rows = [hdr] + members_2019 + [
    ("M00162315753", "USA Rare Earth", "CM0027", "Fathiya Mukri", 456_000.00),
    ("M00229099272", "Vectara", "CM0006", "Hamdan Mostafa", 50_000.00),
    ("M00229099272", "Vectara", "CM0009", "Al Manhaj", 75_000.00),
]
inp = read_split_inputs([xls(tmp / "all_investments.xls", {"Members": rows})])
check("3 investments read as 3 separate member lists",
      sorted(s.code for s in inp.sheets) == ["M00131794562", "M00162315753", "M00229099272"],
      str([(s.code, len(s.members)) for s in inp.sheets]))
ok, d = posted_match(july(inp.sheets))
check("2019 US I&L dividend uses only its own 27 investors", ok, d)

print("== 3. identified by portfolio name only (no Analysis Code column) ==")
rows = [("Portfolio", "CM Code", "Investor", "Investment (USD)")] + [
    (p, cm, n, v) for _, p, cm, n, v in members_2019]
inp = read_split_inputs([xls(tmp / "by_name.xls", {"Members": rows})])
ok, d = posted_match(july(inp.sheets))
check("name-keyed member list matches the dividend", ok and inp.sheets[0].code == "M00131794562", d)

print("== 4. one sheet per investment, sheet named by analysis code ==")
per = {"M00131794562": [(cm, "", v) for _, _, cm, _, v in members_2019],
       "M00162315753": [("CM0027", "Fathiya Mukri", 456_000.00)]}
inp = read_split_inputs([xls(tmp / "per_sheet.xls", per)])
ok, d = posted_match(july(inp.sheets))
check("per-sheet workbook matches the dividend", ok and len(inp.sheets) == 2, d)

print("== 5. the older one-file-per-portfolio sheet still works ==")
legacy = xls(tmp / "2019 US Industrial Logistics Calculation.xls",
             {"Sheet1": [(cm, "", v) for _, _, cm, _, v in members_2019]})
inp = read_split_inputs([legacy])
ok, d = posted_match(july(inp.sheets))
check("legacy file matches the dividend", ok, d)

print("== 6. guards ==")
inp = read_split_inputs([MASTER, legacy])
res = july(inp.sheets)
check("same investment in two files -> problem reported, entry withheld",
      any("twice" in p for p in inp.problems) and not res.ok_entries, str(inp.problems)[:90])
rows = [hdr] + members_2019 + [members_2019[0]]
inp = read_split_inputs([xls(tmp / "dup.xls", {"Members": rows})])
check("investor listed twice for one investment -> problem reported",
      any("listed twice" in p for p in inp.problems))
res = july([])
check("split investment with no members -> withheld, never booked to Malco",
      not res.ok_entries and any("Split sheet missing" in x.title for x in res.exceptions))

if len(sys.argv) > 1:
    print("== 7. Split_revised.xlsx uploaded as it is ==")
    inp = read_split_inputs([Path(sys.argv[1])])
    check("reads its split table (sheet “1”) and Codes; it has no investor lists",
          len(inp.holdings or {}) == 45 and len(inp.codes) == 101 and not inp.sheets,
          f"{len(inp.holdings or {})} holdings, {len(inp.codes)} codes, {len(inp.sheets)} member lists")
    check("its split table is identical to the built-in one", holdings.differences(inp.holdings) == [])
    res = july(inp.sheets, inp.holdings)
    check("on its own it cannot book a split dividend (no investors) -> withheld",
          not res.ok_entries and any("Split sheet missing" in x.title for x in res.exceptions))
    ok, d = posted_match(july(read_split_inputs([Path(sys.argv[1]), MASTER]).sheets, inp.holdings))
    check("Split_revised.xlsx + the master's Members together -> posted lines", ok, d)

print("\nALL CHECKS PASSED" if not fails else f"\n{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
