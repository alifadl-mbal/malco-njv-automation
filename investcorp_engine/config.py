"""Configuration: fixed rates, Orion account map, and entity metadata.

All values confirmed by the Malco accounts team (Aug-Sep 2026):
- FX is FIXED in Orion: USD 3.68, EUR 4.50, SAR 0.98
- Rounding residuals go to the income line
- Portfolios are matched by Analysis NAME, never by analysis code
"""

FX_RATES = {
    "USD": 3.68,
    "EUR": 4.50,
    "SAR": 0.98,
    "AED": 1.00,
}

DIVISION = "MCI"          # Malco Capital Investments
DEPARTMENT = "DXB"        # Dubai

ACCOUNTS = {
    # key:          (main account, sub account, display name)
    "investments":  ("10259", "XC0001",  "Investment through InvestCorp / Investments A/C"),
    "cash_usd":     ("10259", "XC0002",  "Investment through InvestCorp / Cash account"),
    "cash_eur":     ("10259", "XC00023", "Investment through InvestCorp / Cash balance Euro"),
    "change_cost":  ("10259", "XC0004",  "Investment through InvestCorp / Change in cost (investment returned)"),
    "div_income":   ("30711", "MCI0001", "Dividend income on FVOCI investments / Dividend received in Investcorp"),
}

CASH_BY_CURRENCY = {
    "USD": "cash_usd",
    "EUR": "cash_eur",
}

# EFG Bank (account 5089261210) — from posted NJV-2026040009/10/11 and 060003
ACCOUNTS.update({
    "efg_cash":   ("10269", "XC0002",  "Investment with EFG Bank / Cash account"),
    "efg_income": ("30711", "MCI0002", "Dividend income on FVOCI investments / Dividend received in EFG"),
    "fin_exp":    ("40840", "",        "Financial Expenses"),
})

# --------------------------------------------------------------- split line currency
#
# How the CREDIT lines of a family-split entry are denominated.
#
#   "AED"  (default) - currency AED, FC = LC, rate 1. This is how the posted
#          split entries are booked (April NJV-2026040008 = 1 USD debit +
#          25 AED credits), it keeps every line's FC x rate exactly equal to
#          its LC, and it leaves the investor balances on 10265 in AED so
#          month-end FX revaluation does not touch them. The member's USD
#          equivalent is still shown, as an informational figure under each line
#          in the validation report.
#
#   "FC"   - currency USD (the currency received), FC = the member's USD
#          share. Both columns still foot, but a per-line FC x rate can land
#          up to 2 fils away from the LC, so only use this if Orion accepts
#          FC and LC as two independently keyed inputs and does not validate
#          LC = FC x rate.
#
# Flip this once the ERP Admin confirms how Orion treats the two amounts.
SPLIT_LINE_CURRENCY = "AED"

# Company / document context
COMPANY_CODE = "135"
TRAN_CODE = "NJV"

# Tolerance (AED) for balance checks; a residual beyond this is an exception.
ROUNDING_TOLERANCE = 0.011

# ---------------------------------------------------------------------------
# Orion JV upload file (JV_UPLOAD_TEMPLATE.xls)
# ---------------------------------------------------------------------------
# The template's data cells are formatted as Text, so every value is written
# as a string. The settings below are the ones still to be confirmed against a
# file Orion has accepted — change them here, nothing else needs to move.
ORION_UPLOAD = {
    # Doc No groups lines into one NJV document. With Manual Entry = "N" Orion
    # is expected to assign the real NJV number, so this is just 1, 2, 3 ...
    "doc_no_start": 1,
    "manual_entry": "N",
    "date_format": "%d/%m/%Y",          # as Orion prints dates (17/08/2026)
    "dr": "Dr", "cr": "Cr",              # as Orion prints them in the sub-ledger
    # which lines of a portfolio entry carry Anly1: "all" or "none"
    "anly1_lines": "all",
    "amount_format": "{:.2f}",           # no thousands separators
    # FLEX_01 carries IP0001 on every posted investment NJV from 10-Apr-2026 on
    # (ZF_F_T_DETAIL_BI D_F_01); blank it here if the upload does not want it
    "flex_01": "IP0001",
}
