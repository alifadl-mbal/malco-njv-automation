"""Malco / Capital M split of each holding, keyed by Orion analysis code (Anly1).

Source: "Split_revised.xlsx", sheet "1" (Ali Fadlalla, 2026-10-06) — one row per
holding with its analysis code and the Malco / Capital M fractions. Every share in
it agrees, to four decimals, with the 31-Dec-2025 F-2 (Total FV vs Malco FV).

A holding with a Capital M share is held partly for the family investors, so any
income or return of capital on it must be split — it never goes 100% to Malco.

Verified: the posted August 2026 return of capital on 2019 US I&L
(NJV-2026080006) credited 61% to change in cost and 39% elsewhere.

PENDING lists holdings the F-2 shows as part-owned by Capital M but that the
revised split leaves out. Until Malco confirms them they are still treated as
split (entries on them are withheld) — dropping a guard because a row is missing
would book a family share to Malco income.
"""
from __future__ import annotations

from contextlib import contextmanager

from .analysis import code_for
from .parser import normalize_name

SOURCE = "Split_revised.xlsx, sheet 1 (2026-10-06)"
AS_AT = SOURCE                       # kept for messages that cite the source
NOISE = 1e-4                         # Stepful's 0.0000143% is a rounding remnant

# (analysis code, name, counterparty, Capital M share)
SPLIT: list[tuple[str, str, str, float]] = [
    ("Investcorp2", "Eastern Living Properties Portfolio", "Investcorp", 0.0),
    ("Investcorp4", "US Student Housing V Portfolio", "Investcorp", 0.0),
    ("INVESTCORP5", "Baltimore and Minneapolis Industrial Portfolio", "Investcorp", 0.0),
    ("INVESTCORP11", "US Student Housing IV Portfolio", "Investcorp", 0.0),
    ("INVESTCORP6", "US Industrial Growth Portfolio", "Investcorp", 0.0),
    ("Investcorp3", "US Student Housing II Portfolio", "Investcorp", 0.0),
    ("INVESTCORP7", "US Light Industrial Portfolio", "Investcorp", 0.0),
    ("M00184632243", "US Student Housing Portfolio", "Investcorp", 0.0),
    ("Investcorp", "India Warehouse Portfolio", "Investcorp", 0.0),
    ("M00180124186", "Las Vegas Infill Industrial Portfolio", "Investcorp", 0.0),
    ("M00170835188", "Boston and Minneapolis Properties Portfolio", "Investcorp", 0.0),
    ("M00168424083", "2022 Residential Properties Portfolio", "Investcorp", 0.0),
    ("M00160765218", "Florida Residential Portfolio", "Investcorp", 0.0),
    ("M00155699669", "US National Industrial Portfolio II", "Investcorp", 0.0),
    ("M00147227616", "2021 Multifamily II Portfolio", "Investcorp", 0.0),
    ("M00141485003", "Sunbelt Multifamily Portfolio", "Investcorp", 0.0),
    ("M00136377538", "2021 Multifamily Portfolio", "Investcorp", 0.0),
    ("M00131794562", "2019 US Industrial & Logistics Portfolio", "Investcorp", 0.39),
    ("M00131798105", "Frankfurt and Hamburg Properties Portfolio", "Investcorp", 0.0),
    ("M00131791673", "US Distribution Center Portfolio", "Investcorp", 0.0),
    ("M00138314710", "Credit Opportunity Portfolio IV", "Investcorp", 0.0),
    ("Investcorp5", "Credit Opportunity Portfolio VIII", "Investcorp", 0.0),
    ("INVESTCORP10", "JFK Airport", "Investcorp", 0.0),
    ("M00146223493", "Saudi Hospitality", "Shuaa", 0.9583333333333334),
    ("M00229099272", "Vectara", "Greensands", 0.29999971859114016),
    ("M00155701502", "1QBit", "Greensands", 0.6992753623188406),
    ("ZZ0000000062", "Stepful - Series A", "Greensands", 1.429733085955383e-07),
    ("M00162315753", "USA Rare Earth", "Greensands", 0.7189128869565217),
    ("M00229099266", "Elve", "Greensands", 0.1815217391304349),
    ("ZZ0000000055", "Analog Inference", "Greensands", 0.29021739130434776),
    ("M00229099267", "Cogntiv", "Greensands", 0.308695652173913),
    ("M00229099265", "Paradromics", "Greensands", 0.14347826086956508),
    ("M00146217830", "Arsenal Bio", "Greensands", 0.5983400135869565),
    ("ZZ0000000063", "Good Chemistry", "Greensands", 0.49999999999999994),
    ("GreensandsII", "Greensands Funds II", "Greensands", 0.0),
    ("FFA0001", "Tesco SS", "FFA", 0.0),
    ("KYG7387H1526", "Vantage Data Centre", "FFA", 0.9466804836410154),
    ("XS3101460304", "Dar Al Arkan Sukuk 7.250% 02/07/2030", "Emirates Islamic", 1.0),
    ("M00229099270", "US Living Debt Fund I", "GFH", 0.6370772946859904),
    ("M00229099271", "Wadi Al Amal", "Dividend Gate", 0.48758056242175024),
    ("M00214974768", "Flooss Holding", "Flooss Holding", 0.499320652173913),
    ("M00132149087", "Jadwa Saudi Riyal Murabaha Fund", "Jadwa", 0.0),
    ("ETHIS001", "Alternative Financing Fund", "Ethis", 0.0),
    ("NUQI001", "Nuqi Holding", "Nuqi", 0.0),
    ("NUQI002", "Nuqi Blox", "Nuqi", 0.0),
]

