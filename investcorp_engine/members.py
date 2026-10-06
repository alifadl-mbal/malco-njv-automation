"""Member master for the Malco Capital split layer.

Maps each family-investor code (CM...) to its Orion posting treatment.
Derived from the posted split entries (NJV-2026040008 April,
NJV-2026070020 + 070025 July) — to be replaced by the official member
master from the accounts team.

Treatments:
  member    -> credit 10265 / <sub_account>  (Investment with Malco Capital)
  capital_m -> credit 11221 (Capital M Investments), narration tagged with the member
  to_income -> share folds into the 30711 income line (e.g. transferred to Malco)
"""

MEMBER_MASTER = {
    # code:      (treatment,   sub_account, display name for narrations)
    "CM0001": ("to_income", None,     "Malco Capital Investments LLC"),
    "CM0004": ("member",    None,     "Moosa Abullatif Mustafa"),          # zero holdings
    "CM0005": ("member",    "XI0002", "ASIA ARIF"),
    "CM0006": ("member",    "XI0003", "HAMDAN MOSTAFA"),
    "CM0007": ("member",    "XC0005", "REDHWANA ABBAS"),
    "CM0008": ("member",    "XC0046", "Heirs of Ali Abdullatif"),
    "CM0009": ("member",    "XC0007", "AL MANHAJ"),
    "CM0011": ("member",    "XC0016", "FAIZA MOSTAFA"),
    "CM0012": ("member",    "XC0008", "RAANA ABBAS"),
    "CM0013": ("member",    "XC0035", "NARGEES"),
    "CM0015": ("member",    "XC0010", "MUSTAFA ANWAR MUSTAFA"),
    "CM0016": ("member",    "XC0009", "ZAINAB AL AWADHI"),
    "CM0017": ("capital_m", None,     "Monawar Abdulla Mustafa Abdullatif"),
    "CM0018": ("member",    "XC0014", "AHMED KHOORI"),
    "CM0019": ("member",    "XC0018", "NASREEN ABDULLA"),
    "CM0020": ("member",    "XC0015", "NAIM AL HASHMI"),
    "CM0021": ("member",    "XC0017", "ANWAR MOSTAFA"),
    "CM0022": ("member",    "XC0019", "RUQAYA FIKREE"),
    "CM0024": ("member",    "QU0025", "Mrs.Jehan Mostafa"),
    "CM0025": ("to_income", None,     "Doodman (Transferred to Malco)"),
    "CM0026": ("member",    "XC0058", "Marya Abdulla Mustafa"),
    "CM0027": ("member",    "XC0033", "Fathiya Mukri"),
    "CM0028": ("member",    "XC0025", "OMRAN MOSTAFA"),
    "CM0029": ("member",    "XC0027", "NAELA MOSTAFA"),
    "CM0030": ("member",    "XC0026", "NAEM MOSTAFA"),
    "CM0031": ("member",    "XC0028", "NADA MOSTAFA"),
    "CM0032": ("member",    "XC0029", "NILOOFER MOSTAFA"),
}

MEMBERS_MAIN_ACCOUNT = "10265"       # Investment with Malco Capital
MEMBERS_MAIN_NAME = "Investment with Malco Capital"
CAPITAL_M_ACCOUNT = "11221"          # Capital M Investments
CAPITAL_M_NAME = "Capital M Investments"


# ---------------------------------------------------------------- split coverage
#
# Portfolios that MUST be split across the family investors. If a distribution
# for one of these arrives without its split sheet, the entry is withheld
# rather than silently booked at entity level (which would post the family's
# share to income).
#
# Confirmed from posted entries: 2019 US Industrial & Logistics (April
# NJV-2026040008, July NJV-2026070020+25).
# TODO: complete this list from the Capital M / Malco Capital classification
# in the F-2 FVOCI file — every Malco Capital sleeve deal belongs here.
SPLIT_REQUIRED_PORTFOLIOS = [
    "2019 US Industrial & Logistics Portfolio",
]
