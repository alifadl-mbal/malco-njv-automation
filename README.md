# Statement → Orion entry engine (Investcorp, EFG Bank)

Turns one month's Investcorp document pack into a ready-to-key Orion NJV entry
sheet plus a validation report the accountant can sign off without reopening
the source documents.

Version 0.14.0.

---

## What it produces

| File | For |
|---|---|
| `NJV Upload - <Month>.xls` | Orion's JV upload — the exact `JV_UPLOAD_TEMPLATE.xls` layout, one Doc No per NJV |
| `Validation Report - <Month>.pdf` | Sucharitha — every number traced to its source, with the checks that passed |

Anything that fails a check is **withheld from the upload file** and appears in
the report's Exceptions section instead. The engine never guesses.

---

## The app

`uv run streamlit run app.py` opens a local page: pick the counterparty, upload the
statement, the distribution letters and any split sheets, press Run, and download
the Orion upload file and the validation report. Proposed entries
(with their Anly1 code) and exceptions are listed on the page.

## Running it

The app (easiest):

```
uv run streamlit run app.py
```

Pick the counterparty, upload the statement, the split sheet and the
distribution letters, download the two outputs.

The command line (for a whole folder at once):

```
uv run python -m investcorp_engine "C:\path\to\Jul" -o out
```

Regression test, needs no documents:

```
uv run python test_split_math.py
```

Acceptance tests, against your own copies of the source packs:

```
uv run python acceptance_test.py      "C:\path\to\Jun"
uv run python acceptance_test_july.py "C:\path\to\Jul"
uv run python acceptance_test_august.py "C:\path\to\Aug"
```

Both compare the generated lines against what was actually posted in Orion.

---

## Inputs

**Monthly Investment Statement (PDF).** The Investcorp statement covering the
month. Parsed for the Trust Account page: date, transaction type, investment
name, currency, debit/credit.

**Distribution letters (PDF), one per event.** Parsed for the portfolio name,
the letter date, the dividend / return-of-capital / gain split, the total, and —
for split deals — the **Investment Amount** in Exhibit A. That Investment Amount
is the split basis.

**Family split workbook (XLSX) — one for everything.** Use
`templates/Family Split Master.xlsx`. Each sheet is recognised by its header row:

| Sheet | Columns | What it does |
|---|---|---|
| Members | Analysis Code · Portfolio · CM Code · Investor · Investment (USD) | investors per split investment — **all investments in one sheet**; for a distribution only that investment's rows are used |
| Holdings split | No. · Details · Analysis Code · Mapping · Portfolio · Malco · capital M | the Malco / Capital M fraction per holding (sheet "1" of Split_revised.xlsx); replaces the built-in table for the run |
| Summary | formulas | per split holding: investors listed and their total — a 0 means its entries will be withheld |

Rows are matched to a distribution by analysis code (or by portfolio name when the
code column is empty). Also accepted: one sheet per investment named by its analysis
code; the older one-file-per-portfolio sheet (CM code · investor · investment, portfolio
in the file name); and Split_revised.xlsx as it is (its split table and Codes sheet are
read; it has no investor lists, so a split dividend still needs Members). The same
investment supplied twice, or an investor listed twice for one investment, is reported
and the entry withheld.

The engine does *not* use the members' total as the basis — that sums to the family's
own holding, not the original investment. It does compare it with the Capital M share
and warns when they differ (2019 US I&L: members 30%, split table 39%).

---|---|---|
| portfolio name | in the sheet | taken from the file name |
| dividend | in the sheet | taken from the letter |
| columns | CM code, name, …, investment | CM code, name, investment |

In either layout the engine reads the **CM code** and the **investment amount
per member**. It does *not* use the column total as the basis — that column sums
to the family's own holding, not the original investment, and using it would
inflate every share.

---

## How a split is computed

```
member share = dividend × member investment ÷ original investment (letter Exhibit A)
```

Shares are rounded to 2 decimals and the **income line absorbs the residual**, so
the entry foots exactly. Members flagged `to_income` (Malco itself, Doodman) and
the Capital M member (Monawar → 11221) are routed per the member master in
`investcorp_engine/members.py`.

Portfolios are matched by **analysis NAME**, never by analysis code.

---

## EFG Bank

Input: the monthly **Account Statement Report** PDF (account 5089261210, USD) —
nothing else. The CLI and the app recognise it automatically; outputs are named
`NJV Upload - EFG - <Month>.xls` and `Validation Report - EFG - <Month>.pdf`.

Rules, each taken from the posted GL (ZF_F_T_DETAIL_BI):

| Statement line | Entry |
|---|---|
| `COUPONS …` with an ISIN (credit) | Dr 10269/XC0002 cash · Cr 30711/MCI0002 dividend received in EFG · Anly1 = the ISIN on both lines |
| `MISCELLANEOUS DEBITS … SETTLEMENT` (debit) | Dr 40840 financial expenses · Cr 10269/XC0002 cash · no Anly1 |
| `PRINCIPAL PAYMENT` + `PRINCIPAL`, same day, same amount | no entry — loan rollover |

Narration is the statement description, verbatim. Withheld as exceptions: a coupon
on a sukuk Capital M part-owns (per the F-2), an ISIN not in the analysis master, an
unpaired principal, and anything else (security sales and purchases have no rule yet).

April 2026 reproduces NJV-2026040009, 040010 and 040011 line for line
(`acceptance_test_efg_april.py`).

## Malco / Capital M split