# In the F-2 (31-Dec-2025) as part-owned by Capital M, absent from the revised split.
PENDING: dict[str, tuple[str, float]] = {
    "XS2124942595": ("Dar Al Arkan 20/27 6.875% (EFG)", 1_847_728.00 / 2_217_273.60),
    "XS2491049651": ("Dar Al Arkan 20/26 7.75% (EFG)", 1.0),
    "XS2471859251": ("Arada 22/27 8.125% (EFG)", 1.0),
    "XS3065329446": ("Omniyat Sukuk 1 8.375% (EFG)", 1.0),
    "Al Jubail Gateway": ("Al Jubail Gateway (Dividend Gate)", 1_877_930.14 / 3_884_664.14),
}

_BY_CODE = {code: share for code, _, _, share in SPLIT}
_BY_NAME = {normalize_name(name): share for _, name, _, share in SPLIT}
for _k, (_n, _s) in PENDING.items():
    _BY_CODE.setdefault(_k, _s)
    _BY_NAME.setdefault(normalize_name(_k), _s)


def capital_m_share(code_or_name: str) -> float:
    """Capital M share for an analysis code (exact, case-sensitive) or a name; 0 if Malco-only."""
    if not code_or_name:
        return 0.0
    if code_or_name in _BY_CODE:
        share = _BY_CODE[code_or_name]
    else:
        code = code_for(code_or_name)
        share = _BY_CODE.get(code, _BY_NAME.get(normalize_name(code_or_name), 0.0))
    return 0.0 if share < NOISE else share


def is_pending(code_or_name: str) -> bool:
    return code_or_name in PENDING or normalize_name(code_or_name) in {
        normalize_name(k) for k in PENDING}


@contextmanager
def using(table: dict[str, tuple[str, float]] | None, source: str = ""):
    """Use an uploaded Malco / Capital M table (code -> (name, share)) for one run.

    PENDING holdings stay guarded unless the uploaded table lists them explicitly."""
    global _BY_CODE, _BY_NAME, AS_AT
    if not table:
        yield
        return
    saved = (_BY_CODE, _BY_NAME, AS_AT)
    by_code = {c: sh for c, (_, sh) in table.items()}
    by_name = {normalize_name(n): sh for c, (n, sh) in table.items()}
    for k, (n, sh) in PENDING.items():
        if k not in by_code:
            by_code[k] = sh
            by_name.setdefault(normalize_name(k), sh)
    _BY_CODE, _BY_NAME, AS_AT = by_code, by_name, source or "uploaded split table"
    try:
        yield
    finally:
        _BY_CODE, _BY_NAME, AS_AT = saved


def differences(table: dict[str, tuple[str, float]]) -> list[str]:
    """How an uploaded table differs from the built-in one (for the report)."""
    base = {code: (name, share) for code, name, _, share in SPLIT}
    out = []
    for code, (name, share) in table.items():
        if code not in base:
            out.append(f"{code} {name}: new, Capital M {share:.2%}")
        elif abs(base[code][1] - share) > 1e-4:
            out.append(f"{code} {name}: Capital M {base[code][1]:.2%} → {share:.2%}")
    for code, (name, share) in base.items():
        if code not in table:
            out.append(f"{code} {name}: not in the uploaded table (built-in {share:.2%} kept)")
    return out
