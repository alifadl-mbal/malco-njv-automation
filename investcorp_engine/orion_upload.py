"""Write the Orion JV upload file, in the exact layout of JV_UPLOAD_TEMPLATE.xls.

One row per journal line; lines of the same NJV document share a Doc No. The
header row is the template's, column for column (134 columns, including the
trailing space in 'Seq No '). Every value is text, as in the template.
"""
from __future__ import annotations

from pathlib import Path

import xlwt

from .booking import RunResult
from .config import DEPARTMENT, DIVISION, ORION_UPLOAD

HEADER = (
    ["Doc No", "Doc Dt", "Seq No ", "Ref Seq No", "Manual Entry Y/N", "Main A/C",
     "Sub A/C", "Div", "Dept", "Anly1", "Anly2", "Acty1", "Acty2", "Currency", "FC Amt",
     "LC Amt", "Dr/Cr", "Detail Narration", "Header Narration", "Paym Mode",
     "Chq Book Id", "Chq No", "Chq Dt", "Payee Name", "Val Date", "Doc Ref", "TH Doc ref",
     "Due Dt"]
    + [f"FLEX_{i:02d}" for i in range(1, 51)]
    + ["Party Code", "NOP/NOR", "Tax Code", "Expense Code", "DISC Code"]
    + [f"TH_FLEX_{i:02d}" for i in range(1, 51)]
    + ["TD_BANK_ACNT_NO"]
)
COL = {h: i for i, h in enumerate(HEADER)}


def upload_rows(res: RunResult) -> list[list[str]]:
    cfg = ORION_UPLOAD
    fmt = cfg["amount_format"].format
    rows: list[list[str]] = []
    for n, e in enumerate(res.ok_entries, start=cfg["doc_no_start"]):
        header_narr = e.lines[0].narration if e.lines else ""
        for seq, l in enumerate(e.lines, start=1):
            r = [""] * len(HEADER)
            r[COL["Doc No"]] = str(n)
            r[COL["Doc Dt"]] = e.entry_date.strftime(cfg["date_format"])
            r[COL["Seq No "]] = str(seq)
            r[COL["Manual Entry Y/N"]] = cfg["manual_entry"]
            r[COL["Main A/C"]] = l.main
            r[COL["Sub A/C"]] = l.sub or ""
            r[COL["Div"]] = DIVISION
            r[COL["Dept"]] = DEPARTMENT
            if cfg["anly1_lines"] == "all":
                r[COL["Anly1"]] = e.analysis_code
            r[COL["Currency"]] = l.currency
            r[COL["FC Amt"]] = fmt(l.fc)
            r[COL["LC Amt"]] = fmt(l.aed)
            r[COL["Dr/Cr"]] = cfg["dr"] if l.drcr == "Dr" else cfg["cr"]
            r[COL["Detail Narration"]] = l.narration
            r[COL["Header Narration"]] = header_narr
            r[COL["FLEX_01"]] = cfg.get("flex_01", "")
            rows.append(r)
    return rows


def write_orion_upload(res: RunResult, out_path: Path) -> Path:
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Sheet1")
    text = xlwt.easyxf(num_format_str="@")
    for c, h in enumerate(HEADER):
        ws.write(0, c, h, text)
    for r, row in enumerate(upload_rows(res), start=1):
        for c, v in enumerate(row):
            if v != "":
                ws.write(r, c, v, text)
    widths = {"Doc No": 9, "Doc Dt": 11, "Seq No ": 7, "Manual Entry Y/N": 15,
              "Main A/C": 10, "Sub A/C": 10, "Div": 6, "Dept": 6, "Anly1": 15,
              "Currency": 9, "FC Amt": 13, "LC Amt": 13, "Dr/Cr": 6,
              "Detail Narration": 48, "Header Narration": 48}
    for h, w in widths.items():
        ws.col(COL[h]).width = 256 * w
    wb.save(str(out_path))
    return out_path
