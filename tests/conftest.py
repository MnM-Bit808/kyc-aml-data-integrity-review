# Written by Claude Code - infrastructure, not analysis
"""
Known-bad fixtures for the Module 1 data-quality rules.

Each fixture is a tiny table where you already know which rows are wrong and why.
The tests in test_dq_rules.py assert that your rule flags exactly those rows -
no more, no fewer. Flagging too much is as much a failure as flagging too little,
because a rule that fires on everything tells the business nothing.

Read the comment above each bad row before writing the rule it tests.

These fixtures cover ONLY the record-level errors already named in CLAUDE.md
Section 8.8. The other rules in Module 1 are yours to design, and you write their
fixtures too - designing the test case IS designing the rule.
"""

import pandas as pd
import pytest

# The portfolio's "as of" date. Everything time-based is measured against this.
# Matches config/policy.yaml. Australia's ongoing CDD obligations commenced on
# this date, which is why the scenario asks its question here.
AS_OF = pd.Timestamp("2026-03-31")


@pytest.fixture
def as_of():
    return AS_OF


@pytest.fixture
def customers():
    """
    Nine customers. C001 and C002 are clean; the rest each carry exactly one
    defect, so a failing test points at one rule rather than a tangle.
    """
    rows = [
        # --- clean ---
        dict(customer_id="C001", market="UK", customer_type="Individual",
             onboarding_date="2019-04-12", last_periodic_review_date="2025-06-01",
             risk_rating="Medium", id_doc_type="passport", id_doc_expiry="2030-01-31",
             date_of_birth="1985-03-02", postcode="SW1A 1AA",
             occupation_text="Software Engineer", info_last_refreshed_date="2025-06-01"),
        dict(customer_id="C002", market="JP", customer_type="Individual",
             onboarding_date="2021-09-30", last_periodic_review_date="2025-11-20",
             risk_rating="Low", id_doc_type="drivers_licence", id_doc_expiry="2029-08-15",
             date_of_birth="1990-12-11", postcode="100-0001",
             occupation_text="Teacher", info_last_refreshed_date="2025-11-20"),

        # --- missing mandatory field: risk_rating is absent ---
        # Completeness. Without a rating there is no review cycle, so this
        # customer's compliance status is UNKNOWN, not compliant.
        dict(customer_id="C003", market="UK", customer_type="Individual",
             onboarding_date="2020-01-15", last_periodic_review_date="2025-02-01",
             risk_rating=None, id_doc_type="passport", id_doc_expiry="2031-05-05",
             date_of_birth="1978-07-19", postcode="M1 1AE",
             occupation_text="Accountant", info_last_refreshed_date="2025-02-01"),

        # --- missing mandatory field: empty string, not None ---
        # The trap. An empty string is not null, so isna() misses it entirely.
        # A completeness rule that only checks isna() will pass this row and be wrong.
        dict(customer_id="C004", market="AU", customer_type="Individual",
             onboarding_date="2018-06-01", last_periodic_review_date="2024-06-01",
             risk_rating="   ", id_doc_type="passport", id_doc_expiry="2028-02-20",
             date_of_birth="1982-01-30", postcode="2000",
             occupation_text="Nurse", info_last_refreshed_date="2024-06-01"),

        # --- future date: reviewed in the future ---
        # Validity. Impossible, so it is a data error, not a compliant customer.
        # Note this row would otherwise look like the MOST compliant in the table.
        dict(customer_id="C005", market="AU", customer_type="Individual",
             onboarding_date="2017-03-03", last_periodic_review_date="2027-01-01",
             risk_rating="High", id_doc_type="passport", id_doc_expiry="2032-09-09",
             date_of_birth="1975-05-25", postcode="3000",
             occupation_text="Builder", info_last_refreshed_date="2027-01-01"),

        # --- expired identity document ---
        # Timeliness. Expired more than a year before the as-of date.
        dict(customer_id="C006", market="UK", customer_type="Individual",
             onboarding_date="2016-11-11", last_periodic_review_date="2025-01-10",
             risk_rating="Low", id_doc_type="passport", id_doc_expiry="2025-01-09",
             date_of_birth="1969-09-09", postcode="EH1 1YZ",
             occupation_text="Driver", info_last_refreshed_date="2025-01-10"),

        # --- review date precedes onboarding ---
        # Consistency. Reviewed before they were a customer. Ordering error.
        dict(customer_id="C007", market="JP", customer_type="Individual",
             onboarding_date="2022-05-20", last_periodic_review_date="2021-05-20",
             risk_rating="Medium", id_doc_type="passport", id_doc_expiry="2030-03-03",
             date_of_birth="1995-02-02", postcode="150-0002",
             occupation_text="Designer", info_last_refreshed_date="2021-05-20"),

        # --- invalid format: date of birth implies an implausible age ---
        # Validity. Born 1898 - would be over 120. Almost always a typo or a
        # default value, never a real cardmember.
        dict(customer_id="C008", market="UK", customer_type="Individual",
             onboarding_date="2015-02-02", last_periodic_review_date="2024-02-02",
             risk_rating="Low", id_doc_type="passport", id_doc_expiry="2029-01-01",
             date_of_birth="1898-01-01", postcode="B1 1AA",
             occupation_text="Retired", info_last_refreshed_date="2024-02-02"),

        # --- business customer, used by the beneficial-ownership tests ---
        dict(customer_id="C009", market="UK", customer_type="Business",
             onboarding_date="2019-08-08", last_periodic_review_date="2025-08-08",
             risk_rating="High", id_doc_type=None, id_doc_expiry=None,
             date_of_birth=None, postcode="EC2R 8AH",
             occupation_text=None, info_last_refreshed_date="2025-08-08"),
    ]
    df = pd.DataFrame(rows)
    for col in ["onboarding_date", "last_periodic_review_date", "id_doc_expiry",
                "date_of_birth", "info_last_refreshed_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


@pytest.fixture
def beneficial_owners():
    """
    Beneficial owners for business customers.

    B-series ids belong to C009 (valid, totals 100%).
    The rest are deliberately broken in one way each.
    """
    rows = [
        # --- C009: clean, sums to exactly 100 ---
        dict(bo_id="B001", customer_id="C009", bo_name="Alice Fenwick",
             ownership_pct=60.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-08-01"),
        dict(bo_id="B002", customer_id="C009", bo_name="Bruno Gallo",
             ownership_pct=40.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-08-01"),

        # --- C010: ownership sums to 130%, which is impossible ---
        dict(bo_id="B003", customer_id="C010", bo_name="Cara Iyer",
             ownership_pct=80.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-03-01"),
        dict(bo_id="B004", customer_id="C010", bo_name="Dev Raman",
             ownership_pct=50.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-03-01"),

        # --- C011: owner above the 25% threshold is NOT verified ---
        # This is the MLR 2017 reg. 28 duty. 30% > 25%, so verification is required.
        dict(bo_id="B005", customer_id="C011", bo_name="Elena Marsh",
             ownership_pct=30.0, id_verified_flag=False,
             verification_evidence_type=None, verification_date=None),
        dict(bo_id="B006", customer_id="C011", bo_name="Farid Nouri",
             ownership_pct=70.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-01-15"),

        # --- C012: the boundary case. EXACTLY 25.0%. ---
        # MLR 2017 reg. 5 says MORE THAN 25%, so 25.0 does NOT trigger the duty
        # on the ownership limb. A rule written with >= flags this row and is WRONG.
        # See docs/sources.md, note on S4.
        dict(bo_id="B007", customer_id="C012", bo_name="Greta Lind",
             ownership_pct=25.0, id_verified_flag=False,
             verification_evidence_type=None, verification_date=None),
        dict(bo_id="B008", customer_id="C012", bo_name="Hassan Oyelaran",
             ownership_pct=75.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-02-02"),

        # --- ORPHAN: customer_id C999 does not exist in customers ---
        dict(bo_id="B009", customer_id="C999", bo_name="Ivy Pemberton",
             ownership_pct=100.0, id_verified_flag=True,
             verification_evidence_type="passport", verification_date="2025-04-04"),
    ]
    df = pd.DataFrame(rows)
    df["verification_date"] = pd.to_datetime(df["verification_date"], errors="coerce")
    return df


@pytest.fixture
def uk_register_extract():
    """
    Simulated Companies House-style extract.

    IMPORTANT (docs/sources.md, note on S5): under MLR 2017 reg. 28 a bank does NOT
    discharge its duty by relying on the register alone. A mismatch here is a prompt
    to investigate, not proof the bank's record is wrong. Word the rule that way.
    """
    rows = [
        # C009 agrees with beneficial_owners - no mismatch
        dict(registration_number="RC009", customer_id="C009",
             registered_name="Fenwick Gallo Trading Ltd", psc_name="Alice Fenwick",
             psc_ownership_band="50-75%", psc_identity_verified=True),
        # C011: register names someone absent from the bank's own records
        dict(registration_number="RC011", customer_id="C011",
             registered_name="Marsh Nouri Holdings Ltd", psc_name="Zara Quaid",
             psc_ownership_band="25-50%", psc_identity_verified=True),
    ]
    return pd.DataFrame(rows)
