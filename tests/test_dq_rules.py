# Written by Claude Code - infrastructure, not analysis
"""
Failing tests for the Module 1 record-level rules.

These are written BEFORE the rules exist. That is the point: the test states what
the rule must do, you make it pass. Run `pytest -v` to see the list.

Every test asserts an EXACT set of flagged ids. Over-flagging fails just as hard
as under-flagging, because a rule that fires on everything produces an issue log
nobody can act on.
"""

import pandas as pd
import pytest

from src import dq_rules


def flagged_ids(mask: pd.Series, df: pd.DataFrame, id_col: str = "customer_id") -> set:
    """Turn a boolean Series into the set of ids it flags."""
    if mask.index.name == id_col or id_col not in df.columns:
        return set(mask[mask].index)
    return set(df.loc[mask, id_col])


# --------------------------------------------------------------------------
# Completeness
# --------------------------------------------------------------------------

def test_missing_risk_rating_catches_null_and_whitespace(customers):
    """C003 is None, C004 is whitespace. Both are unusable; both must be caught."""
    mask = dq_rules.missing_mandatory_field(customers, "risk_rating")
    assert flagged_ids(mask, customers) == {"C003", "C004"}


def test_missing_mandatory_field_does_not_flag_clean_rows(customers):
    mask = dq_rules.missing_mandatory_field(customers, "risk_rating")
    assert not mask.loc[customers["customer_id"].isin(["C001", "C002"])].any()


# --------------------------------------------------------------------------
# Validity
# --------------------------------------------------------------------------

def test_future_review_date_is_invalid(customers, as_of):
    """C005 was 'reviewed' in 2027. It would otherwise look like the best record here."""
    mask = dq_rules.future_date(customers, "last_periodic_review_date", as_of)
    assert flagged_ids(mask, customers) == {"C005"}


def test_implausible_date_of_birth(customers, as_of):
    """C008 is born 1898 - over 120 years old."""
    mask = dq_rules.implausible_date_of_birth(customers, as_of)
    assert flagged_ids(mask, customers) == {"C008"}


# --------------------------------------------------------------------------
# Timeliness
# --------------------------------------------------------------------------

def test_expired_identity_document(customers, as_of):
    """C006's passport expired in January 2025, before the as-of date."""
    mask = dq_rules.expired_document(customers, as_of)
    assert flagged_ids(mask, customers) == {"C006"}


# --------------------------------------------------------------------------
# Consistency
# --------------------------------------------------------------------------

def test_review_cannot_precede_onboarding(customers):
    """C007 was reviewed a year before becoming a customer."""
    mask = dq_rules.review_before_onboarding(customers)
    assert flagged_ids(mask, customers) == {"C007"}


def test_review_before_onboarding_ignores_nulls(customers):
    """
    Rows with a null date are the completeness rule's problem, not this one.
    Counting one defect under two rules inflates the issue log.
    """
    mask = dq_rules.review_before_onboarding(customers)
    assert not mask.loc[customers["last_periodic_review_date"].isna()].any()


# --------------------------------------------------------------------------
# Beneficial ownership
# --------------------------------------------------------------------------

def test_ownership_total_above_100(beneficial_owners):
    """C010's owners sum to 130%."""
    mask = dq_rules.ownership_total_exceeds_100(beneficial_owners)
    assert set(mask[mask].index) == {"C010"}


def test_ownership_total_exactly_100_is_fine(beneficial_owners):
    """C009 sums to exactly 100. A > vs >= slip shows up right here."""
    mask = dq_rules.ownership_total_exceeds_100(beneficial_owners)
    assert not mask.get("C009", False)


def test_unverified_owner_above_threshold(beneficial_owners):
    """C011 has an unverified owner at 30%, which is above 25%."""
    mask = dq_rules.unverified_owner_above_threshold(beneficial_owners)
    assert set(mask[mask].index) == {"C011"}


def test_owner_at_exactly_25_percent_is_not_a_beneficial_owner(beneficial_owners):
    """
    THE BOUNDARY TEST.

    MLR 2017 reg. 5 says MORE THAN 25% - strictly greater. C012's owner holds
    exactly 25.0% and is unverified, and must NOT be flagged. A rule using >=
    fails here, and would overstate the Issuer's exposure in the memo.

    See docs/sources.md, note on S4.
    """
    mask = dq_rules.unverified_owner_above_threshold(beneficial_owners)
    assert not mask.get("C012", False)


def test_orphan_beneficial_owner(beneficial_owners, customers):
    """B009 points at C999, which does not exist."""
    mask = dq_rules.orphan_beneficial_owners(beneficial_owners, customers)
    assert flagged_ids(mask, beneficial_owners, id_col="bo_id") == {"B009"}


def test_register_mismatch(beneficial_owners, uk_register_extract):
    """
    C011's register entry names someone absent from the bank's records; C009 agrees.

    Remember this is a prompt to investigate, not proof the bank is wrong -
    MLR 2017 reg. 28 says the register alone does not discharge the duty.
    """
    mask = dq_rules.register_mismatch(beneficial_owners, uk_register_extract)
    assert set(mask[mask].index) == {"C011"}


# --------------------------------------------------------------------------
# The hard one
# --------------------------------------------------------------------------

def test_suspicious_uniformity_fires_on_a_defaulted_column():
    """
    A column that is 80% one value looks auto-filled, not recorded.
    Completeness would score this column 100%.
    """
    df = pd.DataFrame({"risk_rating": ["Low"] * 80 + ["Medium"] * 12 + ["High"] * 8})
    assert dq_rules.suspicious_uniformity(df, "risk_rating") is True


def test_suspicious_uniformity_quiet_on_a_plausible_spread():
    """A believable mix must not fire, or the rule is useless."""
    df = pd.DataFrame({"risk_rating": ["Low"] * 45 + ["Medium"] * 35 + ["High"] * 20})
    assert dq_rules.suspicious_uniformity(df, "risk_rating") is False


# --------------------------------------------------------------------------
# Placeholder for the rules you design
# --------------------------------------------------------------------------

@pytest.mark.skip(reason="the analyst designs these - at least 5 more to reach 15 rules")
def test_remaining_rules_are_designed_and_tested():
    """
    Module 1 needs 15+ rules across completeness, validity, timeliness and
    consistency. Ten are stubbed. The rest are yours - and writing the fixture
    row IS designing the rule, so do that first.

    Candidates worth considering:
      - periodic review overdue against the risk-based cycle (one of the five
        reconciliation rules, and the one most likely to hide an off-by-one)
      - Japanese information staleness against tenure (the H4 detector)
      - postcode format valid for its market
      - trigger events with no completed review inside the deadline (H7)
      - a business customer with no beneficial owners recorded at all
      - duplicate business entities by name variant (the H5 detector)
    """
