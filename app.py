"""Investcorp → Orion statement automation — local web app.

Run:  uv run streamlit run app.py
Then open http://localhost:8501 in the browser.

Everything runs locally: files are processed in a temporary folder on this
machine and nothing is sent anywhere.
"""
from __future__ import annotations

import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import streamlit as st

from investcorp_engine.__main__ import build, write_outputs
from investcorp_engine.efg import is_efg_statement
from investcorp_engine.config import SPLIT_LINE_CURRENCY

st.set_page_config(page_title="Investcorp → Orion", page_icon="🧾", layout="wide")

ACCENT = "#0E7C66"
st.markdown(f"""
<style>
  .stApp h1 {{ font-size: 1.6rem; }}
  div[data-testid="stMetricValue"] {{ color: {ACCENT}; }}
  .block-container {{ padding-top: 2.2rem; max-width: 1150px; }}
  div[data-testid="stFileUploaderDropzone"] {{ padding: 0.9rem 1rem; }}
</style>""", unsafe_allow_html=True)

COUNTERPARTIES = {
    "Investcorp": {
        "ready": True,
        "note": "Statement, distribution letters and family-split sheets. "
                "Rules verified against posted June, July and August 2026 entries.",
    },
    "EFG Bank": {
        "ready": True,
        "note": "Monthly Account Statement Report only. Coupons, loan-interest settlements "
                "and principal rollovers; rules verified against posted April 2026 entries.",
    },
    "Other private entity": {"ready": False,
                             "note": "Not configured yet — send one month's pack to add it."},
}

st.title("Statement → Orion NJV automation")

entity = st.selectbox(
    "Counterparty", list(COUNTERPARTIES), index=0,
    help="Each counterparty has its own statement layout and booking rules.")
meta = COUNTERPARTIES[entity]

if not meta["ready"]:
    st.warning(f"**{entity} is not configured yet.** {meta['note']}  \n"
               "Only Investcorp can be processed at the moment.")
    st.stop()

st.caption(f"**{entity}** — {meta['note']} Everything is processed locally on this machine.")
st.divider()

if entity == "EFG Bank":
    st.subheader("1 · Upload this month's statement")
    stmt_file = st.file_uploader("statement", type=["pdf"], key="efg_stmt",
                                 label_visibility="collapsed")
    letter_files = []
    split_files = st.file_uploader("Family split workbook (optional) — Holdings split / Members",
                                   type=["xlsx", "xls"], key="efg_splits",
                                   accept_multiple_files=True)
    with st.expander("Expected format"):
        st.markdown(
            "One PDF per month, as EFG sends it — the **Account Statement Report** for "
            "account 5089261210 (USD).\n\n"
            "- Coupons with an ISIN → cash / dividend received in EFG, Anly1 = the ISIN\n"
            "- *Miscellaneous debits … settlement* → financial expenses\n"
            "- A principal repaid and redrawn the same day → no entry (loan rollover)\n"
            "- A coupon on a sukuk Capital M part-owns, a security sale or purchase, or "
            "anything else → withheld as an exception")