`investcorp_engine/holdings.py` holds the Malco / Capital M fraction of every holding,
keyed by analysis code, from **Split_revised.xlsx sheet "1"** (2026-10-06). Every share
in it agrees with the 31-Dec-2025 F-2. Among the Investcorp portfolios only
**2019 US Industrial & Logistics (39%)** is split, which confirms
`SPLIT_REQUIRED_PORTFOLIOS`; the same 39% reproduces the posted August return of capital
(NJV-2026080006: 61% → change in cost AED 256,968.77, 39% → Capital M AED 164,291.50).

Five holdings the F-2 shows as part-owned by Capital M are missing from the revised
split (four EFG sukuks and Al Jubail Gateway). They sit in `PENDING` and are still
treated as split until Malco confirms them.

## The Orion upload file

`NJV Upload - <Month>.xls` has the template's 134 columns in the template's order,
header spelled exactly as the template (including the trailing space in `Seq No `),
and — like the template — every value stored as text. Per line it fills:

| Column | Value |
|---|---|
| Doc No | 1, 2, 3 … one per NJV document |
| Doc Dt | entry date, `dd/mm/yyyy` |
| Seq No | line number within the document |
| Manual Entry Y/N | `N` |
| Main A/C, Sub A/C | from the booking rules |
| Div, Dept | `MCI`, `DXB` |
| Anly1 | the portfolio's code from the analysis master (blank on trust profit) |
| Currency, FC Amt, LC Amt | e.g. `USD`, `2717.80`, `10001.50` |
| Dr/Cr | `Dr` / `Cr` |
| Detail / Header Narration | Orion's own wording, e.g. `Dividend from Eastern Living Properties Portfolio` |
| FLEX_01 | `IP0001` — on every posted investment NJV since 10-Apr-2026 |

Everything else is left blank. The unconfirmed choices — Doc No numbering, the
Manual Entry flag, date format, Dr/Cr spelling, which lines carry Anly1 — are all
in `ORION_UPLOAD` in `config.py`.

Narrations follow the posted convention: `Dividend from X` when the letter is
dividend-only, `Distribution from X` when it carries return of capital or gain,
`Return of Capital from X` when it is all ROC, and `Profit for Aug-2026 for USD A/c`
/ `for Euro A/c` for trust profit.

## The analysis master

`investcorp_engine/analysis.py` holds every ANL_CODE1 and its name — 105 codes: the list sent on 2026-09-24 plus the "Codes" sheet of Split_revised.xlsx. A name with two codes (Innoskel) never resolves to either. Portfolios are
still matched by name; the code is looked up from the name. A portfolio the
master doesn't know is withheld with an exception rather than uploaded without an
Anly1. If Investcorp spells a portfolio differently from the master, add the
spelling to `ALIASES`.

Codes are never case-folded: `Investcorp5` (Credit Opportunity Portfolio VIII)
and `INVESTCORP5` (Baltimore and Minneapolis) are different portfolios.

## The currency convention

Split credit lines are denominated in **AED** by default, matching the posted
April and July split entries. A single setting controls it:

```python
# investcorp_engine/config.py
SPLIT_LINE_CURRENCY = "AED"   # or "FC"
```

* `"AED"` — each investor credit is keyed as AED at rate 1.00, so
  `FC × rate = LC` exactly on every line. Each investor's received-currency
  equivalent is shown under the line in the validation report, for information.
* `"FC"` — each investor credit is keyed in the currency received. Both columns
  still foot, but because an uneven share has to be rounded twice, thirteen of
  July's twenty-six lines end up a fil or two away from `FC × rate`. Only use
  this if the ERP Admin confirms Orion keys FC and LC independently and does not
  re-derive LC from FC.

Flip the setting and re-run; nothing else changes.

Fixed Orion rates: USD 3.68, EUR 4.50, SAR 0.98.

---

## Checks the engine runs

* three-way match — letter total = statement amount
* split sheet dividend = letter/statement
* per-member recomputation matches the split sheet
* FC column foots to the cash debit
* entry balances, Dr = Cr
* cash roll-forward against the statement
* unknown CM code → blocker
* split-required portfolio with no split sheet → blocker
* return-of-capital on a split deal → withheld pending the rule

---

## Still outstanding from Malco

1. The complete list of split-required portfolios (from the F-2 classification)
   for `SPLIT_REQUIRED_PORTFOLIOS`.
2. The official member master — CM code → investor name → sub account.
3. The Orion entry-sheet template from the ERP Admin, if there is a prescribed
   column layout.
4. Whether the sheet must also carry the analysis CODE, or the name is enough.
5. The treatment of return-of-capital and gain on a split deal.
6. Whether Orion validates LC = FC × rate (this decides `SPLIT_LINE_CURRENCY`).

---

## Layout

```
app.py                      Streamlit app
acceptance_test.py          June, against the posted NJVs
acceptance_test_july.py     July split, against the posted NJVs
test_split_math.py          self-contained split regression, no documents needed
investcorp_engine/
  config.py                 rates, accounts, SPLIT_LINE_CURRENCY
  members.py                CM code → treatment, sub account, name
  pdftext.py                layout-preserving PDF text, pure Python
  parser.py                 statement, letters, split sheets
  booking.py                the booking rules and the checks
  analysis.py               ANL_CODE1 master, name -> code
  holdings.py               Malco / Capital M split per analysis code
  split_master.py           reads the family split workbook(s)
  efg.py                    EFG statement parser and booking rules
  orion_upload.py           the Orion JV upload file
  validation.py             the pdf
```

No Poppler, no external binaries — PDF text extraction is pure Python, so it
runs on a plain Windows install.
