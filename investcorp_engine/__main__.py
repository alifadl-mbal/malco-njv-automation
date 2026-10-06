"""CLI: python -m investcorp_engine <input_folder> [-o <output_folder>]

<input_folder> holds one month's pack for ONE counterparty, detected
automatically:
  Investcorp — the monthly Investment Statement PDF, one distribution letter PDF
               per event, and any family-split calculation workbooks
  EFG Bank   — the monthly "Account Statement Report" PDF

Outputs (into the output folder):
  Validation Report - [EFG - ]<Month>.pdf   — audit trail for the accountant
  NJV Upload - [EFG - ]<Month>.xls          — Orion JV upload file (template layout)
Exit code is non-zero when blocker exceptions exist.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .booking import build_entries
from .efg import build_efg_entries, is_efg_statement, parse_efg_statement
from .orion_upload import write_orion_upload
from contextlib import nullcontext

from . import analysis, holdings
from .booking import ExceptionItem
from .parser import find_statement, parse_letters, parse_statement
from .split_master import read_split_inputs
from .validation import write_validation_report


def output_label(res) -> str:
    """File-name label: 'August 2026' for Investcorp, 'EFG - April 2026' otherwise."""
    label = res.month_label or "output"
    return label if res.counterparty == "Investcorp" else f"{res.counterparty} - {label}"


def write_outputs(res, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    label = output_label(res)
    pdf = write_validation_report(res, output_dir / f"Validation Report - {label}.pdf")
    xls = write_orion_upload(res, output_dir / f"NJV Upload - {label}.xls")
    return xls, pdf


def build(statement_pdf: Path, letter_pdfs: list[Path], split_files: list[Path],
          counterparty: str | None = None):
    """One month, one counterparty. Shared by the CLI and the app."""
    inputs = read_split_inputs(split_files)
    holdings_ctx = (holdings.using(inputs.holdings, inputs.holdings_source)
                    if inputs.holdings else nullcontext())
    with analysis.extended(inputs.codes), holdings_ctx:
        if counterparty == "EFG" or (counterparty is None and is_efg_statement(statement_pdf)):
            res = build_efg_entries(parse_efg_statement(statement_pdf))
        else:
            stmt = parse_statement(statement_pdf)
            letters = parse_letters(list(letter_pdfs))
            res = build_entries(stmt, letters, inputs.sheets)
    for prob in inputs.problems:
        res.exceptions.append(ExceptionItem("blocker", "Split workbook problem", prob))
    if inputs.holdings:
        diffs = holdings.differences(inputs.holdings)
        res.input_notes.append(f"Malco / Capital M split: {inputs.holdings_source} "
                               f"({len(inputs.holdings)} holdings)"
                               + ("" if diffs else " — same as the built-in table"))
        for d in diffs:
            res.exceptions.append(ExceptionItem("warning", "Uploaded split differs from built-in", d))
    else:
        res.input_notes.append(f"Malco / Capital M split: built-in ({holdings.SOURCE})")
    if inputs.sheets:
        res.input_notes.append("Family members: " + "; ".join(
            f"{s.portfolio} — {len(s.members)} investors ({s.path.name})" for s in inputs.sheets))
    if inputs.codes:
        res.input_notes.append(f"Analysis codes: {len(inputs.codes)} read from the upload")
    return res


def run(input_dir: Path, output_dir: Path):
    pdfs = sorted(input_dir.glob("*.pdf"))
    xlsx = sorted(list(input_dir.glob("*.xlsx")) + list(input_dir.glob("*.xls")))
    efg = [p for p in pdfs if is_efg_statement(p)]
    if efg:
        if len(efg) > 1:
            raise ValueError(f"{len(efg)} EFG statements in {input_dir} — run one month at a time")
        res = build(efg[0], [], xlsx, "EFG")
    else:
        stmt_path = find_statement(input_dir)
        res = build(stmt_path, [p for p in pdfs if p != stmt_path], xlsx, "Investcorp")
    xls, pdf = write_outputs(res, output_dir)
    return res, xls, pdf


def main(argv=None):
    ap = argparse.ArgumentParser(prog="investcorp_engine", description=__doc__)
    ap.add_argument("input", type=Path, help="folder with the month's documents")
    ap.add_argument("-o", "--output", type=Path, default=Path("out"))
    args = ap.parse_args(argv)

    res, xls, pdf = run(args.input, args.output)

    print(f"Counterparty:       {res.counterparty}")
    print(f"Month:              {res.month_label}")
    print(f"Statement lines:    {len(res.statement.lines)}")
    print(f"Letters parsed:     {len(res.letters)}")
    print(f"Entries generated:  {len(res.ok_entries)} ready "
          f"({len(res.entries) - len(res.ok_entries)} withheld)")
    for e in res.ok_entries:
        print(f"  {e.ref} {e.entry_date} {e.entry_type:<16} "
              f"{(e.analysis_name or 'Trust account')[:42]:<42} "
              f"Dr {e.dr_total:>12,.2f}  Cr {e.cr_total:>12,.2f}")
    if res.exceptions:
        print("Exceptions:")
        for x in res.exceptions:
            print(f"  [{x.severity.upper()}] {x.title}")
    print(f"Orion upload:       {xls}")
    print(f"Validation report:  {pdf}")
    return 1 if [x for x in res.exceptions if x.severity == "blocker"] else 0


if __name__ == "__main__":
    sys.exit(main())
