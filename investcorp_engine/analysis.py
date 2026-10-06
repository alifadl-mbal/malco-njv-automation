"""Analysis master — Orion ANL_CODE1 (the upload's 'Anly1') per portfolio name.

Source: the ANL_CODE1 list Ali Fadlalla sent on 2026-09-24, extended on
2026-10-06 with the "Codes" sheet of Split_revised.xlsx (101 codes "as per Orion"). Portfolios are
still MATCHED by name (the stable key); the code is looked up from the name and
written to the upload file.

Codes are emitted exactly as stored. Two codes differ only by case and are
different portfolios in Orion:
    Investcorp5  = Credit Opportunity Portfolio VIII
    INVESTCORP5  = Baltimore and Minneapolis Industrial Portfolio
so nothing here ever case-folds a code.

To add a portfolio: add a (code, name) row below. If a statement spells a
portfolio differently from the master, add the statement spelling to ALIASES.
"""
from __future__ import annotations

from contextlib import contextmanager

from .parser import normalize_name

MASTER: list[tuple[str, str]] = [
    ("AEA007301012", "ADNOC Drilling Co PJSC"),
    ("Investcorp1", "Coastal Infill Industrial Portfolio"),
    ("XS0911024635", "SAUDI ELECTRICITY GLOBAL SUKUK COMPANY 5.06 %"),
    ("AEE01356D236", "Dubai Taxi Co PJSC"),
    ("M00138314710", "CREDIT OPPORTUNITY PORTFOLIO IV"),
    ("AEE01195A234", "Adnoc Gas PLC"),
    ("M00160765218", "FLORIDA RESIDENTIAL PORTFOLIO"),
    ("M00168424083", "2022 RESIDENTIAL PROPERTIES PORTFOLIO"),
    ("XS3065329446", "OMNIYAT SUKUK 1 LTD 8.375% 06/05/28"),
    ("Investcorp4", "US Student Housing V Portfolio"),
    ("AEE01569T248", "Talabat Holding PLC"),
    ("DGC Fund", "Dividend Gate Capital Fund"),
    ("M00229099271", "WADI AL AMAL MEDICAL CENTER"),
    ("EREITS", "Emirates REITS Sukuk 5.125 17/22"),
    ("AED000201015", "Dubai Islamic Bank PJSC"),
    ("XS2701661303", "ALPHA STAR 12.04.27 INTEREST RATE 8.375%"),
    ("FFA0001", "TESCO SS- RASMALA LONG INCOME FUND-NON VOTING SH CL D3 USD INC"),
    ("INVESTCORP11", "US STUDENT HOUSING IV PORTFOLIO"),
    ("AEE000301011", "Emaar Properties PJSC"),
    ("VISIONEXPRES", "Vision Express Building"),
    ("DGC002", "121 CRAWFORD STREET"),
    ("XS2124942595", "DAR AL-ARKAN SUKUK CO LT 6.875% 26/02/27"),
    ("INVESTCORP6", "US INDUSTRIAL GROWTH PORTFOLIO"),
    ("AEE01362P238", "Pure Health Holding PJSC"),
    ("Investcorp2", "Eastern Living Properties Portfolio"),
    ("INVESTCORP10", "JFK AIRPORT"),
    ("Investcorp5", "Credit Opportunity Portfolio VIII"),
    ("INVESTCORP7", "US LIGHT INDUSTRIAL PORTFOLIO"),
    ("GFH0002", "GFHP Link Logistics"),
    ("Investcorp3", "US Student Housing II Portfolio"),
    ("M00131791673", "US DISTRIBUTION CENTER PORTFOLIO"),
    ("AEE01110S227", "Salik Co PJSC"),
    ("AEE01268A239", "ADNOC Logistics & Services"),
    ("M00136377538", "2021 MULTIFAMILY PORTFOLIO"),
    ("AEE01657D252", "Dubai Residential REIT"),
    ("M00131794562", "2019 US INDUSTRIAL AND LOGISTICS PORTFOLIO"),
    ("AEE01198A238", "Al Ansari Financial Services P"),
    ("XS2491049651", "DAR AL-ARKAN SUKUK CO LT 7.75% 07/02/26"),
    ("XS3068748618", "RIYAD SUKUK LIMITED 6.209 % SUKUK NOTES - 2025-14.07.35"),
    ("M00184632243", "US STUDENT HOUSING PORTFOLIO"),
    ("XS2975300208", "AL RAJHI TIER 1 SUKUK LIMITED 6.25 % EURO MEDIUM TERM NOTES"),
    ("XS2311313378", "ARABIAN CENTRES SUKUK II 5.625% 07/10/26"),
    ("AEA002001013", "Aldar Properties PJSC"),
    ("INVESTCORP5", "BALTIMORE AND MINNEAPOLIS INDUSTRIAL PORTFOLIO"),
    ("DGC001", "AUREA VILLAS"),
    ("GreensandsII", "Greensands Funds II"),
    ("M00162315753", "USA RARE EARTH"),
    ("Investcorp", "India Warehouse Portfolio"),
    ("M00229099270", "US LIVING DEBT FUND"),
    ("DGC0001", "GLOBAL SHARES CAPITAL WLL"),
    ("M00170835188", "BOSTON AND MINNEAPOLIS PROPERTIES PORTFOLIO"),
    ("AED001801011", "Dubai Electricity & Water Auth"),
    ("M00155699669", "US NATIONAL INDUSTRIAL PORTFOLIO II"),
    ("XS2471859251", "ARADA SUKUK LTD 8.125% 08/06/27"),
    ("M00214974770", "GOLDEN WING"),
    ("M00180124186", "LAS VEGAS INFILL INDUSTRIAL PORTFOLIO"),
    ("AEE01487L240", "Lulu Retail Holdings PLC"),
    ("DAK1", "Dar Al Arkan Sukuk 6.75 19/25"),
    ("AEA000801018", "Abu Dhabi Islamic Bank PJSC"),
    ("AEE01370P249", "Parkin Company PJSC"),
    ("AEE01134E227", "Emirates Central Cooling Syste"),
    ("M00141485003", "SUNBELT MULTIFAMILY PORTFOLIO"),
    ("XS3101460304", "DAR AL-ARKAN SUKUK CO LT 7.250%"),
    # --- added 2026-10-06 from Split_revised.xlsx: sheet "Codes" (As per Orion)
    #     and the analysis codes in sheet "1" ---
    ('AEA001501013', 'Arabtec Holding PJSC'),
    ('M00146217828', 'M1 PROPITEER CAPITAL SUKUK 6% 04/11/23'),
    ('KYG7387H1526', 'M1 VANTAGE DATA CENTERS'),
    ('KYG7387H1609', 'RASMALA NORTH AMERICAN R.E INCOME FUND'),
    ('KYG7387W3408', 'RASMALA LONG INCOME FUND'),
    ('M00131788754', '2019 MULTIFAMILY II PORTFOLIO'),
    ('M00131791674', '2018 MULTIFAMILY PORTFOLIO'),
    ('M00131794564', '2020 SOUTHEAST INDUSTRIAL AND LOGISTICS PORTF'),
    ('M00131798105', 'FRANKFURT AND HAMBURG PROPERTIES PORTFOLIO'),
    ('M00132149087', 'JADWA SAUDI RIYAL MURABAHA - CLASS B'),
    ('M00132169431', 'GENERAL CERAMICS'),
    ('M00132169433', 'WORLD DVPMNT CO.'),
    ('M00139803351', 'US NATIONAL INDUSTRIAL PORTFOLIO'),
    ('M00142320894', 'JADWA MEZZANINE FINANCING OPPO FUN'),
    ('M00146217830', 'ARSENAL BIO'),
    ('M00146223493', 'SAUDI HOSPITALITY 8% 23/06/2024'),
    ('M00147227616', '2021 MULTIFAMILY II PORTFOLIO'),
    ('M00155701502', '1QB INFORMATION TECHNOLOGIES INC'),
    ('M00183704121', 'INNOSKEL'),
    ('M00214974768', 'FLOOS'),
    ('M00229099264', 'SAGENCE AI'),
    ('M00229099265', 'PARADROMICS'),
    ('M00229099266', 'ELVE'),
    ('M00229099267', 'COGNITIV'),
    ('M00229099272', 'VECTARA'),
    ('XS2066049219', 'DAR AL-ARKAN SUKUK CO LT 6.75% 15/02/25'),
    ('XS2089155761', 'SD INT SUKUK II LTD 6.9965% 12/03/25'),
    ('XS2100582142', 'GFH SUKUK LTD 7.5% 28/01/25'),
    ('XS2313699618', 'SOCIETE GENERALE 5.1% 01/09/23'),
    ('XS2351310482', 'OMAN SOVEREIGN SUKUK 4.875% 15/06/30'),
    ('XS2523929474', 'HAZINE MUSTESARLIGI VARL 9.758% 13/11/25'),
    ('XS2648078322', 'DAR AL-ARKAN SUKUK CO LT 8.% 25/02/29'),
    ('XS2109794417', 'QIB 20/25 6.99%'),
    ('AEE01710A255', 'Alec Holdings'),
    ('ZZ0000000055', 'Analog Inference'),
    ('ZZ0000000063', 'Good Chemistry'),
    ('ZZ0000000052', 'Innoskel'),
    ('ZZ0000000015', 'Pure Harvest Smart Farms'),
    ('ZZ0000000062', 'Stepful'),
    ('ETHIS001', 'Alternative Financing Fund'),
    ('NUQI001', 'Nuqi Holding'),
    ('NUQI002', 'Nuqi Blox'),
]