else:
    st.subheader("1 · Upload this month's documents")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Monthly statement** &nbsp;·&nbsp; required")
        stmt_file = st.file_uploader("statement", type=["pdf"], key="stmt",
                                     label_visibility="collapsed")
        with st.expander("Expected format"):
            st.markdown(
                "One PDF per month, as Investcorp sends it.\n\n"
                "- File name like **`Investment Statement - August 2026.pdf`**\n"
                "- The engine reads the last page, **“Trust Account Statement”** — every "
                "USD/EUR cash line there becomes a journal entry\n"
                "- The month shown on the statement names the output files")

    with c2:
        st.markdown("**Distribution letters** &nbsp;·&nbsp; one per distribution")
        letter_files = st.file_uploader("letters", type=["pdf"], key="letters",
                                        accept_multiple_files=True,
                                        label_visibility="collapsed")
        with st.expander("Expected format"):
            st.markdown(
                "One PDF per distribution event, original file names are fine.\n\n"
                "- e.g. **`2019 US Industrial & Logistics Portfolio Investment Distribution.pdf`**\n"
                "- The engine reads **Exhibit A**: Dividends, Return of Capital, Capital Gain, "
                "and **Investment Amount** (the split basis)\n"
                "- A distribution on the statement with **no letter** is withheld — never "
                "booked on the statement figure alone")

    with c3:
        st.markdown("**Family split workbook** &nbsp;·&nbsp; optional")
        split_files = st.file_uploader("splits", type=["xlsx", "xls"], key="splits",
                                       accept_multiple_files=True,
                                       label_visibility="collapsed")
        with st.expander("Expected format"):
            st.markdown(
                "**One master workbook for every split investment** — use "
                "`Family Split Master.xlsx`. The engine reads each sheet by its header "
                "and, for a distribution, takes only the rows of that investment.\n\n"
                "Sheet **Members** — one row per investor per investment:")
            st.table([
                {"Analysis Code": "M00131794562", "Portfolio": "2019 US Industrial & Logistics Portfolio",
                 "CM Code": "CM0005", "Investor": "Asia Abdulrahman Arif", "Investment (USD)": "5,859.27"},
                {"Analysis Code": "M00131794562", "Portfolio": "2019 US Industrial & Logistics Portfolio",
                 "CM Code": "CM0001", "Investor": "Malco Capital Investments LLC", "Investment (USD)": "7,998.01"},
                {"Analysis Code": "M00162315753", "Portfolio": "USA Rare Earth",
                 "CM Code": "CM00xx", "Investor": "…", "Investment (USD)": "…"},
            ])
            st.markdown(
                "Sheet **Holdings split** (optional) — the Malco / Capital M fraction per "
                "holding, same layout as sheet “1” of *Split_revised.xlsx*. If present it "
                "replaces the built-in table for this run.\n\n"
                "*Split_revised.xlsx* itself can be uploaded as it is. The older one-file-"
                "per-portfolio sheets (CM code | investor | investment, portfolio in the "
                "file name) also still work. A split investment with **no members** is "
                "withheld, never booked to Malco.")

ready = stmt_file is not None
run = st.button("Run", type="primary", disabled=not ready)
if not ready:
    st.caption("The monthly statement is required before the run can start.")

if run and stmt_file:
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "in"; out = Path(td) / "out"
        inp.mkdir(); out.mkdir()
        stmt_path = inp / stmt_file.name
        stmt_path.write_bytes(stmt_file.getbuffer())
        letter_paths, split_paths = [], []
        for f in (letter_files or []):
            p = inp / f"letter_{len(letter_paths)}_{Path(f.name).name}"
            p.write_bytes(f.getbuffer()); letter_paths.append(p)
        for f in (split_files or []):
            p = inp / Path(f.name).name
            p.write_bytes(f.getbuffer()); split_paths.append(p)

        try:
            with st.spinner("Parsing documents and generating entries…"):
                if entity == "EFG Bank" and not is_efg_statement(stmt_path):
                    raise ValueError("this does not look like an EFG Account Statement Report")
                res = build(stmt_path, letter_paths, split_paths,
                            "EFG" if entity == "EFG Bank" else "Investcorp")
                stmt = res.statement
                letters, split_sheets = res.letters, res.split_sheets
                label = res.month_label or "output"
                xls, pdf = write_outputs(res, out)
        except Exception as exc:                        # noqa: BLE001 - surfaced to the user
            st.error(
                f"Could not process this pack: **{type(exc).__name__}: {exc}**\n\n"
                "Nothing was generated. Check that the statement PDF opens normally and "
                "that the split sheets are the usual calculation workbooks, then try again. "
                "If it keeps failing, send this message with the files to the automation team.")
            with st.expander("Technical detail (for the developer)"):
                st.code(traceback.format_exc())
            st.stop()

        st.session_state["result"] = {
            "entity": entity, "label": label,
            "pdf": pdf.read_bytes(), "pdf_name": pdf.name,
            "xls": xls.read_bytes(), "xls_name": xls.name,
            "n_lines": len(stmt.lines), "n_letters": len(letters),
            "n_sheets": len(split_sheets), "n_no_entry": len(res.no_entry),
            "notes": list(res.input_notes),
            "entries": [
                dict(ref=e.ref, date=str(e.entry_date), type=e.entry_type,
                     name=e.analysis_name or "Trust account", code=e.analysis_code,
                     lines=len(e.lines), dr=e.dr_total, cr=e.cr_total, ok=e.ok)
                for e in res.entries],
            "exceptions": [dict(sev=x.severity, title=x.title, detail=x.detail)
                           for x in res.exceptions],
            "ran_at": datetime.now().strftime("%d-%b-%Y %H:%M"),
        }

