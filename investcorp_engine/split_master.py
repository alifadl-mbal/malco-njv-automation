"""Read the family-split workbooks Malco supplies.

One workbook can now carry everything; each sheet is recognised by its header:

  Members        — who holds what in each split investment, any number of
                   investments in one sheet:
                   Analysis Code | Portfolio | CM Code | Investor | Investment (USD)
                   The engine takes only the rows of the investment being booked.
  Holdings split — the Malco / Capital M fraction per holding, in the layout of
                   Split_revised.xlsx sheet "1":
                   No. | Details | Analysis Code | Mapping | Portfolio | Malco | capital M
                   When present it is used for the run instead of the built-in table.
  Codes          — "As per Orion" Code | Name (Split_revised.xlsx sheet "Codes");
                   extends the analysis master for the run.

The older one-file-per-portfolio sheets (CM code | investor | investment, the
portfolio taken from the file name) still work unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import code_for, code_for_fragment, name_for_code
from .parser import SplitMember, SplitSheet, normalize_name, parse_split_sheet

CM_RE = re.compile(r"^CM\d{4}$")


def _txt(v) -> str:
    return str(v).strip() if v is not None else ""


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "")) if _txt(v) else None
    except ValueError:
        return None


def _find_header(rows, *patterns):
    """First row (index, {pattern: col}) whose cells match every pattern."""
    for i, r in enumerate(rows[:30]):
        cells = [_txt(c).lower() for c in r]
        hit = {}
        for p in patterns:
            for j, c in enumerate(cells):
                if j not in hit.values() and re.search(p, c):
                    hit[p] = j
                    break
        if len(hit) == len(patterns):
            return i, hit
    return None, None


@dataclass
class SplitInputs:
    sheets: list[SplitSheet] = field(default_factory=list)        # member lists, per investment
    holdings: dict[str, tuple[str, float]] | None = None          # code -> (name, Capital M share)
    holdings_source: str = ""
    codes: list[tuple[str, str]] = field(default_factory=list)    # extra analysis codes
    problems: list[str] = field(default_factory=list)             # blocking input problems
    notes: list[str] = field(default_factory=list)


def read_workbook(path: Path, into: SplitInputs) -> None:
    try:
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_path(str(path))
    except Exception:
        return
    used_any = False
    for sheet_name in wb.sheet_names:
        rows = wb.get_sheet_by_name(sheet_name).to_python(skip_empty_area=False)

        # --- Holdings split (Malco / Capital M fractions) -------------------------
        hi, hc = _find_header(rows, r"analysis\s*code", r"^malco$", r"capital\s*m")
        if hi is not None:
            name_col = next((j for j, c in enumerate(rows[hi]) if _txt(c).lower() in
                             ("details", "portfolio name", "investment", "name")), None)
            table = {}
            for r in rows[hi + 1:]:
                code = _txt(r[hc[r"analysis\s*code"]]) if len(r) > hc[r"analysis\s*code"] else ""
                m = _num(r[hc[r"^malco$"]]) if len(r) > hc[r"^malco$"] else None
                c = _num(r[hc[r"capital\s*m"]]) if len(r) > hc[r"capital\s*m"] else None
                if not code or c is None:
                    continue
                name = _txt(r[name_col]) if name_col is not None and len(r) > name_col else code
                if m is not None and abs(m + c - 1) > 0.001:
                    into.problems.append(
                        f"{path.name} / {sheet_name}: {code} Malco {m:.4f} + Capital M {c:.4f} ≠ 1")
                table[code] = (name, c)
            if table:
                if into.holdings is not None:
                    into.problems.append(f"Two Malco / Capital M split tables supplied "
                                         f"({into.holdings_source} and {path.name} / {sheet_name})")
                into.holdings = table
                into.holdings_source = f"{path.name} / sheet “{sheet_name}”"
                used_any = True
            continue

        # --- Codes ("As per Orion": Code | Name) -----------------------------------
        ci, cc = _find_header(rows, r"^code$", r"^name$")
        if ci is not None and any("as per orion" in _txt(c).lower()
                                  for r in rows[:ci + 1] for c in r):
            for r in rows[ci + 1:]:
                code, name = _txt(r[cc[r"^code$"]]), _txt(r[cc[r"^name$"]])
                if code and name:
                    into.codes.append((code, name))
            used_any = True
            continue

        # --- Members master (many investments in one sheet) ------------------------
        mi, mc = _find_header(rows, r"cm\s*code", r"investment|amount|usd")
        if mi is not None:
            key_col = next((j for j, c in enumerate(rows[mi]) if re.search(r"analysis\s*code",
                            _txt(c).lower())), None)
            name_col = next((j for j, c in enumerate(rows[mi]) if re.search(
                            r"^(portfolio|investment name|details|holding)$", _txt(c).lower())), None)
            inv_name_col = next((j for j, c in enumerate(rows[mi]) if re.search(
                                r"investor|member|name", _txt(c).lower())
                                and j not in (key_col, name_col, mc[r"cm\s*code"])), None)
            if key_col is not None or name_col is not None:
                groups: dict[str, dict] = {}
                for n, r in enumerate(rows[mi + 1:], start=mi + 2):
                    cm = _txt(r[mc[r"cm\s*code"]]) if len(r) > mc[r"cm\s*code"] else ""
                    if not CM_RE.match(cm):
                        continue
                    code = _txt(r[key_col]) if key_col is not None and len(r) > key_col else ""
                    pname = _txt(r[name_col]) if name_col is not None and len(r) > name_col else ""
                    if not code and pname:
                        code = code_for(pname) or ""
                    if code and not pname:
                        pname = name_for_code(code) or code
                    key = code or normalize_name(pname)
                    if not key:
                        into.problems.append(f"{path.name} / {sheet_name} row {n}: {cm} has no "
                                             f"analysis code or portfolio")
                        continue
                    amt = _num(r[mc[r"investment|amount|usd"]])
                    g = groups.setdefault(key, {"code": code, "name": pname, "members": {}})
                    if cm in g["members"]:
                        into.problems.append(f"{path.name} / {sheet_name}: {cm} listed twice "
                                             f"for {pname or code}")
                        continue
                    inv_name = (_txt(r[inv_name_col]) if inv_name_col is not None
                                and len(r) > inv_name_col else "")
                    g["members"][cm] = SplitMember(code=cm, name=inv_name, inv_usd=amt or 0.0)
                for key, g in groups.items():
                    into.sheets.append(SplitSheet(
                        path=Path(f"{path.name} · {sheet_name}"), portfolio=g["name"] or key,
                        dividend_fc=None, total_investment=0.0,
                        members=list(g["members"].values()),
                        basis_source=f"members master ({g['code'] or 'by name'})",
                        code=g["code"]))
                if groups:
                    used_any = True
                continue
    if not used_any:
        cm_sheets = [n for n in wb.sheet_names
                     if any(r and CM_RE.match(_txt(r[0])) for r in
                            wb.get_sheet_by_name(n).to_python(skip_empty_area=False))]
        if len(cm_sheets) <= 1:
            # older layout: one portfolio per file, CM rows, name from the file name
            s = parse_split_sheet(path)
            if s and s.members:
                s.code = code_for_fragment(s.portfolio) or ""
                into.sheets.append(s)
            return
        # one sheet per investment: the sheet name must identify the investment
        for n in cm_sheets:
            rows = wb.get_sheet_by_name(n).to_python(skip_empty_area=False)
            code = n.strip() if name_for_code(n.strip()) else (code_for(n) or "")
            if not code:
                into.problems.append(f"{path.name}: sheet “{n}” has investor rows but its name "
                                     f"is not an analysis code or a known portfolio name")
                continue
            members = []
            for r in rows:
                if r and CM_RE.match(_txt(r[0])):
                    nums = [c for c in r[2:] if isinstance(c, (int, float))]
                    members.append(SplitMember(code=_txt(r[0]),
                                               name=_txt(r[1]) if len(r) > 1 else "",
                                               inv_usd=float(nums[0]) if nums else 0.0))
            into.sheets.append(SplitSheet(path=Path(f"{path.name} · {n}"),
                                          portfolio=name_for_code(code) or n, dividend_fc=None,
                                          total_investment=0.0, members=members,
                                          basis_source=f"sheet per investment ({code})", code=code))


def read_split_inputs(paths) -> SplitInputs:
    inputs = SplitInputs()
    for p in paths:
        read_workbook(Path(p), inputs)
    # the same investment supplied twice is ambiguous — never pick one
    seen: dict[str, str] = {}
    for s in inputs.sheets:
        key = getattr(s, "code", "") or s.norm
        if key in seen:
            inputs.problems.append(f"Members for “{s.portfolio}” supplied twice "
                                   f"({seen[key]} and {s.path.name})")
        seen[key] = s.path.name
    return inputs


def read_split_folder(folder: Path) -> SplitInputs:
    paths = sorted(list(folder.glob("*.xlsx")) + list(folder.glob("*.xls")))
    return read_split_inputs(paths)
