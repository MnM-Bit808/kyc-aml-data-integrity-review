# Written by Claude Code — infrastructure, not analysis
"""
Sealed synthetic-data generator (CLAUDE.md Section 8.5; generator/GENERATOR_SPEC.md).

Reading this file tells you what COULD have been planted and how. It never tells you what
WAS: every hidden value is drawn at run time from config/generator_ranges.yaml with a secret
seed that is written only to sealed/answer_key.json. No drawn value appears in this file.

Usage
-----
    python generator/generate.py              # the one real run: fresh secret seed, then checks
    python generator/acceptance_checks.py     # re-run the acceptance checks on existing output

    Development only (refuses to write inside the repository):
    python generator/generate.py --dev-seed 123 --out-root <scratch dir> [--zero-defects]

The real run refuses to overwrite an existing sealed/answer_key.json, and refuses to run when
config/generator_ranges.yaml says `locked: true`, unless --force is given. Regenerating after
analysis has started would silently invalidate that analysis.

Seeds
-----
Two seeds, kept separate (GENERATOR_SPEC.md, "Two seeds").

* sampling_seed (public, config/generator_ranges.yaml) decides WHICH 50,000 accounts form the
  portfolio, and nothing else. To reproduce the sample independently on Day 2:
    1. Read HI-Small_Trans.csv with every column as a string. Account identity is the pair
       (From Bank, Account) on the sending side and (To Bank, Account.1) on the receiving side.
    2. The universe is every distinct pair appearing on either side, sorted by bank_id then
       account_id as strings.
    3. An account is laundering-involved if it is either party to any row with Is Laundering = 1.
       EVERY involved account is included (inclusion probability 1, weight 1).
    4. The remaining places are filled from the non-involved accounts, kept in that sorted order:
           idx = np.random.default_rng(sampling_seed).choice(n_non_involved,
                                                            size=50000 - n_involved,
                                                            replace=False)
       Weight for a non-involved account = n_non_involved / (50000 - n_involved).
  Consequence: laundering prevalence in the portfolio is inflated by design and is not a
  real-world rate.

* hidden_parameter_seed (secret, 128 bits from OS entropy, recorded only in the answer key)
  drives every draw from the ranges file and the placement of every planted defect.

* DEVIATION FROM THE SPEC, deliberate. The spec lists "all bulk synthetic content (names,
  addresses, ordinary event timing)" under the public seed. Taken literally, anyone could run
  this script with any secret seed, obtain the identical clean baseline, and diff it against the
  published files: every differing cell would be a planted defect, which would break the seal
  completely. So bulk content here is keyed on BOTH seeds. The sample itself (and therefore
  customer_labels.csv and sampling_weights.csv) still depends on the public seed alone, which is
  all Day 2 needs. The README consequence the spec already states still holds: until Day 10 the
  generated files are the reproducible artefact.

Interpretations a reader could reasonably question
---------------------------------------------------
1. The decoy is a DATA ELEMENT (field), not one of the four H1 dimensions. A whole dimension
   cannot be clean without contradicting the approved ranges: every record-level error type has
   a lower bound above zero, and every dimension owns at least one of them (missing values are
   completeness, malformed identifiers are validity, expired documents are timeliness, register
   mismatches are consistency), and check 9 requires planted missing values to exist. The
   proposal that introduced the decoy describes it as "a field with no missingness, no
   defaults, no staleness", which is what is implemented: one field, drawn from
   DECOY_CANDIDATES, receives no planted defect of any kind in any market.
2. H1 (market ranking) is implemented as an extra, market-skewed "generic" defect process per
   dimension at base_defect_rate x (multiplier in the worst market, 1 elsewhere). The named
   record-level errors are applied at their drawn rates uniformly across markets. The worst
   market is drawn independently per dimension.
3. H2 (gaps vs transfer_suspicious). A customer "has a data gap" if at least one mandatory value
   is missing (null OR whitespace), their beneficial-owner records are missing entirely, or an
   owner above the 25% threshold has no verification evidence. The H1 completeness process and
   record-level `missing_mandatory_field` are combined into one customer-level gap probability
   p0 = 1 - (1 - base x market factor)(1 - missing_mandatory_field); within each market the odds
   of a gap for suspicious customers are the drawn odds ratio times the odds for the rest.
4. H3 and H6 both write risk_rating = "Low"; H3 can instead default the review date to the
   onboarding date. In the H3 market the auto-fill also fills blanks, so the defaulted field is
   never missing there.
5. H4, H1 timeliness defects and expired documents are REAL-WORLD states (the data are accurate:
   the review really did not happen). Every other planted defect is a DATA error over a true
   value that the answer key records.
6. H5 duplicates stay inside the 50,000 (each duplicate is a different bank account held by the
   same company). Duplicates share owners; half share the registration number exactly, half carry
   a mis-keyed number that is not on the register.
7. The card label `card_suspicious` is written to data/raw/card_labels.csv. CLAUDE.md 8.7 says
   the label is "provided at account level" without naming a file, and it is kept away from
   customer_labels.csv so it is never unioned with transfer_suspicious.
8. uk_register_extract.csv follows the CLAUDE.md 8.6 schema exactly and so has NO customer_id: a
   real register extract is keyed by company number. It joins to customers on
   registration_number. tests/conftest.py's register fixture carries a customer_id column; the
   rule that consumes the real file must join through customers instead.
9. Every customer was onboarded before the first IBM transfer (1 September 2022), so no customer
   appears to transact before becoming a customer.

Card balances satisfy, per customer and month, exactly (all amounts in the account currency):
    statement_balance[t] = statement_balance[t-1] + purchases[t] + cash_advances[t]
                           - payments[t] - merchant_refunds[t] + refund_requests[t]
where purchases are not stored as events (CLAUDE.md 8.7) but are always >= 0, and a
refund_request is paid out in full. No interest or fees are modelled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from faker import Faker

# --------------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[1]
RANGES_PATH = REPO / "config" / "generator_ranges.yaml"
POLICY_PATH = REPO / "config" / "policy.yaml"
IBM_TRANS_PATH = REPO / "data" / "raw" / "HI-Small_Trans.csv"
IBM_PATTERNS_PATH = REPO / "data" / "raw" / "HI-Small_Patterns.txt"
KEY_RELPATH = Path("sealed") / "answer_key.json"
RAW_OUTPUTS = ["customers.csv", "beneficial_owners.csv", "uk_register_extract.csv",
               "customer_changes.csv", "card_statements.csv", "card_activity.csv",
               "card_labels.csv"]
PROCESSED_OUTPUTS = ["customer_labels.csv", "sampling_weights.csv",
                     "sampled_transactions.parquet"]
# Planted owners, register discrepancies and card typologies add or remove rows in these files,
# so their row counts carry information about hidden draws. The real run does not print them.
ROW_COUNT_WITHHELD = {"beneficial_owners.csv", "uk_register_extract.csv", "card_activity.csv"}

# --------------------------------------------------------------------------------------------
# Public design constants (CLAUDE.md / spec). None of these is a drawn value.
# --------------------------------------------------------------------------------------------
MARKETS = ("UK", "AU", "JP")
MARKET_CUSTOMERS = {"UK": 21000, "AU": 18000, "JP": 11000}          # CLAUDE.md 8.4
MARKET_BUSINESS_SHARE = {"UK": 0.25, "AU": 0.15, "JP": 0.12}        # CLAUDE.md 8.4
N_CUSTOMERS = sum(MARKET_CUSTOMERS.values())
LOCALE = {"UK": "en_GB", "AU": "en_AU", "JP": "ja_JP"}
CURRENCY = {"UK": "GBP", "AU": "AUD", "JP": "JPY"}
FX = {"UK": 1.0, "AU": 1.9, "JP": 190.0}      # rough scale of amounts, GBP-equivalent

IBM_HEADER = ["Timestamp", "From Bank", "Account", "To Bank", "Account", "Amount Received",
              "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format",
              "Is Laundering"]
IBM_COLUMNS = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Received",
               "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format",
               "Is Laundering"]

ONBOARD_START = np.datetime64("2008-01-01", "D")
ONBOARD_END = np.datetime64("2022-08-31", "D")    # before the first IBM transfer

RATINGS = np.array(["High", "Medium", "Low"], dtype=object)
RISK_MIX_IND = (0.07, 0.28, 0.65)
RISK_MIX_BIZ = (0.15, 0.45, 0.40)
RISK_MIX_PEP = (0.75, 0.25, 0.00)
RISK_MIX_HIGH_RISK_INDUSTRY = (0.45, 0.45, 0.10)

POSTCODE_RE = {"UK": r"^[A-Z]{1,2}[0-9][A-Z0-9]? [0-9][A-Z]{2}$",
               "AU": r"^[0-9]{4}$",
               "JP": r"^[0-9]{3}-[0-9]{4}$"}
REGNUM_RE = r"^SYN-(UK|AU|JP)-[0-9]{7}$"
VALID_ID_DOC_TYPES = ("passport", "drivers_licence", "national_id", "residence_card")
VALID_PEP = ("Y", "N")
ID_DOC_MIX = {"UK": (("passport", 0.60), ("drivers_licence", 0.40)),
              "AU": (("passport", 0.45), ("drivers_licence", 0.55)),
              "JP": (("national_id", 0.40), ("drivers_licence", 0.35), ("passport", 0.15),
                     ("residence_card", 0.10))}
BO_EVIDENCE = {"UK": ("passport", "drivers_licence", "electronic_id_check"),
               "AU": ("passport", "drivers_licence", "electronic_id_check"),
               "JP": ("passport", "drivers_licence", "national_id")}

# Values pandas reads as missing by default. Natural text must never equal one of these.
PANDAS_NA_TOKENS = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan",
                    "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a",
                    "nan", "null"}

# The decoy is drawn from these fields (see docstring, interpretation 1).
DECOY_CANDIDATES = ("date_of_birth", "postcode", "pep_flag", "id_doc_type")

# Mandatory fields a completeness gap can hit, with relative weights.
GAP_FIELDS_IND = (("risk_rating", 1.0), ("last_periodic_review_date", 1.0),
                  ("id_doc_type", 0.5), ("id_doc_expiry", 1.0), ("date_of_birth", 0.5),
                  ("address_line", 0.6), ("city", 0.3), ("postcode", 0.6),
                  ("occupation_text", 1.5), ("purpose_of_account_text", 1.5),
                  ("pep_flag", 0.8), ("info_last_refreshed_date", 0.8))
GAP_FIELDS_BIZ = (("risk_rating", 1.0), ("last_periodic_review_date", 1.0),
                  ("registration_number", 0.6), ("address_line", 0.6), ("city", 0.3),
                  ("postcode", 0.6), ("industry_text", 1.2),
                  ("purpose_of_account_text", 1.5), ("pep_flag", 0.8),
                  ("info_last_refreshed_date", 0.8), ("bo_records", 0.7),
                  ("bo_verification", 1.2))
GAP_COUNT_CHOICES = (1, 2, 3)
GAP_COUNT_PROBS = (0.75, 0.18, 0.07)

INVALID_RISK_CODES = ("Unrated", "TBC", "Hgh", "Med", "HIGH", "low")
INVALID_PEP_CODES = ("U", "?", "Yes", "0", "X")
INVALID_ID_DOC_CODES = ("pasport", "DL", "other", "ID card", "unknown")

CHANGE_RATES = (("address", 0.10, 0.10), ("name", 0.02, 0.02), ("occupation", 0.05, 0.0),
                ("ownership", 0.0, 0.12), ("pep_status", 0.004, 0.004))   # per year: ind, biz

# Beneficial-ownership templates (percentages) and weights. Every template satisfies
# total + largest > 100, so duplicating the largest owner always breaks 100%.
BO_TEMPLATES = (((100,), 0.22), ((50, 50), 0.12), ((60, 40), 0.06), ((70, 30), 0.05),
                ((75, 25), 0.05), ((80, 20), 0.04), ((51, 49), 0.03), ((50, 25, 25), 0.05),
                ((40, 30, 30), 0.04), ((34, 33, 33), 0.04), ((60, 20, 20), 0.04),
                ((45, 35, 20), 0.03), ((25, 25, 25, 25), 0.04), ((40, 20, 20, 20), 0.03),
                ((30, 30, 20, 20), 0.03), ((20, 20, 20, 20, 20), 0.02),
                ((30, 20, 20, 15), 0.02), ((35, 25, 15, 15), 0.02), ((22, 22, 22, 22), 0.02),
                ((45, 25, 10), 0.01))

# --------------------------------------------------------------------------------------------
# Free-text vocabularies (canonical value: variants). Module 1b standardises these.
# --------------------------------------------------------------------------------------------
OCCUPATIONS = {
    "Software Engineer": ["software developer", "programmer", "S/W engineer", "IT developer",
                          "developer", "SWE"],
    "Teacher": ["school teacher", "secondary school teacher", "primary teacher", "educator",
                "tchr"],
    "Nurse": ["registered nurse", "RN", "staff nurse", "nursing"],
    "Accountant": ["chartered accountant", "CPA", "accountancy", "acct"],
    "Doctor": ["GP", "physician", "medical doctor", "surgeon"],
    "Lawyer": ["solicitor", "barrister", "attorney", "legal counsel"],
    "Sales Manager": ["sales mgr", "head of sales", "area sales manager"],
    "Retail Assistant": ["shop assistant", "sales assistant", "retail worker", "cashier",
                         "store associate"],
    "Civil Servant": ["government employee", "public servant", "civil service", "govt officer"],
    "Student": ["university student", "undergraduate", "postgraduate student",
                "full-time student"],
    "Retired": ["retiree", "pensioner", "retd", "retired (pension)"],
    "Self-employed": ["self employed", "sole trader", "freelancer", "own business"],
    "Company Director": ["director", "managing director", "business owner", "company owner"],
    "Electrician": ["electrical tradesman", "sparky", "licensed electrician"],
    "Plumber": ["plumbing", "plumber & gas fitter", "gas engineer"],
    "Chef": ["cook", "head chef", "sous chef", "kitchen staff"],
    "Driver": ["delivery driver", "HGV driver", "taxi driver", "truck driver", "courier"],
    "Engineer": ["mechanical engineer", "civil engineer", "engineering"],
    "Consultant": ["management consultant", "business consultant", "advisor"],
    "Pharmacist": ["chemist", "pharmacy", "dispensing pharmacist"],
    "Police Officer": ["police", "police constable", "law enforcement"],
    "Architect": ["architectural designer", "architect (RIBA)"],
    "Farmer": ["agriculture", "farm owner", "grazier", "dairy farmer"],
    "Real Estate Agent": ["estate agent", "realtor", "property agent", "letting agent"],
    "Financial Analyst": ["analyst", "finance analyst", "investment analyst"],
    "Marketing Manager": ["marketing", "marketing mgr", "head of marketing", "brand manager"],
    "Homemaker": ["housewife", "stay at home parent", "home duties", "househusband"],
    "Unemployed": ["not working", "job seeker", "between jobs"],
    "Designer": ["graphic designer", "UX designer", "interior designer", "web designer"],
    "Builder": ["construction worker", "tradesman", "labourer", "bricklayer"],
    "Mechanic": ["motor mechanic", "auto technician", "car mechanic"],
    "Office Worker": ["office employee", "administrator", "admin assistant", "clerk",
                      "company employee", "salaryman"],
    "Part-time Worker": ["part timer", "casual worker", "part-time"],
    "Care Worker": ["carer", "support worker", "aged care worker"],
    "IT Manager": ["IT mgr", "head of IT", "technology manager"],
    "Hospitality Worker": ["waiter", "waitress", "bar staff", "barista", "hotel staff"],
}
OCC_ROMAJI = {"Office Worker": ["kaishain"], "Civil Servant": ["koumuin"],
              "Self-employed": ["jieigyou"], "Homemaker": ["shufu"], "Student": ["gakusei"],
              "Part-time Worker": ["paato", "arubaito"], "Retired": ["nenkin seikatsu"]}
OCC_WEIGHT_JP = {"Office Worker": 4.0, "Part-time Worker": 2.0, "Civil Servant": 1.5}

INDUSTRIES = {
    "Construction": ["building contractor", "construction services", "builders", "civil works"],
    "Retail": ["retail trade", "shop", "retail store", "e-commerce retail"],
    "Hospitality": ["restaurant", "cafe", "hotel", "food & beverage", "F&B"],
    "Professional Services": ["consulting", "consultancy", "advisory services",
                              "prof. services"],
    "Technology": ["IT services", "software", "tech", "IT consultancy", "SaaS"],
    "Manufacturing": ["manufacturer", "mfg", "production", "factory"],
    "Transport & Logistics": ["logistics", "freight", "haulage", "courier services",
                              "transport"],
    "Real Estate": ["property", "property management", "real estate agency", "lettings"],
    "Healthcare": ["medical practice", "clinic", "health services", "dental practice"],
    "Wholesale Trade": ["wholesale", "wholesaler", "distribution", "import & distribution"],
    "Financial Services": ["finance", "financial advisory", "insurance broker",
                           "accounting services"],
    "Agriculture": ["farming", "agri", "horticulture", "livestock"],
    "Education": ["training provider", "tutoring", "education services"],
    "Media & Entertainment": ["media", "film production", "events", "entertainment"],
    "Automotive": ["car dealer", "motor trade", "auto repairs", "vehicle sales"],
    "Cleaning Services": ["cleaning", "commercial cleaning", "janitorial"],
    "Money Services Business": ["money transfer", "currency exchange", "bureau de change",
                                "remittance", "MSB"],
    "Precious Metals & Jewellery": ["jewellery", "jeweller", "gold dealer", "bullion"],
    "Gambling": ["betting", "bookmaker", "gaming", "casino"],
    "Import/Export": ["import export", "trading company", "general trading", "import & export"],
}
INDUSTRY_WEIGHTS = {"Construction": 9, "Retail": 10, "Hospitality": 8,
                    "Professional Services": 11, "Technology": 8, "Manufacturing": 6,
                    "Transport & Logistics": 6, "Real Estate": 6, "Healthcare": 5,
                    "Wholesale Trade": 5, "Financial Services": 4, "Agriculture": 3,
                    "Education": 3, "Media & Entertainment": 3, "Automotive": 3,
                    "Cleaning Services": 3, "Money Services Business": 1.5,
                    "Precious Metals & Jewellery": 1.5, "Gambling": 1, "Import/Export": 3}
HIGH_RISK_INDUSTRIES = ("Money Services Business", "Precious Metals & Jewellery", "Gambling",
                        "Import/Export")

PURPOSES_IND = {
    "Everyday spending": ["daily purchases", "general spending", "day to day expenses",
                          "everyday use", "shopping"],
    "Travel": ["overseas travel", "holidays", "travel & dining", "travel"],
    "Online shopping": ["online purchases", "internet shopping", "e-commerce"],
    "Rewards and points": ["rewards", "air miles", "points", "cashback"],
    "Building credit history": ["credit building", "build credit", "credit history"],
    "Large purchases": ["big ticket items", "home improvements", "furniture"],
    "Balance transfer": ["transfer balance", "consolidate debt", "debt consolidation"],
}
PURPOSES_IND_WEIGHTS = (30, 18, 16, 14, 8, 8, 6)
PURPOSES_BIZ = {
    "Business expenses": ["company expenses", "business spend", "operating expenses", "opex"],
    "Supplier payments": ["paying suppliers", "vendor payments", "supplier invoices"],
    "Employee expenses": ["staff expenses", "T&E", "travel and expenses", "employee travel"],
    "Fuel and fleet": ["fuel", "fleet costs", "vehicle expenses"],
    "Inventory purchases": ["stock purchases", "inventory", "purchasing stock"],
    "Advertising": ["marketing spend", "ads", "online advertising"],
}
PURPOSES_BIZ_WEIGHTS = (32, 22, 18, 10, 12, 6)

SECTOR_WORDS = {
    "Construction": ["Construction", "Building", "Developments", "Contractors"],
    "Retail": ["Retail", "Stores", "Supplies", "Trading"],
    "Hospitality": ["Catering", "Hospitality", "Restaurants", "Kitchens"],
    "Professional Services": ["Consulting", "Associates", "Partners", "Advisory", "Management"],
    "Technology": ["Technologies", "Software", "Digital", "Solutions", "Systems"],
    "Manufacturing": ["Manufacturing", "Engineering", "Industries", "Fabrications"],
    "Transport & Logistics": ["Logistics", "Freight", "Haulage", "Transport"],
    "Real Estate": ["Properties", "Estates", "Property Management", "Lettings"],
    "Healthcare": ["Healthcare", "Medical", "Clinics", "Care Services"],
    "Wholesale Trade": ["Distribution", "Wholesale", "Supplies", "Trading"],
    "Financial Services": ["Financial Services", "Capital", "Investments", "Insurance Services"],
    "Agriculture": ["Farms", "Agriculture", "Produce"],
    "Education": ["Training", "Education", "Learning", "Tutors"],
    "Media & Entertainment": ["Media", "Productions", "Events", "Studios"],
    "Automotive": ["Motors", "Automotive", "Vehicle Services"],
    "Cleaning Services": ["Cleaning Services", "Cleaning", "Facilities Management"],
    "Money Services Business": ["Money Transfer", "Exchange", "Remittance Services", "FX"],
    "Precious Metals & Jewellery": ["Jewellers", "Gold", "Bullion", "Precious Metals"],
    "Gambling": ["Gaming", "Betting", "Leisure"],
    "Import/Export": ["International Trading", "Imports", "Global Trading", "Import Export"],
}
JP_SECTOR_WORDS = {
    "Construction": ["建設", "工務店", "建工"], "Retail": ["商店", "ストア", "販売"],
    "Hospitality": ["フーズ", "飲食", "ホテル"],
    "Professional Services": ["コンサルティング", "総研", "パートナーズ"],
    "Technology": ["システム", "ソフト", "テクノロジー", "情報技術"],
    "Manufacturing": ["製作所", "工業", "精密"], "Transport & Logistics": ["運輸", "物流", "運送"],
    "Real Estate": ["不動産", "地所", "ハウジング"],
    "Healthcare": ["メディカル", "医療サービス", "ヘルスケア"],
    "Wholesale Trade": ["商事", "物産", "卸"],
    "Financial Services": ["ファイナンス", "保険サービス", "キャピタル"],
    "Agriculture": ["農産", "ファーム", "水産"], "Education": ["教育", "ゼミナール", "ラーニング"],
    "Media & Entertainment": ["企画", "プロダクション", "メディア"],
    "Automotive": ["自動車", "モータース", "オート"],
    "Cleaning Services": ["クリーンサービス", "ビルメンテナンス"],
    "Money Services Business": ["両替", "送金サービス", "マネーサービス"],
    "Precious Metals & Jewellery": ["貴金属", "宝飾", "ゴールド"],
    "Gambling": ["遊技", "アミューズメント", "ゲーミング"],
    "Import/Export": ["貿易", "インターナショナル", "トレーディング"],
}
UK_SUFFIXES = (("Limited", 0.35), ("Ltd", 0.40), ("PLC", 0.05), ("LLP", 0.06), ("& Co", 0.04),
               ("Ltd.", 0.03), ("Group Ltd", 0.07))
AU_SUFFIXES = (("Pty Ltd", 0.65), ("Pty. Ltd.", 0.08), ("Pty Limited", 0.12), ("Ltd", 0.08),
               ("Holdings Pty Ltd", 0.07))
LEGAL_TOKENS = {"ltd", "limited", "plc", "llp", "pty", "proprietary", "co", "company",
                "public", "liability", "partnership", "l", "p"}
SUFFIX_ALTERNATIVES = {"Limited": ["Ltd", "Ltd.", "LTD", ""], "Ltd": ["Limited", "Ltd.", "LTD", ""],
                       "Ltd.": ["Ltd", "Limited", ""], "PLC": ["plc", "P.L.C.",
                                                           "Public Limited Company"],
                       "LLP": ["L.L.P.", "Limited Liability Partnership"],
                       "& Co": ["and Co", "& Company", "& Co."],
                       "Group Ltd": ["Group Limited", "Group"]}
ABBREVIATIONS = (("International", "Intl"), ("Services", "Svcs"), ("Engineering", "Eng"),
                 ("Holdings", "Hldgs"), ("Management", "Mgmt"), ("Company", "Co"),
                 ("Associates", "Assocs"), ("Construction", "Constr"), ("Technologies", "Tech"),
                 ("Properties", "Props"), ("Trading", "Trdg"), ("Solutions", "Solns"),
                 ("Group", "Grp"), ("Manufacturing", "Mfg"), ("Distribution", "Distn"),
                 ("Industries", "Inds"), ("Developments", "Devs"), ("Financial", "Fin"),
                 ("Estates", "Ests"), ("Productions", "Prodns"), ("Supplies", "Supp"),
                 ("Motors", "Mtrs"), ("Contractors", "Contr"), ("Investments", "Invs"),
                 ("Consulting", "Consultancy"), ("Logistics", "Logistic"))
STREET_ABBREV = (("Street", "St"), ("Road", "Rd"), ("Avenue", "Ave"), ("Lane", "Ln"),
                 ("Drive", "Dr"), ("Close", "Cl"), ("Court", "Ct"), ("Place", "Pl"),
                 ("Gardens", "Gdns"), ("Crescent", "Cres"), ("Square", "Sq"),
                 ("Terrace", "Terr"), ("Grove", "Gr"), ("Parade", "Pde"), ("Highway", "Hwy"))
FULLWIDTH = str.maketrans("0123456789-", "０１２３４５６７８９－")

# Card layer design constants
SPEND_MEDIAN = {"Individual": 900.0, "Business": 4000.0}
SPEND_SIGMA = {"Individual": 0.7, "Business": 0.9}
SEASON = {"2025-11": 1.10, "2025-12": 1.25, "2026-01": 0.90}
N_MERCHANTS = 8000


# --------------------------------------------------------------------------------------------
# Random streams
# --------------------------------------------------------------------------------------------
def _tag(name: str) -> int:
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big")


class Streams:
    """Named, independent random streams, so adding a draw in one place never shifts another."""

    def __init__(self, sampling_seed: int, hidden_seed: int):
        self.sampling_seed = int(sampling_seed)
        self.hidden_seed = int(hidden_seed)

    def sampling(self) -> np.random.Generator:
        return np.random.default_rng(self.sampling_seed)

    def bulk(self, name: str) -> np.random.Generator:
        return np.random.default_rng(
            np.random.SeedSequence([self.sampling_seed, self.hidden_seed, _tag("bulk:" + name)]))

    def hidden(self, name: str) -> np.random.Generator:
        return np.random.default_rng(
            np.random.SeedSequence([self.hidden_seed, _tag("hidden:" + name)]))

    def faker(self, locale: str, name: str, hidden: bool = False) -> Faker:
        rng = self.hidden("faker:" + name) if hidden else self.bulk("faker:" + name)
        f = Faker(locale)
        f.seed_instance(int(rng.integers(0, 2 ** 62)))
        return f


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------
def td(n) -> np.timedelta64:
    return np.timedelta64(int(n), "D")


def iso(d) -> str | None:
    if d is None or pd.isna(d):
        return None
    return str(np.datetime64(d, "D"))


def iso_array(arr) -> np.ndarray:
    out = np.empty(len(arr), dtype=object)
    for i, d in enumerate(arr):
        out[i] = None if np.isnat(d) else str(d)
    return out


def pick(seq, rng):
    return seq[int(rng.integers(len(seq)))]


def pick_weighted(pairs, rng):
    vals = [p[0] for p in pairs]
    w = np.array([p[1] for p in pairs], dtype=float)
    return vals[int(rng.choice(len(vals), p=w / w.sum()))]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_text(s: str, fallback: str) -> str:
    """Natural text must never collide with a pandas missing-value token."""
    if s is None or s.strip() in PANDAS_NA_TOKENS or s.strip() == "":
        return fallback
    return s


def typo(s: str, rng) -> str:
    words = s.split(" ")
    cand = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha()]
    if not cand:
        return s
    i = cand[int(rng.integers(len(cand)))]
    w = words[i]
    j = int(rng.integers(1, len(w) - 1))
    op = int(rng.integers(3))
    if op == 0:
        w = w[:j] + w[j + 1:]
    elif op == 1:
        w = w[:j] + w[j] + w[j:]
    else:
        w = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
    words[i] = w
    return " ".join(words)


def render_free_text(canon: str, variants: list, rng, romaji: list | None = None) -> str:
    """Messy but meaningful free text. The canonical value is kept as truth."""
    if romaji and rng.random() < 0.15:
        s = pick(romaji, rng)
    elif rng.random() < 0.55 or not variants:
        s = canon
    else:
        s = pick(variants, rng)
    w = rng.random()
    if w < 0.10:
        s = typo(s, rng)
    elif w < 0.18:
        s = s.upper()
    elif w < 0.28:
        s = s.lower()
    elif w < 0.33:
        s = s + "."
    elif w < 0.36:
        s = "  " + s
    elif w < 0.39:
        s = s.replace(" ", "  ", 1) if " " in s else s + " "
    return safe_text(s, canon)


def norm_bizname(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    toks = [t for t in s.split() if t not in LEGAL_TOKENS and t != "and"]
    return " ".join(toks)


def norm_jp_bizname(s: str) -> str:
    for t in ("株式会社", "有限会社", "合同会社", "(株)", "㈱", "(有)", " ", "　"):
        s = s.replace(t, "")
    return s


# ---- name / address variant machinery (natural messiness and H5 share it) -----------------
def _suffix_of(name: str):
    for suf in sorted(SUFFIX_ALTERNATIVES, key=len, reverse=True):
        if name.endswith(" " + suf):
            return suf
    return None


def variant_legal_suffix(name: str, rng):
    suf = _suffix_of(name)
    if suf is None:
        return None
    alt = pick(SUFFIX_ALTERNATIVES[suf], rng)
    base = name[: -len(suf) - 1]
    return (base + (" " + alt if alt else "")).strip()


def variant_abbreviation(name: str, rng):
    opts = []
    for full, short in ABBREVIATIONS:
        if re.search(r"\b" + re.escape(full) + r"\b", name):
            opts.append((full, short))
    if " & " in name:
        opts.append((" & ", " and "))
    if " and " in name:
        opts.append((" and ", " & "))
    if not opts:
        return None
    full, short = pick(opts, rng)
    if full.strip() in ("&", "and"):
        return name.replace(full, short, 1)
    return re.sub(r"\b" + re.escape(full) + r"\b", short, name, count=1)


def variant_punctuation(name: str, rng):
    opts = []
    suf = _suffix_of(name)
    if suf:
        opts.append("comma_before_suffix")
    if "-" in name:
        opts.append("hyphen_to_space")
    if "." in name:
        opts.append("drop_periods")
    opts += ["double_space", "trailing_period"]
    op = pick(opts, rng)
    if op == "comma_before_suffix":
        return name[: -len(suf) - 1] + ", " + suf
    if op == "hyphen_to_space":
        return name.replace("-", " ", 1)
    if op == "drop_periods":
        return name.replace(".", "")
    if op == "double_space":
        i = name.find(" ")
        return name if i < 0 else name[:i] + "  " + name[i + 1:]
    return name + "."


def variant_address(addr: str, rng):
    opts = []
    for full, short in STREET_ABBREV:
        if re.search(r"\b" + full + r"\b", addr):
            opts.append(("abbrev", full, short))
        if re.search(r"\b" + short + r"\b", addr):
            opts.append(("expand", short, full))
    m = re.match(r"^((?:Flat|Unit|Studio|Apartment|Suite) \w+),? (.+)$", addr)
    if m:
        opts.append(("reorder", m.group(1), m.group(2)))
    if "," in addr:
        opts.append(("drop_commas", None, None))
    opts.append(("upper", None, None))
    kind, a, b = pick(opts, rng)
    if kind == "abbrev":
        return re.sub(r"\b" + a + r"\b", b, addr, count=1)
    if kind == "expand":
        return re.sub(r"\b" + a + r"\b", b, addr, count=1)
    if kind == "reorder":
        return f"{b}, {a}"
    if kind == "drop_commas":
        return addr.replace(",", "")
    return addr.upper()


def variant_jp_address(addr: str, rng):
    if rng.random() < 0.5:
        m = re.search(r"(\d+)丁目(\d+)番(\d+)号", addr)
        if m:
            return addr.replace(m.group(0), f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return addr.translate(FULLWIDTH)


def natural_business_variant(name: str, market: str, rng) -> str:
    if market == "JP":
        u = rng.random()
        if "株式会社" in name and u < 0.6:
            return name.replace("株式会社", "(株)" if rng.random() < 0.6 else "㈱")
        for form in ("株式会社", "合同会社"):
            if name.startswith(form):
                return name[len(form):] + form
            if name.endswith(form):
                return form + name[: -len(form)]
        return name
    u = rng.random()
    if u < 0.35:
        return name.upper()
    if u < 0.75:
        return variant_legal_suffix(name, rng) or name.upper()
    return variant_punctuation(name, rng)


# --------------------------------------------------------------------------------------------
# Configuration and parameter draws
# --------------------------------------------------------------------------------------------
def load_config():
    with open(RANGES_PATH, encoding="utf-8") as fh:
        ranges = yaml.safe_load(fh)
    with open(POLICY_PATH, encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)
    return ranges, policy


def _draw(spec: dict, rng):
    if spec["dist"] == "uniform":
        return float(rng.uniform(float(spec["low"]), float(spec["high"])))
    if spec["dist"] == "uniform_int":                      # inclusive of both ends
        return int(rng.integers(int(spec["low"]), int(spec["high"]) + 1))
    raise ValueError(f"unknown distribution {spec['dist']!r}")


def _choice_from_spec(value: str, default: tuple, rng) -> str:
    if value == "drawn_at_random":
        return default[int(rng.integers(len(default)))]
    m = re.fullmatch(r"drawn_at_random_from\s*\[(.+)\]", value.strip())
    if not m:
        raise ValueError(f"cannot parse choice spec {value!r}")
    opts = [x.strip() for x in m.group(1).split(",")]
    return opts[int(rng.integers(len(opts)))]


def draw_parameters(ranges: dict, rng) -> dict:
    """Every hidden value, drawn once, keyed by its dotted path in generator_ranges.yaml."""
    P = {}
    h1 = ranges["H1"]
    for d in h1["dimensions"]:
        P[f"H1.base_defect_rate.{d}"] = _draw(h1["base_defect_rate"], rng)
        P[f"H1.worst_market_multiplier.{d}"] = _draw(h1["worst_market_multiplier"], rng)
        P[f"H1.worst_market.{d}"] = MARKETS[int(rng.integers(len(MARKETS)))]
    h2 = ranges["H2"]
    P["H2.is_null"] = bool(rng.random() < float(h2["null_probability"]))
    P["H2.odds_ratio_if_not_null"] = _draw(h2["odds_ratio_if_not_null"], rng)
    P["H2.effective_odds_ratio"] = 1.0 if P["H2.is_null"] else P["H2.odds_ratio_if_not_null"]
    h3 = ranges["H3"]
    P["H3.present"] = bool(rng.random() < float(h3["present_probability"]))
    P["H3.affected_share"] = _draw(h3["affected_share"], rng)
    P["H3.market"] = _choice_from_spec(h3["market"], MARKETS, rng)
    P["H3.field"] = _choice_from_spec(h3["field"], (), rng)
    P["H4.extra_stale_prob_per_tenure_year"] = _draw(ranges["H4"]["extra_stale_prob_per_tenure_year"], rng)
    h5 = ranges["H5"]
    P["H5.duplicate_clusters"] = _draw(h5["duplicate_clusters"], rng)
    P["H5.cluster_size"] = [_draw(h5["cluster_size"], rng) for _ in range(P["H5.duplicate_clusters"])]
    P["H6.share_of_suspicious_forced_low"] = _draw(ranges["H6"]["share_of_suspicious_forced_low"], rng)
    h7 = ranges["H7"]
    P["H7.baseline_neglect_rate"] = _draw(h7["baseline_neglect_rate"], rng)
    P["H7.concentration_multiplier"] = _draw(h7["concentration_multiplier"], rng)
    P["H7.concentrated_market"] = _choice_from_spec(h7["concentrated_market"], MARKETS, rng)
    P["H8.unlabelled_share_of_truly_suspicious"] = _draw(ranges["H8"]["unlabelled_share_of_truly_suspicious"], rng)
    dec = ranges["decoy"]
    P["decoy.clean_dimension"] = (_choice_from_spec(dec["clean_dimension"], DECOY_CANDIDATES, rng)
                                  if dec.get("enabled", False) else None)
    for typ, spec in ranges["card_layer"]["typology_prevalence"].items():
        P[f"card_layer.typology_prevalence.{typ}"] = _draw(spec, rng)
    for err, spec in ranges["record_level_errors"].items():
        P[f"record_level_errors.{err}"] = _draw(spec, rng)
    return P


def zero_out(P: dict) -> dict:
    """Development only: every planting mechanism switched off, for testing the clean baseline."""
    Z = dict(P)
    for k in list(Z):
        if k.startswith("H1.base_defect_rate") or k.startswith("record_level_errors") \
                or k.startswith("card_layer.typology_prevalence"):
            Z[k] = 0.0
    Z["H2.effective_odds_ratio"] = 1.0
    Z["H3.present"] = False
    Z["H4.extra_stale_prob_per_tenure_year"] = 0.0
    Z["H5.duplicate_clusters"] = 0
    Z["H5.cluster_size"] = []
    Z["H6.share_of_suspicious_forced_low"] = 0.0
    Z["H7.baseline_neglect_rate"] = 0.0
    return Z


# --------------------------------------------------------------------------------------------
# IBM data and sampling (public seed only)
# --------------------------------------------------------------------------------------------
def load_ibm(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        header = fh.readline().rstrip("\r\n").split(",")
    if header != IBM_HEADER:
        raise SystemExit("IBM header differs from the expected 11 columns - refusing to guess.")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    if list(df.columns) != IBM_COLUMNS:
        raise SystemExit("pandas did not name the receiving account column 'Account.1'.")
    for c in ("From Bank", "Account", "To Bank", "Account.1"):
        if (df[c].str.len() == 0).any():
            raise SystemExit(f"empty identifier in column {c!r}")
    if not df["Is Laundering"].isin(["0", "1"]).all():
        raise SystemExit("Is Laundering holds values other than 0/1")
    df["Is Laundering"] = (df["Is Laundering"] == "1").astype("int8")
    for c in ("Amount Received", "Amount Paid"):
        df[c] = pd.to_numeric(df[c], errors="raise")
    return df


def sample_portfolio(trans: pd.DataFrame, sampling_seed: int, n_target: int):
    """Returns (sample frame, sampled transactions). Depends on the public seed only."""
    sep = "\x1f"
    fkey = trans["From Bank"] + sep + trans["Account"]
    tkey = trans["To Bank"] + sep + trans["Account.1"]
    universe = pd.DataFrame({
        "bank_id": pd.concat([trans["From Bank"], trans["To Bank"]], ignore_index=True),
        "account_id": pd.concat([trans["Account"], trans["Account.1"]], ignore_index=True),
    }).drop_duplicates()
    universe = universe.sort_values(["bank_id", "account_id"], kind="mergesort").reset_index(drop=True)
    # The pair is the account key. Fail loudly if it is not unique or not well formed.
    if universe.duplicated(["bank_id", "account_id"]).any():
        raise SystemExit("(bank_id, account_id) is not unique in the account universe")
    ukey = universe["bank_id"] + sep + universe["account_id"]
    lab = trans["Is Laundering"].to_numpy() == 1
    in_from = ukey.isin(pd.Index(fkey[lab].unique())).to_numpy()
    in_to = ukey.isin(pd.Index(tkey[lab].unique())).to_numpy()
    involved = in_from | in_to
    role = np.select([in_from & in_to, in_from, in_to], ["both", "sender", "receiver"], "none")
    inv_idx = np.flatnonzero(involved)
    clean_idx = np.flatnonzero(~involved)
    if len(inv_idx) > n_target:
        raise SystemExit("more involved accounts than portfolio places")
    k = n_target - len(inv_idx)
    rng = np.random.default_rng(int(sampling_seed))
    pick_idx = rng.choice(len(clean_idx), size=k, replace=False)
    chosen = np.sort(np.concatenate([inv_idx, clean_idx[np.sort(pick_idx)]]))
    s = universe.iloc[chosen].reset_index(drop=True)
    s["transfer_suspicious"] = involved[chosen].astype(int)
    s["suspicious_role"] = role[chosen]
    s["stratum"] = np.where(s["transfer_suspicious"] == 1, "laundering_involved", "not_involved")
    p_clean = k / len(clean_idx)
    s["inclusion_probability"] = np.where(s["transfer_suspicious"] == 1, 1.0, p_clean)
    s["sampling_weight"] = 1.0 / s["inclusion_probability"]
    skeys = pd.Index(s["bank_id"] + sep + s["account_id"])
    mask = (fkey.isin(skeys) | tkey.isin(skeys)).to_numpy()
    sampled_tx = trans.loc[mask].copy()
    sampled_tx.insert(0, "row_id", np.flatnonzero(mask).astype(np.int64))
    sampled_tx = sampled_tx.reset_index(drop=True)
    return s, sampled_tx


# --------------------------------------------------------------------------------------------
# The portfolio: natural (clean) baseline
# --------------------------------------------------------------------------------------------
class Portfolio:
    """Holds output values (`out`, strings) and the truth they may later diverge from."""


def build_skeleton(sample: pd.DataFrame, streams: Streams) -> Portfolio:
    rng = streams.bulk("skeleton")
    n = len(sample)
    order = rng.permutation(n)
    sk = sample.iloc[order].reset_index(drop=True)
    market = np.empty(n, dtype=object)
    pos = 0
    for m in MARKETS:
        market[pos:pos + MARKET_CUSTOMERS[m]] = m
        pos += MARKET_CUSTOMERS[m]
    ctype = np.full(n, "Individual", dtype=object)
    for m in MARKETS:
        idx = np.flatnonzero(market == m)
        nb = int(round(MARKET_CUSTOMERS[m] * MARKET_BUSINESS_SHARE[m]))
        ctype[rng.choice(idx, size=nb, replace=False)] = "Business"
    nums = rng.choice(9_000_000, size=n, replace=False) + 1_000_000
    P = Portfolio()
    P.n = n
    P.cid = np.array([f"C{x}" for x in nums], dtype=object)
    P.cid_numbers = set(int(x) for x in nums)
    P.bank = sk["bank_id"].to_numpy(dtype=object)
    P.acct = sk["account_id"].to_numpy(dtype=object)
    P.susp = sk["transfer_suspicious"].to_numpy().astype(int)
    P.role = sk["suspicious_role"].to_numpy(dtype=object)
    P.stratum = sk["stratum"].to_numpy(dtype=object)
    P.incl = sk["inclusion_probability"].to_numpy(dtype=float)
    P.weight = sk["sampling_weight"].to_numpy(dtype=float)
    P.mk = market
    P.typ = ctype
    P.is_ind = ctype == "Individual"
    return P


def _jp_business_name(industry: str, fk: Faker, rng) -> str:
    u = rng.random()
    if u < 0.3:
        stem = fk.last_name()
    elif u < 0.7:
        stem = re.sub(r"[市区町村]$", "", fk.city())
    else:
        stem = fk.town()
    sector = pick(JP_SECTOR_WORDS[industry], rng)
    form = pick_weighted((("株式会社", 0.7), ("有限会社", 0.15), ("合同会社", 0.15)), rng)
    if form != "有限会社" and rng.random() < 0.5:
        return f"{form}{stem}{sector}"
    return f"{stem}{sector}{form}"


def _western_business_name(market: str, industry: str, fk: Faker, rng) -> str:
    sector = pick(SECTOR_WORDS[industry], rng)
    suffix = pick_weighted(UK_SUFFIXES if market == "UK" else AU_SUFFIXES, rng)
    u = rng.random()
    if u < 0.55:
        core = f"{fk.last_name()} {sector}"
    elif u < 0.75:
        conj = "&" if rng.random() < 0.6 else "and"
        core = f"{fk.last_name()} {conj} {fk.last_name()} {sector}"
    elif u < 0.88:
        core = f"{fk.city()} {sector}"
    else:
        core = f"{fk.last_name()} {sector} {pick(['International', 'Holdings', 'Group', 'Services'], rng)}"
    return f"{core} {suffix}"


def _uk_au_address(fk: Faker):
    return fk.street_address().replace("\n", ", "), fk.city(), fk.postcode()


def _jp_address(fk: Faker, rng):
    line = f"{fk.town()}{fk.chome()}{fk.ban()}{fk.gou()}"
    if rng.random() < 0.3:
        line += f" {fk.building_name()}{int(rng.integers(101, 1200))}"
    return line, fk.city(), fk.zipcode()


def build_natural_customers(P: Portfolio, streams: Streams, policy: dict, as_of) -> None:
    rng = streams.bulk("customers")
    fk = {m: streams.faker(LOCALE[m], "customers:" + m) for m in MARKETS}
    n = P.n
    cycles = {k: int(v) for k, v in policy["periodic_review_cycle_days"].items()}

    # Onboarding: all before the first IBM transfer.
    span = int((ONBOARD_END - ONBOARD_START) / np.timedelta64(1, "D"))
    back = np.floor(rng.beta(1.3, 2.2, n) * span).astype(np.int64)
    P.onboarding = ONBOARD_END - back.astype("timedelta64[D]")

    P.pep = np.where(rng.random(n) < np.where(P.is_ind, 0.012, 0.008), "Y", "N").astype(object)

    ind_names = list(INDUSTRIES)
    ind_w = np.array([INDUSTRY_WEIGHTS[k] for k in ind_names], dtype=float)
    ind_draw = rng.choice(len(ind_names), size=n, p=ind_w / ind_w.sum())
    P.industry_canon = np.array([None if P.is_ind[i] else ind_names[ind_draw[i]] for i in range(n)],
                                dtype=object)

    # Natural risk rating (assigned at onboarding; independent of later transfer behaviour)
    probs = np.where(P.is_ind[:, None], np.array(RISK_MIX_IND), np.array(RISK_MIX_BIZ))
    hri = np.isin(P.industry_canon.astype(str), HIGH_RISK_INDUSTRIES)
    probs[hri] = RISK_MIX_HIGH_RISK_INDUSTRY
    probs[P.pep == "Y"] = RISK_MIX_PEP
    u = rng.random(n)
    r_idx = (u[:, None] > probs.cumsum(axis=1)).sum(axis=1).clip(0, 2)
    P.rating_true = RATINGS[r_idx]
    P.cycle_true = np.array([cycles[r] for r in P.rating_true], dtype=np.int64)

    # Natural periodic-review chain
    lag0 = rng.integers(1, 46, n)
    P.lag0 = lag0
    r = P.onboarding + lag0.astype("timedelta64[D]")
    lapse_at = np.where(rng.random(n) < 0.03, rng.integers(0, 20, n), 10 ** 6)
    k = 0
    active = np.ones(n, dtype=bool)
    while True:
        on_time = rng.random(n) < 0.85
        delay = np.where(on_time, rng.integers(-60, 21, n),
                         20 + np.floor(rng.exponential(120.0, n)).astype(np.int64))
        nxt = r + (P.cycle_true + delay).astype("timedelta64[D]")
        can = active & (nxt <= as_of) & (k < lapse_at)
        if not can.any():
            break
        r = np.where(can, nxt, r)
        active = can
        k += 1
    P.review_true = r
    info_lag = np.where(rng.random(n) < 0.9, 0, rng.integers(1, 46, n))
    info = np.minimum(r + info_lag.astype("timedelta64[D]"), as_of)
    P.info_true = info
    P.info_lag = (info - r).astype(np.int64)

    # Individuals: date of birth, documents, occupation
    age_days = (int(18 * 365.25) + 30 + np.floor(rng.beta(2.0, 3.5, n) * 62 * 365.25)).astype(np.int64)
    P.dob_true = np.where(P.is_ind, P.onboarding - age_days.astype("timedelta64[D]"),
                          np.datetime64("NaT", "D"))
    age_now = ((as_of - P.dob_true) / np.timedelta64(1, "D")) / 365.25
    occ_names = list(OCCUPATIONS)
    occ_base_w = np.array([0.4 if o in ("Retired", "Student") else 1.0 for o in occ_names])
    occ_jp_w = np.array([occ_base_w[j] * OCC_WEIGHT_JP.get(o, 1.0) for j, o in enumerate(occ_names)])
    draw_row = rng.choice(len(occ_names), size=n, p=occ_base_w / occ_base_w.sum())
    draw_jp = rng.choice(len(occ_names), size=n, p=occ_jp_w / occ_jp_w.sum())
    u_age = rng.random(n)
    P.occupation_canon = np.empty(n, dtype=object)
    for i in range(n):
        if not P.is_ind[i]:
            P.occupation_canon[i] = None
            continue
        if age_now[i] >= 66 and u_age[i] < 0.55:
            P.occupation_canon[i] = "Retired"
        elif age_now[i] <= 25 and u_age[i] < 0.35:
            P.occupation_canon[i] = "Student"
        else:
            P.occupation_canon[i] = occ_names[(draw_jp if P.mk[i] == "JP" else draw_row)[i]]

    P.id_doc_type = np.empty(n, dtype=object)
    u_doc = rng.random(n)
    for i in range(n):
        if not P.is_ind[i]:
            P.id_doc_type[i] = None
            continue
        mix = ID_DOC_MIX[P.mk[i]]
        cum = np.cumsum([w for _, w in mix])
        j = min(int(np.searchsorted(cum, u_doc[i] * cum[-1], side="right")), len(mix) - 1)
        P.id_doc_type[i] = mix[j][0]
    expiry = as_of + rng.integers(31, 3651, n).astype("timedelta64[D]")
    P.expiry_true = np.where(P.is_ind, expiry, np.datetime64("NaT", "D"))
    # Boundary cases, NOT defects: a handful of documents expiring exactly on the as-of date.
    ind_idx = np.flatnonzero(P.is_ind)
    P.boundary_expiry_idx = np.sort(rng.choice(ind_idx, size=int(rng.integers(3, 9)), replace=False))
    P.expiry_true[P.boundary_expiry_idx] = as_of

    # Purpose of account
    pi_names, pb_names = list(PURPOSES_IND), list(PURPOSES_BIZ)
    pi = rng.choice(len(pi_names), size=n, p=np.array(PURPOSES_IND_WEIGHTS) / sum(PURPOSES_IND_WEIGHTS))
    pb = rng.choice(len(pb_names), size=n, p=np.array(PURPOSES_BIZ_WEIGHTS) / sum(PURPOSES_BIZ_WEIGHTS))
    P.purpose_canon = np.array([pi_names[pi[i]] if P.is_ind[i] else pb_names[pb[i]] for i in range(n)],
                               dtype=object)

    # Registration numbers (fictional format)
    biz_idx = np.flatnonzero(~P.is_ind)
    regnums = rng.choice(9_000_000, size=len(biz_idx), replace=False) + 1_000_000
    P.regnum_true = np.full(n, None, dtype=object)
    for j, i in enumerate(biz_idx):
        P.regnum_true[i] = f"SYN-{P.mk[i]}-{regnums[j]}"
    P.regnum_numbers = set(int(x) for x in regnums)

    # Names, addresses, free text (record by record, Faker per market)
    out_cols = ["customer_id", "bank_id", "account_id", "market", "customer_type",
                "onboarding_date", "last_periodic_review_date", "risk_rating", "id_doc_type",
                "id_doc_expiry", "date_of_birth", "full_name", "business_name",
                "registration_number", "address_line", "city", "postcode", "occupation_text",
                "industry_text", "purpose_of_account_text", "pep_flag", "info_last_refreshed_date"]
    O = {c: np.full(n, None, dtype=object) for c in out_cols}
    P.biz_canon = np.full(n, None, dtype=object)
    seen_names = {m: set() for m in MARKETS}
    for i in range(n):
        m = P.mk[i]
        f = fk[m]
        if P.is_ind[i]:
            O["full_name"][i] = safe_text(f.name(), "Unnamed")
        else:
            for _ in range(200):
                nm = (_jp_business_name(P.industry_canon[i], f, rng) if m == "JP"
                      else _western_business_name(m, P.industry_canon[i], f, rng))
                key = norm_jp_bizname(nm) if m == "JP" else norm_bizname(nm)
                if key not in seen_names[m]:
                    seen_names[m].add(key)
                    break
            else:
                raise RuntimeError("could not generate a unique business name")
            P.biz_canon[i] = nm
            O["business_name"][i] = natural_business_variant(nm, m, rng) if rng.random() < 0.2 else nm
        for _ in range(50):
            line, city, pc = _jp_address(f, rng) if m == "JP" else _uk_au_address(f)
            if re.match(POSTCODE_RE[m], pc):
                break
        else:
            raise RuntimeError("could not generate a valid postcode")
        if rng.random() < 0.12:
            line = variant_jp_address(line, rng) if m == "JP" else variant_address(line, rng)
        O["address_line"][i] = safe_text(line, "1 Main Street")
        O["city"][i] = safe_text(city, "Townsville")
        O["postcode"][i] = pc
        if P.is_ind[i]:
            oc = P.occupation_canon[i]
            O["occupation_text"][i] = render_free_text(oc, OCCUPATIONS[oc], rng,
                                                       OCC_ROMAJI.get(oc) if m == "JP" else None)
        else:
            ic = P.industry_canon[i]
            O["industry_text"][i] = render_free_text(ic, INDUSTRIES[ic], rng)
        pc_ = P.purpose_canon[i]
        O["purpose_of_account_text"][i] = render_free_text(
            pc_, (PURPOSES_IND if P.is_ind[i] else PURPOSES_BIZ)[pc_], rng)

    O["customer_id"][:] = P.cid
    O["bank_id"][:] = P.bank
    O["account_id"][:] = P.acct
    O["market"][:] = P.mk
    O["customer_type"][:] = P.typ
    O["onboarding_date"][:] = iso_array(P.onboarding)
    O["last_periodic_review_date"][:] = iso_array(P.review_true)
    O["risk_rating"][:] = P.rating_true
    O["id_doc_type"][:] = P.id_doc_type
    O["id_doc_expiry"][:] = iso_array(P.expiry_true)
    O["date_of_birth"][:] = iso_array(P.dob_true)
    O["registration_number"][:] = P.regnum_true
    O["pep_flag"][:] = P.pep
    O["info_last_refreshed_date"][:] = iso_array(P.info_true)
    P.out = O
    P.out_cols = out_cols
    P.entity = P.regnum_true.copy()          # business entity id (true company number)


def build_natural_bo(P: Portfolio, streams: Streams, threshold: float, as_of) -> pd.DataFrame:
    rng = streams.bulk("beneficial_owners")
    fk = {m: streams.faker(LOCALE[m], "bo:" + m) for m in MARKETS}
    tpl = [t for t, _ in BO_TEMPLATES]
    w = np.array([x for _, x in BO_TEMPLATES], dtype=float)
    rows = []
    for i in np.flatnonzero(~P.is_ind):
        m = P.mk[i]
        pcts = tpl[int(rng.choice(len(tpl), p=w / w.sum()))]
        names = set()
        for pct in pcts:
            for _ in range(50):
                nm = safe_text(fk[m].name(), "Unnamed Owner")
                if nm not in names:
                    names.add(nm)
                    break
            verified = pct > threshold or rng.random() < 0.5
            if verified:
                if rng.random() < 0.3:
                    vd = P.review_true[i]
                else:
                    vd = min(P.onboarding[i] + td(rng.integers(-30, 31)), as_of)
                ev = pick(BO_EVIDENCE[m], rng)
            else:
                vd, ev = np.datetime64("NaT", "D"), None
            rows.append({"cust": int(i), "bo_name": nm, "pct": float(pct), "verified": bool(verified),
                         "evidence": ev, "vdate": vd})
    bo = pd.DataFrame(rows)
    bo["evidence_out"] = bo["evidence"].astype(object)
    bo["vdate_out"] = [iso(d) for d in bo["vdate"]]
    bo["origin"] = "natural"
    return bo


def build_register(P: Portfolio, bo: pd.DataFrame, streams: Streams, threshold: float) -> pd.DataFrame:
    """Companies House-style extract for every distinct UK business entity (truth-based)."""
    rng = streams.bulk("register")
    rows = []
    by_cust = bo.groupby("cust")
    for i in np.flatnonzero((P.mk == "UK") & ~P.is_ind):
        if P.h5_secondary[i]:
            continue
        owners = by_cust.get_group(i) if i in by_cust.groups else bo.iloc[0:0]
        pscs = owners[owners["pct"] > threshold]
        if len(pscs) == 0:
            rows.append({"registration_number": P.regnum_true[i], "registered_name": P.biz_canon[i],
                         "psc_name": None, "psc_ownership_band": "none",
                         "psc_identity_verified": None, "cust": int(i)})
        for _, o in pscs.iterrows():
            rows.append({"registration_number": P.regnum_true[i], "registered_name": P.biz_canon[i],
                         "psc_name": o["bo_name"], "psc_ownership_band": ownership_band(o["pct"]),
                         "psc_identity_verified": bool(rng.random() < 0.55), "cust": int(i)})
    return pd.DataFrame(rows)


def ownership_band(pct: float) -> str:
    # Companies House style: more than 25% to 50%; more than 50% to less than 75%; 75% or more.
    if pct >= 75:
        return "75-100%"
    if pct > 50:
        return "50-75%"
    return "25-50%"


def build_natural_changes(P: Portfolio, streams: Streams, as_of) -> pd.DataFrame:
    rng = streams.bulk("customer_changes")
    start = np.maximum(P.onboarding, as_of - td(1096))
    years = ((as_of - start) / np.timedelta64(1, "D")) / 365.25
    frames = []
    for ctype, r_ind, r_biz in CHANGE_RATES:
        lam = np.where(P.is_ind, r_ind, r_biz) * years
        k = rng.poisson(lam)
        idx = np.repeat(np.arange(P.n), k)
        spanl = ((as_of - start[idx]) / np.timedelta64(1, "D")).astype(np.int64)
        off = np.floor(rng.random(len(idx)) * (spanl + 1)).astype(np.int64)
        date = start[idx] + off.astype("timedelta64[D]")
        u = rng.random(len(idx))
        delay = np.where(u < 0.80, rng.integers(1, 26, len(idx)),
                         np.where(u < 0.92, rng.integers(26, 31, len(idx)),
                                  rng.integers(31, 121, len(idx))))
        done = date + delay.astype("timedelta64[D]")
        frames.append(pd.DataFrame({"cust": idx, "change_date": date, "change_type": ctype,
                                    "natural_completed": np.where(done <= as_of, done, np.datetime64("NaT", "D")),
                                    "natural_delay": delay}))
    ch = pd.concat(frames, ignore_index=True)
    ch["review_completed"] = ch["natural_completed"]
    return ch


# --------------------------------------------------------------------------------------------
# H5 - duplicate business entities (UK)
# --------------------------------------------------------------------------------------------
def plant_h5(P: Portfolio, bo: pd.DataFrame, params: dict, streams: Streams, as_of):
    rng = streams.hidden("H5")
    P.h5_secondary = np.zeros(P.n, dtype=bool)
    sizes = list(params["H5.cluster_size"])
    clusters_out = []
    if params["H5.duplicate_clusters"] == 0 or not sizes:
        return bo, clusters_out
    uk_biz = np.flatnonzero((P.mk == "UK") & ~P.is_ind)
    members = rng.choice(uk_biz, size=sum(sizes), replace=False)
    pos = 0
    drop_rows = []
    new_rows = []
    name_types = ["abbreviation", "punctuation", "legal_suffix"]
    for size in sizes:
        cl = [int(x) for x in members[pos:pos + size]]
        pos += size
        prim = cl[0]
        used_names = {P.out["business_name"][prim], P.biz_canon[prim]}
        rec = {"entity_registration_number": P.regnum_true[prim], "primary": P.cid[prim],
               "members": [P.cid[x] for x in cl], "secondaries": []}
        prim_rows = bo[bo["cust"] == prim]
        for s in cl[1:]:
            n_types = int(rng.choice([1, 2, 3], p=[0.35, 0.45, 0.20]))
            types = list(rng.choice(["abbreviation", "punctuation", "legal_suffix", "address_format"],
                                    size=n_types, replace=False))
            name = P.biz_canon[prim]
            applied = []
            for t in [t for t in types if t in name_types]:
                fn = {"abbreviation": variant_abbreviation, "punctuation": variant_punctuation,
                      "legal_suffix": variant_legal_suffix}[t]
                cand = fn(name, rng)
                if cand and cand != name:
                    name = cand
                    applied.append(t)
            if name in used_names and "address_format" not in types:
                cand = variant_punctuation(name, rng)
                if cand != name:
                    name = cand
                    applied.append("punctuation")
            used_names.add(name)
            addr = P.out["address_line"][prim]
            if "address_format" in types:
                addr = variant_address(addr, rng)
                applied.append("address_format")
            same_reg = rng.random() < 0.5
            if same_reg:
                reg = P.regnum_true[prim]
            else:
                digits = P.regnum_true[prim][-7:]
                for _ in range(100):
                    j = int(rng.integers(7))
                    d = str(int(rng.integers(10)))
                    nd = digits[:j] + d + digits[j + 1:]
                    if nd != digits and int(nd) >= 1_000_000 and int(nd) not in P.regnum_numbers:
                        break
                P.regnum_numbers.add(int(nd))
                reg = f"SYN-UK-{nd}"
            original = {f: P.out[f][s] for f in ("business_name", "address_line", "city", "postcode",
                                                  "registration_number", "industry_text", "pep_flag")}
            P.out["business_name"][s] = name
            P.out["address_line"][s] = addr
            P.out["city"][s] = P.out["city"][prim]
            P.out["postcode"][s] = P.out["postcode"][prim]
            P.out["registration_number"][s] = reg
            P.out["industry_text"][s] = render_free_text(P.industry_canon[prim],
                                                         INDUSTRIES[P.industry_canon[prim]], rng)
            P.out["pep_flag"][s] = P.out["pep_flag"][prim]
            P.pep[s] = P.pep[prim]
            P.industry_canon[s] = P.industry_canon[prim]
            P.biz_canon[s] = P.biz_canon[prim]
            P.regnum_true[s] = P.regnum_true[prim]
            P.entity[s] = P.entity[prim]
            P.h5_secondary[s] = True
            drop_rows += list(bo.index[bo["cust"] == s])
            for _, o in prim_rows.iterrows():
                r = o.to_dict()
                r["cust"] = s
                if r["verified"]:
                    r["vdate"] = min(P.onboarding[s] + td(rng.integers(-30, 31)), as_of)
                    r["vdate_out"] = iso(r["vdate"])
                r["origin"] = "natural"
                new_rows.append(r)
            rec["secondaries"].append({"customer_id": P.cid[s], "variant_types_applied": applied,
                                       "registration_number": "identical" if same_reg else "mis-keyed",
                                       "original_values_replaced": original})
        clusters_out.append(rec)
    bo = pd.concat([bo.drop(index=drop_rows), pd.DataFrame(new_rows)], ignore_index=True)
    return bo, clusters_out


# --------------------------------------------------------------------------------------------
# Customer-level planting
# --------------------------------------------------------------------------------------------
class Planter:
    def __init__(self, P: Portfolio, params: dict, streams: Streams, policy: dict, as_of, bo):
        self.P, self.params, self.streams, self.as_of = P, params, streams, as_of
        self.bo = bo
        self.cells = []
        self.touched = [set() for _ in range(P.n)]
        self.ws_rng = streams.hidden("whitespace")
        self.ws_share = float(params["record_level_errors.whitespace_not_null"])
        self.decoy = params["decoy.clean_dimension"]
        self.h3_block = None          # (market, field) filled by H3 auto-fill
        self.bo_remove = set()
        self.bo_verif_missing = []    # bo row indices
        self.bo_future = []           # bo row indices
        self.records = {}
        self.cycles = {k: int(v) for k, v in policy["periodic_review_cycle_days"].items()}

    # -- utilities --------------------------------------------------------------------------
    def missing(self):
        if self.ws_rng.random() < self.ws_share:
            return " " * int(self.ws_rng.integers(1, 4))
        return None

    def excl(self, i) -> set:
        e = set(self.touched[i])
        if self.decoy:
            e.add(self.decoy)
        if self.h3_block and self.P.mk[i] == self.h3_block[0]:
            e.add(self.h3_block[1])
        return e

    def set(self, i, field, value, process, kind, dimension):
        old = self.P.out[field][i]
        self.P.out[field][i] = value
        self.touched[i].add(field)
        self.cells.append(["customers", self.P.cid[i], self.P.cid[i], field, process, kind,
                           dimension, self.P.mk[i], old, value])

    def _rate(self, dim):
        base = self.params[f"H1.base_defect_rate.{dim}"]
        mult = self.params[f"H1.worst_market_multiplier.{dim}"]
        worst = self.params[f"H1.worst_market.{dim}"]
        return np.array([min(1.0, base * (mult if m == worst else 1.0)) for m in self.P.mk])

    # -- H6 ---------------------------------------------------------------------------------
    def h6(self):
        rng = self.streams.hidden("H6")
        u = rng.random(self.P.n)
        sel = (u < self.params["H6.share_of_suspicious_forced_low"]) & (self.P.susp == 1)
        selected, changed = [], []
        for i in np.flatnonzero(sel):
            selected.append(self.P.cid[i])
            if self.P.out["risk_rating"][i] != "Low":
                self.set(i, "risk_rating", "Low", "H6", "suspicious_forced_low", "validity")
                changed.append(self.P.cid[i])
            self.touched[i].add("risk_rating")
        self.records["H6_selected_customers"] = selected
        self.records["H6_changed_customers"] = changed

    # -- H3 ---------------------------------------------------------------------------------
    def h3(self):
        rng = self.streams.hidden("H3")
        u = rng.random(self.P.n)
        affected = []
        if self.params["H3.present"]:
            m3, fld = self.params["H3.market"], self.params["H3.field"]
            field = "risk_rating" if fld == "risk_rating_low" else "last_periodic_review_date"
            self.h3_block = (m3, field)
            for i in np.flatnonzero((u < self.params["H3.affected_share"]) & (self.P.mk == m3)):
                if field in self.touched[i]:
                    continue
                new = "Low" if field == "risk_rating" else self.P.out["onboarding_date"][i]
                affected.append(self.P.cid[i])
                if self.P.out[field][i] != new:
                    self.set(i, field, new, "H3", "default_value_autofill", "validity")
                self.touched[i].add(field)
        self.records["H3_affected_customers"] = affected

    # -- real-world timeliness states (H4, H1 timeliness) --------------------------------------
    def _stale_info(self, i, rng, process, kind) -> bool:
        if "info_last_refreshed_date" in self.excl(i):
            return False
        c = int(self.P.cycle_true[i])
        ob = self.P.onboarding[i]
        hi = min(self.P.review_true[i], self.as_of - td(c + 15))
        if hi < ob:
            return False
        cand = ob + td(self.P.lag0[i])
        if rng.random() < 0.5 and cand <= hi:
            d = cand
        else:
            d = ob + td(rng.integers(0, int((hi - ob) / np.timedelta64(1, "D")) + 1))
        self.set(i, "info_last_refreshed_date", iso(d), process, kind, "timeliness")
        self.P.info_true[i] = d
        return True

    def _overdue_review(self, i, rng, process, kind) -> bool:
        ex = self.excl(i)
        if "last_periodic_review_date" in ex:
            return False
        c = int(self.P.cycle_true[i])
        ob = self.P.onboarding[i]
        hi = min(self.P.review_true[i] - td(1), self.as_of - td(c + 15))
        lo = max(ob + td(1), self.as_of - td(c + 900))
        if hi < lo:
            return False
        d = lo + td(rng.integers(0, int((hi - lo) / np.timedelta64(1, "D")) + 1))
        self.set(i, "last_periodic_review_date", iso(d), process, kind, "timeliness")
        self.P.review_true[i] = d
        if "info_last_refreshed_date" not in ex:
            nd = min(d + td(self.P.info_lag[i]), self.as_of)
            self.set(i, "info_last_refreshed_date", iso(nd), process, kind + "_info_cascade",
                     "timeliness")
            self.P.info_true[i] = nd
        return True

    def h4(self):
        rng = self.streams.hidden("H4")
        slope = self.params["H4.extra_stale_prob_per_tenure_year"]
        tenure = ((self.as_of - self.P.onboarding) / np.timedelta64(1, "D")) / 365.25
        p = np.minimum(0.95, slope * tenure)
        u = rng.random(self.P.n)
        out = []
        for i in np.flatnonzero((u < p) & (self.P.mk == "JP")):
            if self._stale_info(i, rng, "H4", "stale_info_long_tenure"):
                out.append(self.P.cid[i])
        self.records["H4_stale_customers"] = out

    def h1_timeliness(self):
        rng = self.streams.hidden("H1.timeliness")
        u = rng.random(self.P.n)
        sel = np.flatnonzero(u < self._rate("timeliness"))
        unrealised = 0
        for i in sel:
            kinds = ["stale_info", "overdue_review"]
            rng.shuffle(kinds)
            ok = False
            for kd in kinds:
                fn = self._stale_info if kd == "stale_info" else self._overdue_review
                if fn(i, rng, "H1.timeliness", kd):
                    ok = True
                    break
            unrealised += (not ok)
        self.records["H1_timeliness_selected_not_realisable"] = int(unrealised)

    # -- H2: completeness gaps -----------------------------------------------------------------
    def h2(self, threshold):
        rng = self.streams.hidden("H2")
        base = self.params["H1.base_defect_rate.completeness"]
        mult = self.params["H1.worst_market_multiplier.completeness"]
        worst = self.params["H1.worst_market.completeness"]
        r_mm = self.params["record_level_errors.missing_mandatory_field"]
        OR = self.params["H2.effective_odds_ratio"]
        p0 = {m: 1 - (1 - min(1.0, base * (mult if m == worst else 1.0))) * (1 - r_mm) for m in MARKETS}
        p1 = {m: OR * p0[m] / (1 - p0[m] + OR * p0[m]) for m in MARKETS}
        self.records["H2_gap_probability_non_suspicious_by_market"] = p0
        self.records["H2_gap_probability_suspicious_by_market"] = p1
        u = rng.random(self.P.n)
        p = np.array([p1[m] if s == 1 else p0[m] for m, s in zip(self.P.mk, self.P.susp)])
        gap = np.flatnonzero(u < p)
        bo_by_cust = self.bo.groupby("cust").groups
        realised, unrealised = [], []
        for i in gap:
            k = int(rng.choice(GAP_COUNT_CHOICES, p=GAP_COUNT_PROBS))
            ex = self.excl(i)
            fields = GAP_FIELDS_IND if self.P.is_ind[i] else GAP_FIELDS_BIZ
            elig_owner = []
            if not self.P.is_ind[i] and i in bo_by_cust:
                rows = self.bo.loc[bo_by_cust[i]]
                elig_owner = list(rows.index[(rows["pct"] > threshold) & rows["verified"]])
            cands = []
            for f, w in fields:
                if f in ex:
                    continue
                if f == "bo_records" and i not in bo_by_cust:
                    continue
                if f == "bo_verification" and not elig_owner:
                    continue
                cands.append((f, w))
            if not cands:
                unrealised.append(self.P.cid[i])
                continue
            w = np.array([c[1] for c in cands])
            chosen = [cands[j][0] for j in rng.choice(len(cands), size=min(k, len(cands)),
                                                     replace=False, p=w / w.sum())]
            if "bo_records" in chosen and "bo_verification" in chosen:
                chosen.remove("bo_verification")
            for f in chosen:
                if f == "bo_records":
                    self.bo_remove.add(int(i))
                    self.touched[i].add("bo_records")
                    self.touched[i].add("bo_verification")
                elif f == "bo_verification":
                    self.bo_verif_missing.append(int(elig_owner[int(rng.integers(len(elig_owner)))]))
                    self.touched[i].add("bo_verification")
                else:
                    self.set(i, f, self.missing(), "completeness_gap", "missing_value", "completeness")
            realised.append(self.P.cid[i])
        self.records["H2_gap_customers"] = realised
        self.records["H2_gap_selected_not_realisable"] = unrealised

    # -- data errors: consistency, validity, named errors ----------------------------------------
    def _other_market_postcode(self, m, rng):
        other = [x for x in MARKETS if x != m][int(rng.integers(2))]
        if other == "AU":
            return f"{int(rng.integers(800, 8000)):04d}"
        if other == "JP":
            return f"{int(rng.integers(0, 1000)):03d}-{int(rng.integers(0, 10000)):04d}"
        letters = "ABCDEFGHJKLMNPRSTUWYZ"
        return (f"{pick(letters, rng)}{pick(letters, rng)}{int(rng.integers(1, 10))} "
                f"{int(rng.integers(1, 10))}{pick('ABDEFGHJLNPQRSTUWXYZ', rng)}{pick('ABDEFGHJLNPQRSTUWXYZ', rng)}")

    def h1_consistency(self):
        rng = self.streams.hidden("H1.consistency")
        u = rng.random(self.P.n)
        sel = np.flatnonzero(u < self._rate("consistency"))
        unrealised = 0
        for i in sel:
            ex = self.excl(i)
            kinds = []
            if "last_periodic_review_date" not in ex:
                kinds.append("review_before_onboarding")
            if "info_last_refreshed_date" not in ex:
                kinds.append("info_refresh_before_onboarding")
            if "postcode" not in ex:
                kinds.append("postcode_wrong_market")
            if not self.P.is_ind[i] and "registration_number" not in ex:
                kinds.append("registration_prefix_wrong_market")
            if not kinds:
                unrealised += 1
                continue
            kd = pick(kinds, rng)
            ob = self.P.onboarding[i]
            if kd == "review_before_onboarding":
                self.set(i, "last_periodic_review_date", iso(ob - td(rng.integers(30, 901))),
                         "H1.consistency", kd, "consistency")
            elif kd == "info_refresh_before_onboarding":
                self.set(i, "info_last_refreshed_date", iso(ob - td(rng.integers(30, 901))),
                         "H1.consistency", kd, "consistency")
            elif kd == "postcode_wrong_market":
                self.set(i, "postcode", self._other_market_postcode(self.P.mk[i], rng),
                         "H1.consistency", kd, "consistency")
            else:
                cur = self.P.out["registration_number"][i]
                other = [x for x in MARKETS if x != self.P.mk[i]][int(rng.integers(2))]
                self.set(i, "registration_number", cur.replace(f"SYN-{self.P.mk[i]}-", f"SYN-{other}-"),
                         "H1.consistency", kd, "consistency")
        self.records["H1_consistency_selected_not_realisable"] = int(unrealised)

    def _implausible_dob(self, rng):
        u = rng.random()
        if u < 0.4:
            return "1900-01-01"
        if u < 0.7:
            return iso(np.datetime64("1890-01-01") + td(rng.integers(0, 16 * 365)))
        return iso(np.datetime64("2009-01-01") + td(rng.integers(0, 7 * 365)))

    def h1_validity(self):
        rng = self.streams.hidden("H1.validity")
        u = rng.random(self.P.n)
        sel = np.flatnonzero(u < self._rate("validity"))
        unrealised = 0
        for i in sel:
            ex = self.excl(i)
            kinds = []
            if self.P.is_ind[i] and "date_of_birth" not in ex:
                kinds.append("dob_implausible")
            if "risk_rating" not in ex:
                kinds.append("risk_rating_invalid_code")
            if "pep_flag" not in ex:
                kinds.append("pep_flag_invalid_code")
            if self.P.is_ind[i] and "id_doc_type" not in ex:
                kinds.append("id_doc_type_invalid_code")
            if not kinds:
                unrealised += 1
                continue
            kd = pick(kinds, rng)
            if kd == "dob_implausible":
                self.set(i, "date_of_birth", self._implausible_dob(rng), "H1.validity", kd, "validity")
            elif kd == "risk_rating_invalid_code":
                self.set(i, "risk_rating", pick(INVALID_RISK_CODES, rng), "H1.validity", kd, "validity")
            elif kd == "pep_flag_invalid_code":
                self.set(i, "pep_flag", pick(INVALID_PEP_CODES, rng), "H1.validity", kd, "validity")
            else:
                self.set(i, "id_doc_type", pick(INVALID_ID_DOC_CODES, rng), "H1.validity", kd, "validity")
        self.records["H1_validity_selected_not_realisable"] = int(unrealised)

    def _malformed_postcode(self, pc, m, rng):
        for _ in range(50):
            u = rng.random()
            if m == "UK":
                if u < 0.25:
                    v = pc.split(" ")[0]
                elif u < 0.5:
                    v = pc[:-1]
                elif u < 0.75:
                    v = pc + pick("ABDEFGHJ", rng)
                else:
                    v = pc.replace("1", "I").replace("0", "O") if re.search("[01]", pc) else pc.replace(" ", "-")
            elif m == "AU":
                v = pc[:3] if u < 0.35 else (pc + str(int(rng.integers(10))) if u < 0.7 else pc.replace("0", "O", 1) if "0" in pc else "NSW " + pc)
            else:
                v = pc.replace("-", "") if u < 0.35 else (pc.translate(FULLWIDTH) if u < 0.7 else pc[:-1])
            if not re.match(POSTCODE_RE[m], v):
                return v
        return pc + "X"

    def _malformed_regnum(self, reg, rng):
        mkt, digits = reg[4:6], reg[-7:]
        opts = [f"SYN-{mkt}-{digits[:-1]}", f"SYN{mkt}{digits}", f"SYN-{mkt}-{digits}{int(rng.integers(10))}",
                f"SYN-{mkt}-{digits[:3]}E{digits[4:]}", f"SYN {mkt} {digits}", reg.lower()]
        return pick(opts, rng)

    def named_invalid_format(self):
        rng = self.streams.hidden("invalid_format")
        rate = self.params["record_level_errors.invalid_format"]
        u = rng.random(self.P.n)
        n_ok = 0
        for i in np.flatnonzero(u < rate):
            ex = self.excl(i)
            fields = [f for f in (["postcode"] + ([] if self.P.is_ind[i] else ["registration_number"]))
                      if f not in ex]
            if not fields:
                continue
            f = pick(fields, rng)
            if f == "postcode":
                self.set(i, f, self._malformed_postcode(self.P.out[f][i], self.P.mk[i], rng),
                         "record_level_errors", "invalid_format_postcode", "validity")
            else:
                self.set(i, f, self._malformed_regnum(self.P.out[f][i], rng),
                         "record_level_errors", "invalid_format_registration_number", "validity")
            n_ok += 1

    def named_future_date(self, threshold):
        rng = self.streams.hidden("future_date")
        rate = self.params["record_level_errors.future_date"]
        u = rng.random(self.P.n)
        bo_by_cust = self.bo.groupby("cust").groups
        for i in np.flatnonzero(u < rate):
            ex = self.excl(i)
            fields = [f for f in ("last_periodic_review_date", "info_last_refreshed_date") if f not in ex]
            owners = []
            if (not self.P.is_ind[i]) and i in bo_by_cust and "bo_verification" not in ex:
                rows = self.bo.loc[bo_by_cust[i]]
                owners = list(rows.index[rows["verified"]])
                if owners:
                    fields.append("bo_verification_date")
            if not fields:
                continue
            f = pick(fields, rng)
            fut = iso(self.as_of + td(rng.integers(1, 731)))
            if f == "bo_verification_date":
                self.bo_future.append((int(pick(owners, rng)), fut))
                self.touched[i].add("bo_verification")
            else:
                self.set(i, f, fut, "record_level_errors", "future_date", "validity")

    def named_expired_document(self):
        rng = self.streams.hidden("expired_document")
        rate = self.params["record_level_errors.expired_document"]
        u = rng.random(self.P.n)
        boundary = set(int(x) for x in self.P.boundary_expiry_idx)
        for i in np.flatnonzero((u < rate) & self.P.is_ind):
            if "id_doc_expiry" in self.excl(i) or int(i) in boundary:
                continue
            d = self.as_of - td(rng.integers(1, 1501))
            self.set(i, "id_doc_expiry", iso(d), "record_level_errors", "expired_document", "timeliness")
            self.P.expiry_true[i] = d


# --------------------------------------------------------------------------------------------
# Beneficial-owner and register planting
# --------------------------------------------------------------------------------------------
def plant_bo(pl: Planter, bo: pd.DataFrame, params: dict, streams: Streams, as_of, threshold):
    P = pl.P
    cells = pl.cells
    rec = {}
    # 1. owner records missing entirely (completeness gap)
    removed = bo[bo["cust"].isin(sorted(pl.bo_remove))]
    rec["bo_records_missing_customers"] = [P.cid[i] for i in sorted(pl.bo_remove)]
    rec["bo_records_missing_rows"] = [{"customer_id": P.cid[r["cust"]], "bo_name": r["bo_name"],
                                       "ownership_pct": r["pct"]} for _, r in removed.iterrows()]
    bo = bo.drop(index=removed.index)
    # 2. verification evidence missing for an owner above the threshold (completeness gap)
    verif_rows = []
    for r in pl.bo_verif_missing:
        old = (bo.at[r, "evidence_out"], bo.at[r, "vdate_out"])
        bo.at[r, "verified"] = False
        bo.at[r, "evidence_out"] = pl.missing()
        bo.at[r, "vdate_out"] = pl.missing()
        verif_rows.append(r)
        cells.append(["beneficial_owners", r, P.cid[bo.at[r, "cust"]], "verification_evidence_type+verification_date",
                      "completeness_gap", "unverified_owner_above_threshold", "completeness",
                      P.mk[bo.at[r, "cust"]], list(old), [bo.at[r, "evidence_out"], bo.at[r, "vdate_out"]]])
    # 3. future verification dates
    for r, fut in pl.bo_future:
        old = bo.at[r, "vdate_out"]
        bo.at[r, "vdate_out"] = fut
        cells.append(["beneficial_owners", r, P.cid[bo.at[r, "cust"]], "verification_date",
                      "record_level_errors", "future_date", "validity", P.mk[bo.at[r, "cust"]], old, fut])
    # 4. ownership totals above 100%: the largest owner entered twice.
    #    The frame's index IS the stable row key; new rows get fresh keys.
    next_key = int(bo["rowkey"].max()) + 1 if len(bo) else 0
    rng = streams.hidden("ownership_over_100")
    rate = params["record_level_errors.ownership_total_over_100"]
    custs = np.array(sorted(bo["cust"].unique()))
    u = rng.random(len(custs))
    dup_rows, over = [], []
    groups = bo.groupby("cust").groups
    for c in custs[u < rate]:
        rows = bo.loc[groups[c]]
        top = rows["pct"].idxmax()
        r = bo.loc[top].to_dict()
        r["origin"] = "planted_duplicate_owner"
        r["rowkey"] = next_key
        next_key += 1
        dup_rows.append(r)
        over.append({"customer_id": P.cid[c], "duplicated_owner": r["bo_name"],
                     "duplicated_rowkey": int(top), "duplicate_rowkey": int(r["rowkey"]),
                     "total_before": float(rows["pct"].sum()),
                     "total_after": float(rows["pct"].sum() + r["pct"])})
    # 5. orphan owner rows: owners of customers that do not exist
    rng = streams.hidden("orphans")
    fks = {m: streams.faker(LOCALE[m], "orphans:" + m, hidden=True) for m in MARKETS}
    n_orphan = int(round(params["record_level_errors.orphan_beneficial_owner"] * (len(bo) + len(dup_rows))))
    orphan_rows, ghosts = [], []
    tpl = [t for t, _ in BO_TEMPLATES]
    w = np.array([x for _, x in BO_TEMPLATES], dtype=float)
    while len(orphan_rows) < n_orphan:
        for _ in range(1000):
            num = int(rng.integers(1_000_000, 10_000_000))
            if num not in P.cid_numbers:
                break
        P.cid_numbers.add(num)
        ghost = f"C{num}"
        m = MARKETS[int(rng.integers(3))]
        pcts = tpl[int(rng.choice(len(tpl), p=w / w.sum()))]
        gdate = ONBOARD_START + td(rng.integers(0, 5000))
        for pct in pcts:
            if len(orphan_rows) >= n_orphan:
                break
            verified = pct > threshold or rng.random() < 0.5
            vd = gdate + td(rng.integers(-30, 31)) if verified else np.datetime64("NaT", "D")
            ev_ = pick(BO_EVIDENCE[m], rng) if verified else None
            orphan_rows.append({"cust": -1, "ghost_customer_id": ghost,
                                "bo_name": safe_text(fks[m].name(), "Unnamed Owner"),
                                "pct": float(pct), "verified": bool(verified), "evidence": ev_,
                                "vdate": vd, "evidence_out": ev_, "vdate_out": iso(vd),
                                "origin": "planted_orphan", "rowkey": next_key})
            next_key += 1
        ghosts.append(ghost)
    extra = dup_rows + orphan_rows
    if extra:
        add = pd.DataFrame(extra)
        add.index = add["rowkey"].to_numpy()
        bo = pd.concat([bo, add])
    if "ghost_customer_id" not in bo.columns:
        bo["ghost_customer_id"] = None
    bo["verified"] = bo["verified"].astype(bool)
    rec["ownership_total_over_100"] = over
    rec["orphan_ghost_customer_ids"] = ghosts
    rec["orphan_row_count"] = len(orphan_rows)
    # 6. ids: every owner row gets a random id only now, so ids carry no planted signal
    rng = streams.hidden("bo_ids")
    nums = rng.choice(9_000_000, size=len(bo), replace=False) + 1_000_000
    bo["bo_id"] = [f"B{x}" for x in nums]
    bo["customer_id"] = [g if c == -1 else P.cid[c] for c, g in zip(bo["cust"], bo["ghost_customer_id"])]
    rk2id = dict(zip(bo["rowkey"].astype(int), bo["bo_id"]))
    for o in over:
        o["duplicated_bo_id"] = rk2id[o.pop("duplicated_rowkey")]
        o["duplicate_bo_id"] = rk2id[o.pop("duplicate_rowkey")]
    rec["orphan_bo_ids"] = list(bo.loc[bo["origin"] == "planted_orphan", "bo_id"])
    return bo, rec, verif_rows


def _named(v) -> bool:
    return isinstance(v, str) and v != ""


def plant_register(P: Portfolio, reg: pd.DataFrame, params: dict, streams: Streams):
    rng = streams.hidden("register")
    fk = streams.faker("en_GB", "register_psc", hidden=True)
    rate = params["record_level_errors.register_mismatch"]
    entities = list(dict.fromkeys(reg["registration_number"]))
    grouped = {k: g.to_dict("records") for k, g in reg.groupby("registration_number", sort=False)}
    u = rng.random(len(entities))
    out_rows = []
    mism = []
    for e, uu in zip(entities, u):
        rows = grouped[e]
        if uu < rate:
            has_psc = [r for r in rows if _named(r["psc_name"])]
            kinds = ["extra_psc_in_register"]
            if has_psc:
                kinds += ["bank_owner_missing_from_register", "band_disagrees", "name_spelling_variant"]
            kd = pick(kinds, rng)
            detail = {}
            if kd == "extra_psc_in_register":
                new = {"registration_number": e, "registered_name": rows[0]["registered_name"],
                       "psc_name": fk.name(), "psc_ownership_band": pick(["25-50%", "25-50%", "50-75%"], rng),
                       "psc_identity_verified": bool(rng.random() < 0.55), "cust": rows[0]["cust"]}
                rows = [r for r in rows if _named(r["psc_name"])] + [new]
                detail = {"added_psc": new["psc_name"]}
            elif kd == "bank_owner_missing_from_register":
                victim = pick(has_psc, rng)
                rows = [r for r in rows if r is not victim]
                detail = {"removed_psc": victim["psc_name"]}
                if not any(_named(r["psc_name"]) for r in rows):
                    rows = [{"registration_number": e, "registered_name": victim["registered_name"],
                             "psc_name": None, "psc_ownership_band": "none",
                             "psc_identity_verified": None, "cust": victim["cust"]}]
            elif kd == "band_disagrees":
                victim = pick(has_psc, rng)
                old = victim["psc_ownership_band"]
                victim["psc_ownership_band"] = pick([b for b in ("25-50%", "50-75%", "75-100%") if b != old], rng)
                detail = {"psc": victim["psc_name"], "true_band": old, "register_band": victim["psc_ownership_band"]}
            else:
                victim = pick(has_psc, rng)
                old = victim["psc_name"]
                victim["psc_name"] = psc_name_variant(old, rng)
                detail = {"true_name": old, "register_name": victim["psc_name"]}
            customers = [P.cid[i] for i in np.flatnonzero(P.regnum_true == e)]
            mism.append({"registration_number": e, "kind": kd, "detail": detail,
                         "customers_with_this_true_number": customers})
        out_rows += rows
    return pd.DataFrame(out_rows), mism


def psc_name_variant(name: str, rng) -> str:
    parts = name.split(" ")
    u = rng.random()
    if u < 0.4 and len(parts[-1]) >= 4:
        return " ".join(parts[:-1] + [typo(parts[-1], rng)])
    if u < 0.7 and len(parts) >= 2:
        return " ".join(parts[:-1] + [pick("ABCDEFGHJKLMNPRSTW", rng) + "."] + parts[-1:])
    if len(parts) >= 2:
        return parts[0][0] + ". " + " ".join(parts[1:])
    return name + "e"


def plant_h7(P: Portfolio, ch: pd.DataFrame, params: dict, streams: Streams):
    rng = streams.hidden("H7")
    b = params["H7.baseline_neglect_rate"]
    k = params["H7.concentration_multiplier"]
    m7 = params["H7.concentrated_market"]
    mk = P.mk[ch["cust"].to_numpy()]
    p = np.minimum(0.95, np.where(mk == m7, b * k, b))
    u = rng.random(len(ch))
    neglected = u < p
    ch["neglected"] = neglected
    ch.loc[neglected, "review_completed"] = np.datetime64("NaT", "D")
    return ch


# --------------------------------------------------------------------------------------------
# Card layer
# --------------------------------------------------------------------------------------------
def build_card_layer(P: Portfolio, params: dict, streams: Streams, card_cfg: dict, as_of):
    rngN = streams.bulk("card_natural")
    rngT = streams.hidden("card_typologies")
    n = P.n
    months = pd.period_range(end=pd.Period(str(card_cfg["period_ends"])[:7], "M"),
                             periods=int(card_cfg["months"]), freq="M")
    jp = P.mk == "JP"
    fx = np.array([FX[m] for m in P.mk])

    def to_minor(x_major, mask=None):
        x = np.asarray(x_major, dtype=float)
        m = jp if mask is None else mask
        return np.where(m, np.round(x) * 100, np.round(x * 100)).astype(np.int64)

    def round_minor(x_minor, mask=None):
        x = np.asarray(x_minor, dtype=float)
        m = jp if mask is None else mask
        return np.where(m, np.round(x / 100) * 100, np.round(x)).astype(np.int64)

    def one_minor(i, x_major):
        return int(round(x_major) * 100) if jp[i] else int(round(x_major * 100))

    def one_round(i, x_minor):
        return int(round(x_minor / 100) * 100) if jp[i] else int(round(x_minor))

    typ = P.typ
    S = np.array([SPEND_MEDIAN[t] for t in typ]) * np.exp(
        rngN.normal(0, 1, n) * np.array([SPEND_SIGMA[t] for t in typ])) * fx
    lim_unit = np.where(jp, 10000.0, 100.0)
    limit_major = np.maximum(500 * fx, np.round(S * rngN.uniform(3, 7, n) / lim_unit) * lim_unit)
    limit = to_minor(limit_major)
    transactor = rngN.random(n) < 0.7
    own_raw = rngN.integers(0, 16 ** 10, n)
    own_id = np.array([f"PY{x:010X}" for x in own_raw], dtype=object)
    if len(set(own_id)) != n:
        raise RuntimeError("payer id collision")
    n_extra = np.where(P.is_ind, (rngN.random(n) < 0.03).astype(int),
                       np.where(rngN.random(n) < 0.20, rngN.integers(1, 3, n), 0))
    extra1 = np.array([f"PY{x:010X}" for x in rngN.integers(0, 16 ** 10, n)], dtype=object)
    extra2 = np.array([f"PY{x:010X}" for x in rngN.integers(0, 16 ** 10, n)], dtype=object)
    extra_share = np.where(P.is_ind, 0.3, 0.5)
    merchants = np.array([f"MR{x}" for x in rngN.choice(900_000, N_MERCHANTS, replace=False) + 100_000],
                         dtype=object)
    B = to_minor(S * np.where(transactor, rngN.uniform(0.3, 1.2, n), rngN.uniform(1.0, 3.0, n)))
    B = np.minimum(B, limit)

    # ---- typology plans (hidden) -----------------------------------------------------------
    prev_ = {k: params[f"card_layer.typology_prevalence.{k}"] for k in
             ("overpayment_refund_cycling", "third_party_funding", "refunds_without_purchases",
              "cash_advance_velocity")}
    members = {}
    for k, pr in prev_.items():
        cnt = int(round(pr * n))
        members[k] = np.sort(rngT.choice(n, size=cnt, replace=False)) if cnt else np.array([], dtype=int)
    t3_mask = np.zeros(n, dtype=bool)
    t3_mask[members["refunds_without_purchases"]] = True
    plans = {t: [] for t in range(len(months))}
    fresh = lambda: f"PY{int(rngT.integers(0, 16 ** 10)):010X}"
    for i in members["overpayment_refund_cycling"]:
        tp = [fresh() for _ in range(int(rngT.integers(1, 3)))]
        exit_id = fresh()
        for t in np.sort(rngT.choice(len(months), size=int(rngT.integers(3, 9)), replace=False)):
            plans[int(t)].append(("T1", int(i), {
                "mult": float(rngT.uniform(2, 10)), "payer": own_id[i] if rngT.random() < 0.6 else pick(tp, rngT),
                "day": int(rngT.integers(1, 16)), "delay": int(rngT.integers(1, 11)),
                "share": float(rngT.uniform(0.85, 1.0)), "round": bool(rngT.random() < 0.6),
                "refund_to": own_id[i] if rngT.random() < 0.5 else exit_id,
                "ch_pay": pick(["bank_transfer"] * 7 + ["card_app"] * 3, rngT),
                "ch_rr": pick(["app", "phone"], rngT)}))
    for i in members["third_party_funding"]:
        payers = [fresh() for _ in range(int(rngT.integers(4, 13)))]
        exit_id = fresh()
        for t in np.sort(rngT.choice(len(months), size=int(rngT.integers(4, 13)), replace=False)):
            k_ = int(rngT.integers(2, 6))
            plans[int(t)].append(("T2", int(i), {
                "payers": [pick(payers, rngT) for _ in range(k_)],
                "days": sorted(int(x) for x in rngT.integers(0, 27, k_)),
                "amts": [float(rngT.uniform(100, 2000)) for _ in range(k_)],
                "chs": [pick(["bank_transfer"] * 12 + ["branch_cash"] * 5 + ["card_app"] * 3, rngT) for _ in range(k_)],
                "follow": float(rngT.random()), "take": float(rngT.uniform(0.5, 0.9)),
                "exit": exit_id if rngT.random() < 0.7 else own_id[i],
                "n_ca": int(rngT.integers(2, 5))}))
    for i in members["refunds_without_purchases"]:
        mers = [pick(merchants, rngT) for _ in range(int(rngT.integers(1, 3)))]
        exit_id = fresh()
        for _ in range(int(rngT.integers(3, 11))):
            t = int(rngT.integers(len(months)))
            plans[t].append(("T3", int(i), {
                "merchant": pick(mers, rngT), "day": int(rngT.integers(0, 22)),
                "mult": float(rngT.uniform(1, 6)), "follow": float(rngT.random()),
                "take": float(rngT.uniform(0.7, 1.0)), "gap": int(rngT.integers(2, 16)),
                "exit": exit_id, "n_ca": int(rngT.integers(2, 5)),
                "ch": pick(["online", "pos"], rngT)}))
    for i in members["cash_advance_velocity"]:
        tp = fresh()
        for t in np.sort(rngT.choice(len(months), size=int(rngT.integers(1, 5)), replace=False)):
            n_ca = int(rngT.integers(3, 9))
            plans[int(t)].append(("T4", int(i), {
                "day": int(rngT.integers(0, 20)), "mult": float(rngT.uniform(3, 10)),
                "payer": own_id[i] if rngT.random() < 0.5 else tp, "n_ca": n_ca,
                "offs": [int(x) for x in rngT.integers(0, 4, n_ca)],
                "take": float(rngT.uniform(0.7, 1.0)),
                "chs": [pick(["atm"] * 7 + ["quasi_cash"] * 2 + ["branch"], rngT) for _ in range(n_ca)]}))

    # ---- month loop ------------------------------------------------------------------------
    ev = {"c": [], "d": [], "t": [], "a": [], "cp": [], "ch": []}

    def add(c, d, t, a, cp, ch):
        c = np.atleast_1d(np.asarray(c, dtype=np.int64))
        a = np.atleast_1d(np.asarray(a, dtype=np.int64))
        keep = a > 0
        if not keep.any():
            return
        ev["c"].append(c[keep])
        ev["d"].append(np.atleast_1d(np.asarray(d, dtype="datetime64[D]"))[keep] if np.ndim(d) else
                       np.full(keep.sum(), np.datetime64(d, "D")))
        ev["t"].append(np.full(keep.sum(), t, dtype=object))
        ev["a"].append(a[keep])
        cp = np.atleast_1d(np.asarray(cp, dtype=object))
        ev["cp"].append(cp[keep] if len(cp) == len(keep) else np.full(keep.sum(), cp[0], dtype=object))
        ch = np.atleast_1d(np.asarray(ch, dtype=object))
        ev["ch"].append(ch[keep] if len(ch) == len(keep) else np.full(keep.sum(), ch[0], dtype=object))

    statements = np.zeros((len(months), n), dtype=np.int64)
    ca_unit = np.where(jp, 1000.0, 10.0)
    for t, per in enumerate(months):
        ms = np.datetime64(per.start_time.date(), "D")
        nd = int(per.days_in_month)
        mstr = str(per)
        prev = B.copy()
        mark = len(ev["c"])
        purchases = to_minor(S * rngN.gamma(4.0, 0.25, n) * SEASON.get(mstr, 1.0))
        purchases[t3_mask] = round_minor(purchases[t3_mask] * 0.03, jp[t3_mask])
        t1_now = np.zeros(n, dtype=bool)
        for kind, i, pl in plans[t]:
            if kind == "T1":
                t1_now[i] = True
        # natural payment of the previous balance
        due = np.maximum(prev, 0)
        frac = rngN.uniform(0.1, 0.6, n)
        rev_amt = round_minor(np.maximum(np.minimum(due, np.maximum(0.05 * due, to_minor(25 * fx))), due * frac))
        pay_amt = np.where(transactor, due, rev_amt)
        has_pay = (pay_amt > 0) & ~t1_now
        split = rngN.random(n) < 0.15
        d1 = rngN.integers(4, 22, n)
        d2 = np.minimum(nd - 1, d1 + rngN.integers(3, 9, n))
        part = round_minor(pay_amt * rngN.uniform(0.3, 0.7, n))
        amt1 = np.where(split, part, pay_amt)
        amt2 = pay_amt - amt1
        use_extra = (n_extra > 0) & (rngN.random(n) < extra_share)
        payer = np.where(use_extra, np.where((n_extra > 1) & (rngN.random(n) < 0.5), extra2, extra1), own_id)
        ch_u = rngN.random(n)
        # Every channel a typology uses also occurs naturally, so no channel value is a giveaway.
        ch_pay = np.where(
            transactor,
            np.where(ch_u < 0.70, "direct_debit", np.where(ch_u < 0.94, "bank_transfer",
                     np.where(ch_u < 0.98, "card_app", "branch_cash"))),
            np.where(ch_u < 0.48, "bank_transfer", np.where(ch_u < 0.78, "direct_debit",
                     np.where(ch_u < 0.97, "card_app", "branch_cash")))).astype(object)
        idx = np.flatnonzero(has_pay)
        add(idx, ms + d1[idx].astype("timedelta64[D]"), "payment", amt1[idx], payer[idx], ch_pay[idx])
        idx2 = np.flatnonzero(has_pay & split)
        add(idx2, ms + d2[idx2].astype("timedelta64[D]"), "payment", amt2[idx2], payer[idx2], ch_pay[idx2])
        # ad-hoc extra payments
        adhoc = rngN.random(n) < 0.06
        ad_amt = to_minor(np.round(S * rngN.uniform(0.05, 0.5, n) / (10 * fx)) * (10 * fx))
        ad_day = rngN.integers(0, nd, n)
        ad_cu = rngN.random(n)
        ad_ch = np.where(ad_cu < 0.88, "bank_transfer", np.where(ad_cu < 0.94, "card_app", "branch_cash")).astype(object)
        idx = np.flatnonzero(adhoc)
        add(idx, ms + ad_day[idx].astype("timedelta64[D]"), "payment", ad_amt[idx], own_id[idx], ad_ch[idx])
        # natural duplicate payment followed by a refund request (honest overpayment)
        dup = has_pay & (d1 <= 14) & (rngN.random(n) < 0.035)
        dup_day = d1 + rngN.integers(0, 3, n)
        rr_day = np.minimum(nd - 1, dup_day + rngN.integers(3, 12, n))
        rr_ch = np.where(rngN.random(n) < 0.7, "app", "phone").astype(object)
        idx = np.flatnonzero(dup)
        add(idx, ms + dup_day[idx].astype("timedelta64[D]"), "payment", amt1[idx], payer[idx], ch_pay[idx])
        add(idx, ms + rr_day[idx].astype("timedelta64[D]"), "refund_request", amt1[idx], own_id[idx], rr_ch[idx])
        # merchant refunds (never more than a share of this month's purchases)
        k_mr = np.minimum(rngN.poisson(0.15, n), 3)
        idx = np.repeat(np.arange(n), k_mr)
        mr_amt = round_minor(purchases[idx] * rngN.uniform(0.02, 0.2, len(idx)), jp[idx])
        mr_day = rngN.integers(0, nd, len(idx))
        mr_m = merchants[rngN.integers(0, N_MERCHANTS, len(idx))]
        mr_ch = np.where(rngN.random(len(idx)) < 0.6, "online", "pos").astype(object)
        add(idx, ms + mr_day.astype("timedelta64[D]"), "merchant_refund", mr_amt, mr_m, mr_ch)
        # cash advances
        k_ca = rngN.poisson(0.08, n)
        idx = np.repeat(np.arange(n), k_ca)
        ca_amt = to_minor(np.maximum(1, np.round(rngN.uniform(20, 400, len(idx)) * fx[idx] / ca_unit[idx]))
                          * ca_unit[idx], jp[idx])
        ca_day = rngN.integers(0, nd, len(idx))
        cu = rngN.random(len(idx))
        ca_ch = np.where(cu < 0.8, "atm", np.where(cu < 0.9, "branch", "quasi_cash")).astype(object)
        ca_cp = np.array([f"ATM{x:05d}" for x in rngN.integers(0, 100000, len(idx))], dtype=object)
        br = ca_ch == "branch"
        ca_cp[br] = [f"BR{x:04d}" for x in rngN.integers(0, 10000, int(br.sum()))]
        qc = ca_ch == "quasi_cash"
        ca_cp[qc] = merchants[rngN.integers(0, N_MERCHANTS, int(qc.sum()))]
        add(idx, ms + ca_day.astype("timedelta64[D]"), "cash_advance", ca_amt, ca_cp, ca_ch)

        # typology events for this month
        for kind, i, pl in plans[t]:
            Si = S[i]
            if kind == "T1":
                o = Si * pl["mult"]
                if pl["round"]:
                    o = max(100 * FX[P.mk[i]], round(o / (100 * FX[P.mk[i]])) * 100 * FX[P.mk[i]])
                o_minor = one_minor(i, o)
                pay = int(max(prev[i], 0)) + o_minor
                add([i], ms + td(pl["day"]), "payment", [pay], [pl["payer"]], [pl["ch_pay"]])
                rr = one_round(i, o_minor * pl["share"])
                add([i], ms + td(min(nd - 1, pl["day"] + pl["delay"])), "refund_request", [rr], [pl["refund_to"]], [pl["ch_rr"]])
            elif kind == "T2":
                unit = 50 * FX[P.mk[i]]
                amts = [one_minor(i, max(unit, round(a * FX[P.mk[i]] / unit) * unit)) for a in pl["amts"]]
                add([i] * len(amts), [ms + td(d) for d in pl["days"]], "payment", amts, pl["payers"], pl["chs"])
                total = sum(amts)
                last = max(pl["days"])
                if pl["follow"] < 0.5:
                    rr = one_minor(i, total * pl["take"] / 100)
                    add([i], ms + td(min(nd - 1, last + 3)), "refund_request", [rr], [pl["exit"]], ["app"])
                elif pl["follow"] < 0.8:
                    per_ca = one_minor(i, max(ca_unit[i], round(total * pl["take"] / pl["n_ca"] / 100 / ca_unit[i]) * ca_unit[i]))
                    add([i] * pl["n_ca"], [ms + td(min(nd - 1, last + 1 + j)) for j in range(pl["n_ca"])],
                        "cash_advance", [per_ca] * pl["n_ca"], [f"ATM{int(rngT.integers(0, 100000)):05d}"] * pl["n_ca"], ["atm"] * pl["n_ca"])
            elif kind == "T3":
                amt = one_minor(i, Si * pl["mult"])
                add([i], ms + td(pl["day"]), "merchant_refund", [amt], [pl["merchant"]], [pl["ch"]])
                if pl["follow"] < 0.7:
                    rr = one_minor(i, amt * pl["take"] / 100)
                    add([i], ms + td(min(nd - 1, pl["day"] + pl["gap"])), "refund_request", [rr], [pl["exit"]], ["app"])
                else:
                    per_ca = one_minor(i, max(ca_unit[i], round(amt * pl["take"] / pl["n_ca"] / 100 / ca_unit[i]) * ca_unit[i]))
                    add([i] * pl["n_ca"], [ms + td(min(nd - 1, pl["day"] + 1 + j)) for j in range(pl["n_ca"])],
                        "cash_advance", [per_ca] * pl["n_ca"], [f"ATM{int(rngT.integers(0, 100000)):05d}"] * pl["n_ca"], ["atm"] * pl["n_ca"])
            else:  # T4
                pay = one_minor(i, Si * pl["mult"])
                add([i], ms + td(pl["day"]), "payment", [pay], [pl["payer"]], ["bank_transfer"])
                per_ca = one_minor(i, max(ca_unit[i], round(pay * pl["take"] / pl["n_ca"] / 100 / ca_unit[i]) * ca_unit[i]))
                cps = [f"ATM{int(rngT.integers(0, 100000)):05d}" if c == "atm" else
                       (pick(merchants, rngT) if c == "quasi_cash" else f"BR{int(rngT.integers(0, 10000)):04d}")
                       for c in pl["chs"]]
                add([i] * pl["n_ca"], [ms + td(min(nd - 1, pl["day"] + o)) for o in pl["offs"]],
                    "cash_advance", [per_ca] * pl["n_ca"], cps, pl["chs"])

        # month totals and the balance identity
        c_all = np.concatenate(ev["c"][mark:]) if len(ev["c"]) > mark else np.array([], dtype=np.int64)
        t_all = np.concatenate(ev["t"][mark:]) if len(ev["t"]) > mark else np.array([], dtype=object)
        a_all = np.concatenate(ev["a"][mark:]) if len(ev["a"]) > mark else np.array([], dtype=np.int64)

        def total(kind):
            m_ = t_all == kind
            return np.bincount(c_all[m_], weights=a_all[m_].astype(float), minlength=n).round().astype(np.int64)

        pay_s, rr_s, mr_s, ca_s = total("payment"), total("refund_request"), total("merchant_refund"), total("cash_advance")
        Bn = prev + purchases + ca_s - pay_s - mr_s + rr_s
        over = np.maximum(Bn - limit, 0)
        cut = np.minimum(over, purchases)
        cut = round_minor(cut)
        cut = np.minimum(cut, purchases)
        Bn = Bn - cut
        B = Bn
        statements[t] = B

    # ---- assemble --------------------------------------------------------------------------
    c = np.concatenate(ev["c"])
    act = pd.DataFrame({"cust": c, "event_date": np.concatenate(ev["d"]), "event_type": np.concatenate(ev["t"]),
                        "amount_minor": np.concatenate(ev["a"]), "counterparty_id": np.concatenate(ev["cp"]),
                        "channel": np.concatenate(ev["ch"])})
    rng = streams.hidden("event_ids")
    raw = rng.integers(100_000_000, 1_000_000_000, int(len(act) * 1.05) + 1000)
    _, first = np.unique(raw, return_index=True)
    uniq = raw[np.sort(first)][: len(act)]
    if len(uniq) < len(act):
        raise RuntimeError("not enough unique event ids")
    act["event_id"] = [f"E{x}" for x in uniq]
    truly = sorted(set().union(*[set(int(x) for x in v) for v in members.values()]))
    rngL = streams.hidden("H8")
    n_unl = int(round(params["H8.unlabelled_share_of_truly_suspicious"] * len(truly)))
    unl = set(int(x) for x in rngL.choice(truly, size=n_unl, replace=False)) if truly and n_unl else set()
    label = np.zeros(n, dtype=int)
    for i in truly:
        if i not in unl:
            label[i] = 1
    card = {"statements": statements, "months": [str(p) for p in months], "limit": limit,
            "activity": act, "label": label, "members": {k: [P.cid[i] for i in v] for k, v in members.items()},
            "truly": [P.cid[i] for i in truly], "unlabelled": [P.cid[i] for i in sorted(unl)]}
    return card


# --------------------------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------------------------
def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def fmt_minor(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.int64)
    sign = np.where(a < 0, "-", "")
    ab = np.abs(a)
    return np.array([f"{s}{x // 100}.{x % 100:02d}" for s, x in zip(sign, ab)], dtype=object)


def generate(hidden_seed: int, out_root: Path, write_key: bool = True, zero_defects: bool = False,
             verbose: bool = True) -> dict:
    say = print if verbose else (lambda *a, **k: None)
    ranges, policy = load_config()
    as_of = np.datetime64(str(policy["as_of_date"]), "D")
    threshold = float(policy["beneficial_ownership"]["threshold_pct_exclusive"])
    sampling_seed = int(ranges["seeds"]["sampling_seed"])
    streams = Streams(sampling_seed, hidden_seed)
    params = draw_parameters(ranges, streams.hidden("parameters"))
    active = zero_out(params) if zero_defects else params

    say("[1/8] loading IBM transfers and sampling the portfolio (public seed)")
    trans = load_ibm(IBM_TRANS_PATH)
    sample, sampled_tx = sample_portfolio(trans, sampling_seed, N_CUSTOMERS)
    del trans

    say("[2/8] building the clean baseline")
    P = build_skeleton(sample, streams)
    build_natural_customers(P, streams, policy, as_of)
    bo = build_natural_bo(P, streams, threshold, as_of)
    P.rating_natural = P.rating_true.copy()

    say("[3/8] duplicate entities, register extract, customer changes")
    bo, h5_clusters = plant_h5(P, bo, active, streams, as_of)
    bo = bo.reset_index(drop=True)
    bo["rowkey"] = np.arange(len(bo))
    bo.index = bo["rowkey"].to_numpy()
    register = build_register(P, bo, streams, threshold)
    changes = build_natural_changes(P, streams, as_of)

    say("[4/8] planting customer-level defects")
    pl = Planter(P, active, streams, policy, as_of, bo)
    pl.h6()
    pl.h3()
    pl.h4()
    pl.h1_timeliness()
    pl.h2(threshold)
    pl.h1_consistency()
    pl.h1_validity()
    pl.named_invalid_format()
    pl.named_future_date(threshold)
    pl.named_expired_document()

    say("[5/8] planting owner, register and trigger defects")
    bo, bo_rec, _ = plant_bo(pl, bo, active, streams, as_of, threshold)
    register, reg_mism = plant_register(P, register, active, streams)
    changes = plant_h7(P, changes, active, streams)

    say("[6/8] card layer")
    card = build_card_layer(P, active, streams, ranges["card_layer"], as_of)

    say("[7/8] writing outputs")
    raw = out_root / "data" / "raw"
    proc = out_root / "data" / "processed"
    raw.mkdir(parents=True, exist_ok=True)
    proc.mkdir(parents=True, exist_ok=True)

    cust_df = pd.DataFrame({c: P.out[c] for c in P.out_cols}).sort_values("customer_id", kind="mergesort")
    _write_csv(cust_df, raw / "customers.csv")

    bo_out = pd.DataFrame({
        "bo_id": bo["bo_id"], "customer_id": bo["customer_id"], "bo_name": bo["bo_name"],
        "ownership_pct": [f"{x:.1f}" for x in bo["pct"]],
        "id_verified_flag": ["True" if v else "False" for v in bo["verified"]],
        "verification_evidence_type": bo["evidence_out"], "verification_date": bo["vdate_out"]})
    bo_out = bo_out.sort_values(["customer_id", "bo_id"], kind="mergesort")
    _write_csv(bo_out, raw / "beneficial_owners.csv")

    reg_out = register[["registration_number", "registered_name", "psc_name", "psc_ownership_band",
                        "psc_identity_verified"]].copy()
    reg_out["psc_identity_verified"] = [None if v is None or (isinstance(v, float) and np.isnan(v))
                                        else ("True" if v else "False") for v in reg_out["psc_identity_verified"]]
    reg_out["_sort"] = reg_out["psc_name"].fillna("")
    reg_out = reg_out.sort_values(["registration_number", "_sort"], kind="mergesort").drop(columns="_sort")
    _write_csv(reg_out, raw / "uk_register_extract.csv")

    rng_ch = streams.hidden("change_ids")
    ch_nums = rng_ch.choice(9_000_000, size=len(changes), replace=False) + 1_000_000
    changes["change_id"] = [f"CH{x}" for x in ch_nums]
    ch_out = pd.DataFrame({"change_id": changes["change_id"], "customer_id": P.cid[changes["cust"].to_numpy()],
                           "change_date": iso_array(changes["change_date"].to_numpy().astype("datetime64[D]")),
                           "change_type": changes["change_type"],
                           "review_completed_date": iso_array(changes["review_completed"].to_numpy().astype("datetime64[D]"))})
    ch_out = ch_out.sort_values(["change_date", "change_id"], kind="mergesort")
    _write_csv(ch_out, raw / "customer_changes.csv")

    n_m = len(card["months"])
    st = pd.DataFrame({
        "customer_id": np.repeat(P.cid, n_m),
        "statement_month": np.tile(np.array(card["months"], dtype=object), P.n),
        "statement_balance": fmt_minor(card["statements"].T.reshape(-1)),
        "credit_limit": fmt_minor(np.repeat(card["limit"], n_m)),
        "currency": np.repeat(np.array([CURRENCY[m] for m in P.mk], dtype=object), n_m)})
    st = st.sort_values(["customer_id", "statement_month"], kind="mergesort")
    _write_csv(st, raw / "card_statements.csv")

    act = card["activity"]
    act_out = pd.DataFrame({"event_id": act["event_id"], "customer_id": P.cid[act["cust"].to_numpy()],
                            "event_date": iso_array(act["event_date"].to_numpy().astype("datetime64[D]")),
                            "event_type": act["event_type"], "amount": fmt_minor(act["amount_minor"].to_numpy()),
                            "currency": [CURRENCY[m] for m in P.mk[act["cust"].to_numpy()]],
                            "counterparty_id": act["counterparty_id"], "channel": act["channel"]})
    act_out = act_out.sort_values(["event_date", "event_id"], kind="mergesort")
    _write_csv(act_out, raw / "card_activity.csv")

    lab_out = pd.DataFrame({"customer_id": P.cid, "card_suspicious": card["label"]}).sort_values("customer_id")
    _write_csv(lab_out, raw / "card_labels.csv")

    cl = pd.DataFrame({"customer_id": P.cid, "bank_id": P.bank, "account_id": P.acct,
                       "transfer_suspicious": P.susp, "suspicious_role": P.role}).sort_values("customer_id")
    _write_csv(cl, proc / "customer_labels.csv")
    sw = pd.DataFrame({"customer_id": P.cid, "bank_id": P.bank, "account_id": P.acct, "stratum": P.stratum,
                       "inclusion_probability": P.incl, "sampling_weight": P.weight}).sort_values("customer_id")
    _write_csv(sw, proc / "sampling_weights.csv")
    sampled_tx.to_parquet(proc / "sampled_transactions.parquet", index=False, engine="pyarrow",
                          compression="snappy")

    files = {}
    for name in RAW_OUTPUTS:
        pth = raw / name
        files[f"data/raw/{name}"] = {"sha256": sha256_file(pth), "rows": int(sum(1 for _ in open(pth, "rb")) - 1)}
    for name in PROCESSED_OUTPUTS:
        pth = proc / name
        rows = len(sampled_tx) if name.endswith(".parquet") else int(sum(1 for _ in open(pth, "rb")) - 1)
        files[f"data/processed/{name}"] = {"sha256": sha256_file(pth), "rows": int(rows)}

    say("[8/8] assembling the answer key")
    key = build_answer_key(hidden_seed, sampling_seed, params, active, zero_defects, P, pl, bo, bo_rec,
                           reg_mism, changes, h5_clusters, card, files, as_of, threshold, policy)
    key_bytes = json.dumps(key, ensure_ascii=False, indent=1, default=_json_default).encode("utf-8")
    if write_key:
        kp = out_root / KEY_RELPATH
        kp.parent.mkdir(parents=True, exist_ok=True)
        with open(kp, "wb") as fh:
            fh.write(key_bytes)
    return {"files": files, "key_sha256": hashlib.sha256(key_bytes).hexdigest(), "key_bytes": key_bytes}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.datetime64):
        return iso(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


def build_answer_key(hidden_seed, sampling_seed, params, active, zero_defects, P, pl, bo, bo_rec, reg_mism,
                     changes, h5_clusters, card, files, as_of, threshold, policy) -> dict:
    # map owner row indices recorded during planting to bo_ids
    rk2id = dict(zip(bo["rowkey"].astype(int), bo["bo_id"]))
    cells = []
    for c in pl.cells:
        c = list(c)
        if c[0] == "beneficial_owners":
            c[1] = rk2id[int(c[1])]
        cells.append(c)
    counts = {}
    for c in cells:
        k = f"{c[4]}|{c[5]}|{c[6]}|{c[7]}"
        counts[k] = counts.get(k, 0) + 1

    # planted-issue counts per hypothesis and market
    mk_of = dict(zip(P.cid, P.mk))
    susp_of = dict(zip(P.cid, P.susp))

    def by_market(ids):
        out = {m: 0 for m in MARKETS}
        for x in ids:
            out[mk_of[x]] += 1
        return out

    gap_set = set(pl.records.get("H2_gap_customers", []))
    h2_table = {m: {"suspicious_with_gap": 0, "suspicious_without_gap": 0,
                    "other_with_gap": 0, "other_without_gap": 0} for m in MARKETS}
    for cid_, m in mk_of.items():
        k = ("suspicious" if susp_of[cid_] == 1 else "other") + ("_with_gap" if cid_ in gap_set else "_without_gap")
        h2_table[m][k] += 1
    dim_customers = {}
    for c in cells:
        dim_customers.setdefault(c[6], {m: set() for m in MARKETS})[c[7]].add(c[2])
    h7_ids = list(changes.loc[changes["neglected"], "change_id"])
    ch_mk = dict(zip(changes["change_id"], P.mk[changes["cust"].to_numpy()]))
    ch_total = {m: int((P.mk[changes["cust"].to_numpy()] == m).sum()) for m in MARKETS}
    per_hyp = {
        "H1_customers_with_any_planted_defect_by_dimension": {
            d: {m: len(v) for m, v in mm.items()} for d, mm in sorted(dim_customers.items())},
        "H2_gap_by_market_and_transfer_suspicious": h2_table,
        "H3_affected": by_market(pl.records.get("H3_affected_customers", [])),
        "H4_stale": by_market(pl.records.get("H4_stale_customers", [])),
        "H5_clusters": len(h5_clusters),
        "H5_records_in_clusters": by_market([x for cl in h5_clusters for x in cl["members"]]),
        "H6_selected": by_market(pl.records.get("H6_selected_customers", [])),
        "H6_changed": by_market(pl.records.get("H6_changed_customers", [])),
        "H7_neglected_changes": {m: sum(1 for x in h7_ids if ch_mk[x] == m) for m in MARKETS},
        "H7_all_changes": ch_total,
        "card_typology_members": {t: by_market(v) for t, v in card["members"].items()},
        "card_truly_suspicious": by_market(card["truly"]),
        "card_unlabelled_truly_suspicious": by_market(card["unlabelled"]),
        "bo_records_missing": by_market(bo_rec["bo_records_missing_customers"]),
        "bo_ownership_total_over_100": by_market([o["customer_id"] for o in bo_rec["ownership_total_over_100"]]),
        "bo_orphan_rows_no_market": bo_rec["orphan_row_count"],
        "register_mismatches_UK_by_kind": {k: sum(1 for x in reg_mism if x["kind"] == k)
                                           for k in ("extra_psc_in_register", "bank_owner_missing_from_register",
                                                     "band_disagrees", "name_spelling_variant")},
    }

    # truth tables
    status = np.where((as_of - P.review_true) / np.timedelta64(1, "D") > P.cycle_true, "overdue", "compliant")
    truth_cust = [[P.cid[i], P.rating_natural[i], iso(P.review_true[i]), status[i], iso(P.info_true[i]),
                   iso(P.expiry_true[i]), P.occupation_canon[i], P.industry_canon[i], P.purpose_canon[i],
                   P.biz_canon[i], P.entity[i]] for i in range(P.n)]
    ch_status = []
    deadline = int(policy["trigger_review"]["deadline_days"])
    for r in changes.itertuples(index=False):
        age = int((as_of - np.datetime64(r.change_date, "D")) / np.timedelta64(1, "D"))
        if r.neglected:
            s = "neglected_never_reviewed"
        elif pd.isna(r.natural_completed):
            s = "pending_within_deadline" if age <= deadline else "pending_past_deadline"
        else:
            s = "completed_on_time" if int(r.natural_delay) <= deadline else "completed_late"
        ch_status.append([r.change_id, P.cid[r.cust], s])

    bo_verif_ids = [rk2id[int(r)] for r in pl.bo_verif_missing]
    exact_boundary = bo[(bo["pct"] == threshold) & (~bo["verified"].astype(bool))
                        & (bo["origin"] == "natural")]
    key = {
        "about": "Sealed answer key. Do not open before Day 10 (CLAUDE.md Section 8.5).",
        "seeds": {"sampling_seed": sampling_seed, "hidden_parameter_seed": str(hidden_seed)},
        "zero_defects_dev_mode": bool(zero_defects),
        "provenance": {"generate_py_sha256": sha256_file(Path(__file__)),
                       "generator_ranges_sha256": sha256_file(RANGES_PATH),
                       "policy_sha256": sha256_file(POLICY_PATH),
                       "ibm_trans_sha256": sha256_file(IBM_TRANS_PATH),
                       "ibm_patterns_sha256": sha256_file(IBM_PATTERNS_PATH) if IBM_PATTERNS_PATH.exists() else None},
        "interpretations": {
            "decoy": "field-level: the drawn field receives no planted defect of any kind in any market",
            "decoy_candidates": list(DECOY_CANDIDATES),
            "H1": "extra market-skewed generic process per dimension; named record-level errors uniform",
            "H2_gap_definition": "at least one mandatory value missing (null or whitespace) in customers.csv, "
                                 "OR all beneficial-owner rows missing, OR an owner above the threshold "
                                 "without verification evidence",
            "real_world_states": "H4, H1.timeliness and expired_document change the truth; other defects are data errors",
            "periodic_status_rule": "overdue if (as_of - true review date) > cycle days of the true rating",
            "trigger_status_rule": f"on time if completed within {deadline} days of the change date",
        },
        "drawn_parameters": params,
        "derived": {k: v for k, v in pl.records.items() if k.startswith("H2_gap_probability")},
        "planted_counts_by_hypothesis_and_market": per_hyp,
        "planted_counts_by_process_kind_dimension_market": counts,
        "planted_cells": {"columns": ["table", "record_id", "customer_id", "field", "process", "kind",
                                      "dimension", "market", "original", "planted"], "rows": cells},
        "hypotheses": {
            "H2_gap_customers": pl.records.get("H2_gap_customers", []),
            "H2_gap_selected_not_realisable": pl.records.get("H2_gap_selected_not_realisable", []),
            "H3_affected_customers": pl.records.get("H3_affected_customers", []),
            "H4_stale_customers": pl.records.get("H4_stale_customers", []),
            "H5_clusters": h5_clusters,
            "H6_selected_customers": pl.records.get("H6_selected_customers", []),
            "H6_changed_customers": pl.records.get("H6_changed_customers", []),
            "H7_neglected_change_ids": list(changes.loc[changes["neglected"], "change_id"]),
            "H8_card": {"truly_suspicious": card["truly"], "unlabelled_truly_suspicious": card["unlabelled"],
                        "typology_members": card["members"]},
            "not_realisable_counts": {k: v for k, v in pl.records.items() if k.endswith("not_realisable")},
        },
        "beneficial_owners": {**bo_rec, "unverified_owner_above_threshold_bo_ids": bo_verif_ids},
        "register_mismatches": reg_mism,
        "cascades": {
            "bo_records_missing_UK": "the register still lists the company's PSCs, so a register comparison also shows a discrepancy",
            "registration_number_defects": "malformed, wrong-prefix, missing or H5 mis-keyed numbers do not join to the register",
            "ownership_duplicate_owner": "the same person appears twice; summing per person changes the register band comparison",
            "overdue_review_info_cascade": "an overdue review also leaves information unrefreshed since that review",
        },
        "boundary_cases_not_defects": {
            "unverified_owner_at_exactly_threshold_bo_ids": list(exact_boundary["bo_id"]),
            "id_doc_expiring_on_as_of_customer_ids": [P.cid[i] for i in P.boundary_expiry_idx
                                                       if P.out["id_doc_expiry"][i] == iso(as_of)],
        },
        "truth": {
            "customers": {"columns": ["customer_id", "true_risk_rating", "true_last_periodic_review_date",
                                      "true_periodic_status", "true_info_last_refreshed_date",
                                      "true_id_doc_expiry", "occupation_canonical", "industry_canonical",
                                      "purpose_canonical", "business_name_canonical", "business_entity_id"],
                          "rows": truth_cust},
            "customer_changes": {"columns": ["change_id", "customer_id", "true_status"], "rows": ch_status},
        },
        "output_files": files,
    }
    return key


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------
def load_key_seed(repo: Path = REPO) -> int:
    with open(repo / KEY_RELPATH, encoding="utf-8") as fh:
        return int(json.load(fh)["seeds"]["hidden_parameter_seed"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--force", action="store_true", help="overwrite an existing answer key / ignore lock")
    ap.add_argument("--skip-checks", action="store_true")
    ap.add_argument("--dev-seed", type=int, help="development only; requires --out-root outside the repo")
    ap.add_argument("--out-root", type=Path)
    ap.add_argument("--zero-defects", action="store_true", help="development only")
    args = ap.parse_args(argv)

    if args.dev_seed is not None or args.zero_defects:
        if args.dev_seed is None or args.out_root is None:
            raise SystemExit("development runs need both --dev-seed and --out-root")
        root = args.out_root.resolve()
        if root == REPO or REPO in root.parents:
            raise SystemExit("development runs must not write inside the repository")
        res = generate(args.dev_seed, root, write_key=True, zero_defects=args.zero_defects)
        for k, v in res["files"].items():
            print(f"  {k}: {v['rows']:,} rows")
        return 0

    if args.out_root is not None and args.out_root.resolve() != REPO:
        raise SystemExit("the real run writes into the repository only")
    ranges, _ = load_config()
    key_path = REPO / KEY_RELPATH
    if key_path.exists() and not args.force:
        raise SystemExit("sealed/answer_key.json already exists - refusing to overwrite (use --force).")
    if ranges.get("locked") and not args.force:
        raise SystemExit("config/generator_ranges.yaml is locked - refusing to regenerate (use --force).")
    seed = secrets.randbits(128)
    res = generate(seed, REPO, write_key=True)
    print("Row counts (withheld where the count moves with a hidden parameter):")
    for k, v in res["files"].items():
        if Path(k).name in ROW_COUNT_WITHHELD:
            print(f"  {k}: written")
        else:
            print(f"  {k}: {v['rows']:,} rows")
    if args.skip_checks:
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import acceptance_checks
    return 0 if acceptance_checks.run_all() else 1


if __name__ == "__main__":
    sys.exit(main())