# statement spelling -> master name, for portfolios Investcorp names differently
ALIASES: dict[str, str] = {
    # "JFK Airport Terminal One Portfolio": "JFK AIRPORT",   # example — confirm the spelling
}

_CODES_BY_NAME: dict[str, set[str]] = {}
for _code, _name in MASTER:
    _CODES_BY_NAME.setdefault(normalize_name(_name), set()).add(_code)
for _alias, _name in ALIASES.items():
    _CODES_BY_NAME[normalize_name(_alias)] = _CODES_BY_NAME[normalize_name(_name)]


def code_for(portfolio_name: str) -> str | None:
    """Anly1 code for a portfolio name; None if unknown OR if the name has more
    than one code (e.g. Innoskel: M00183704121 and ZZ0000000052) — never guesses."""
    if not portfolio_name:
        return None
    codes = _CODES_BY_NAME.get(normalize_name(portfolio_name), set())
    return next(iter(codes)) if len(codes) == 1 else None


def is_ambiguous(portfolio_name: str) -> bool:
    return len(_CODES_BY_NAME.get(normalize_name(portfolio_name), set())) > 1


def case_collisions() -> list[tuple[str, ...]]:
    """Codes identical except for case (they are distinct in Orion)."""
    seen: dict[str, list[str]] = {}
    for c, _ in MASTER:
        seen.setdefault(c.lower(), []).append(c)
    return [tuple(v) for v in seen.values() if len(v) > 1]