r = st.session_state.get("result")
if r:
    st.divider()
    ok_entries = [e for e in r["entries"] if e["ok"]]
    withheld = [e for e in r["entries"] if not e["ok"]]
    blockers = [x for x in r["exceptions"] if x["sev"] == "blocker"]

    st.subheader(f"2 · {r['entity']} — {r['label']}")
    st.caption(f"Run at {r['ran_at']}" + ("" if r["entity"] == "EFG Bank"
               else f" · split credit lines denominated in {SPLIT_LINE_CURRENCY}"))
    for note in r.get("notes", []):
        st.caption(note)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Statement lines", r["n_lines"])
    if r["entity"] == "EFG Bank":
        m2.metric("No entry needed", r.get("n_no_entry", 0))
    else:
        m2.metric("Letters / split sheets", f"{r['n_letters']} / {r['n_sheets']}")
    m3.metric("Entries ready to key", len(ok_entries))
    m4.metric("Withheld (exceptions)", len(withheld),
              delta=None if not withheld else f"{len(blockers)} blocker(s)",
              delta_color="inverse")

    d0, d2 = st.columns(2)
    d0.download_button(f"⬇ {r['xls_name']}", r["xls"], file_name=r["xls_name"],
                       mime="application/vnd.ms-excel", type="primary",
                       use_container_width=True,
                       help="Orion JV upload file — JV_UPLOAD_TEMPLATE layout.")
    d2.download_button(f"⬇ {r['pdf_name']}", r["pdf"], file_name=r["pdf_name"],
                       mime="application/pdf", type="primary", use_container_width=True)

    st.subheader("Proposed entries")
    st.table(
        [{"Entry": e["ref"], "Date": e["date"],
          "Type": {"dividend": "Dividend", "roc_distribution": "Distribution with ROC/gain",
                   "split_dividend": "Dividend + family split", "netting": "Capital call netting",
                   "trust_profit": "Trust profit", "coupon": "Sukuk / bond coupon",
                   "loan_interest": "Loan interest settlement"}.get(e["type"], e["type"]),
          "Portfolio / account": e["name"], "Anly1": e["code"], "Lines": e["lines"],
          "Dr (AED)": f"{e['dr']:,.2f}", "Cr (AED)": f"{e['cr']:,.2f}",
          "Status": "✅ ready" if e["ok"] else "⛔ withheld"}
         for e in r["entries"]])

    st.subheader("Exceptions — human decision needed")
    if not r["exceptions"]:
        st.success("None this month.")
    else:
        for x in r["exceptions"]:
            (st.error if x["sev"] == "blocker" else st.warning)(
                f"**{x['title']}** — {x['detail']}")
        st.caption("Fix the input (e.g. add the missing letter above) and press Run again — "
                   "regeneration takes seconds.")
else:
    st.info("Upload the month's documents and press **Run**. Anything that fails a check "
            "is listed as an exception — the app never books a line it cannot verify.")