_BY_CODE: dict[str, str] = {c: n for c, n in MASTER}


def name_for_code(code: str) -> str | None:
    """Master name for an exact Anly1 code (case-sensitive), e.g. an ISIN."""
    return _BY_CODE.get(code)


@contextmanager
def extended(codes: list[tuple[str, str]] | None):
    """Add analysis codes (e.g. an uploaded "Codes" sheet) for one run."""
    if not codes:
        yield
        return
    added_codes, added_names = [], []
    for code, name in codes:
        if code not in _BY_CODE:
            _BY_CODE[code] = name
            added_codes.append(code)
        key = normalize_name(name)
        if code not in _CODES_BY_NAME.get(key, set()):
            _CODES_BY_NAME.setdefault(key, set()).add(code)
            added_names.append((key, code))
    try:
        yield
    finally:
        for code in added_codes:
            _BY_CODE.pop(code, None)
        for key, code in added_names:
            _CODES_BY_NAME[key].discard(code)
            if not _CODES_BY_NAME[key]:
                del _CODES_BY_NAME[key]


_NOISE = {"portfolio", "the", "of", "and", "investment", "investments", "distribution",
          "calculation", "repp", "llc", "ltd", "limited", "dividend", "split"}


def code_for_fragment(fragment: str) -> str | None:
    """Code for a partial name such as a file name ("2019 US Industrial Logistics"):
    exact match first, else the ONE master name containing all its distinctive words."""
    exact = code_for(fragment)
    if exact:
        return exact
    want = {t for t in normalize_name(fragment).split() if t not in _NOISE}
    if not want:
        return None
    hits = {c for name, codes in _CODES_BY_NAME.items()
            if want <= set(name.split()) for c in codes}
    return next(iter(hits)) if len(hits) == 1 else None
