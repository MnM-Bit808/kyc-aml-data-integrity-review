"""
Module 1 data-quality rules.

>>> THESE STUBS ARE YOURS TO WRITE. Claude wrote the signatures and the failing
>>> tests; the bodies are the skill being demonstrated and must be yours.

Convention every rule follows:

    input:  a pandas DataFrame
    output: a boolean Series aligned to that DataFrame's index,
            True where the record FAILS the rule

Returning a boolean Series (rather than a filtered frame or a list of ids) is
deliberate. It composes - you can sum it for a count, combine rules with & and |,
and assign it straight back as a column. Getting comfortable with boolean Series
is most of what "thinking in pandas" means.

Run `pytest -v` to see which rules are still unwritten. Work down the list.
Read the fixture comments in tests/conftest.py before writing each rule - the
known-bad row tells you what the rule has to catch, and often what it must NOT
catch.

Only the record-level errors named in CLAUDE.md Section 8.8 are stubbed here.
Module 1 needs at least 15 rules; the rest are yours to design, and you write
their fixtures and tests too.
"""

import pandas as pd


def missing_mandatory_field(df: pd.DataFrame, column: str) -> pd.Series:
    """
    Flag records where `column` has no usable value.

    Careful: "no usable value" is wider than null. Fixture C004 holds a
    whitespace-only string, which is not null but is just as useless to a
    reviewer. A rule built only on .isna() will pass C004 and be wrong.

    Expected to flag: C003 (None) and C004 (whitespace) for risk_rating.
    """
    raise NotImplementedError("Module 1 rule DQ01 - write me")


def future_date(df: pd.DataFrame, column: str, as_of: pd.Timestamp) -> pd.Series:
    """
    Flag records where `column` holds a date later than `as_of`.

    Note what this catches in the fixture: C005 has the most recent review date
    in the table, so a naive "is the review recent enough" rule would score it as
    the healthiest record in the portfolio. It is actually corrupt.
    """
    raise NotImplementedError("Module 1 rule DQ02 - write me")


def expired_document(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """
    Flag records whose identity document had expired by `as_of`.

    Decide and document: is a document expiring exactly ON the as-of date
    expired? State your choice in docs/data_quality_rules.md. Either answer is
    defensible; failing to notice the boundary exists is not.
    """
    raise NotImplementedError("Module 1 rule DQ03 - write me")


def review_before_onboarding(df: pd.DataFrame) -> pd.Series:
    """
    Flag records reviewed before the customer was onboarded (C007).

    Records with a null on either side are NOT failures of this rule - they are
    already caught by the completeness rule, and double-counting one defect
    across two rules inflates your issue log.
    """
    raise NotImplementedError("Module 1 rule DQ04 - write me")


def implausible_date_of_birth(df: pd.DataFrame, as_of: pd.Timestamp,
                              max_age: int = 120, min_age: int = 18) -> pd.Series:
    """
    Flag implausible ages (C008 is born 1898).

    Thresholds are parameters, not literals in the body - you will be asked why
    you chose 120, and "it is configurable and here is the reasoning" is the
    better answer.
    """
    raise NotImplementedError("Module 1 rule DQ05 - write me")


def ownership_total_exceeds_100(bo: pd.DataFrame) -> pd.Series:
    """
    Flag CUSTOMERS whose beneficial owners' ownership_pct sums above 100 (C010).

    Note the shape change: input is one row per owner, output is per customer.
    Return a boolean Series indexed by customer_id.

    This is one of the five cross-engine reconciliation rules, chosen because
    grouped aggregation is where pandas and SQL most easily disagree about how
    missing values are treated.
    """
    raise NotImplementedError("Module 1 rule DQ06 - write me")


def unverified_owner_above_threshold(bo: pd.DataFrame,
                                     threshold_pct_exclusive: float = 25.0) -> pd.Series:
    """
    Flag customers with an unverified beneficial owner above the threshold.

    THE BOUNDARY MATTERS. MLR 2017 reg. 5 defines a beneficial owner as someone
    holding MORE THAN 25% - strictly greater. Fixture C012 holds exactly 25.0%
    and is unverified, and it must NOT be flagged. A rule using >= fails this
    test, and would over-report the Issuer's exposure in the memo.

    Read `threshold_pct_exclusive` from config/policy.yaml. Never hard-code 25.

    Expected to flag: C011 only.
    """
    raise NotImplementedError("Module 1 rule DQ07 - write me")


def orphan_beneficial_owners(bo: pd.DataFrame, customers: pd.DataFrame) -> pd.Series:
    """
    Flag owner records whose customer_id has no matching customer (B009 -> C999).

    Returns a Series aligned to `bo`, not to customers - the broken record is the
    owner row, and that is what a remediation ticket would point at.
    """
    raise NotImplementedError("Module 1 rule DQ08 - write me")


def register_mismatch(bo: pd.DataFrame, register: pd.DataFrame) -> pd.Series:
    """
    Flag UK business customers whose owners disagree with the register extract.

    Word this carefully, in code and in the issue log. Under MLR 2017 reg. 28 a
    bank does not discharge its duty by relying on the register alone, so a
    mismatch does NOT mean the bank's record is wrong - it means the two sources
    disagree and someone must look. See docs/sources.md, note on S5.

    Expected to flag: C011 (register names a person absent from the bank's own
    records). C009 agrees and must not be flagged.
    """
    raise NotImplementedError("Module 1 rule DQ09 - write me")


def suspicious_uniformity(df: pd.DataFrame, column: str,
                          share_threshold: float = 0.60) -> bool:
    """
    The H3 detector, and the hardest rule in Module 1.

    Every other rule asks "is THIS record wrong?". This one asks "is this COLUMN
    wrong?" - does one value appear so often that it looks auto-filled rather
    than recorded? It returns a single bool about the column, not a Series about
    rows, and that difference is the point.

    Why it matters: a column that is 70% "Low" scores 100% on completeness and is
    still worthless. If you only ever count nulls, you will never find H3, and
    "completeness looked fine and the data was still unusable" is the single best
    story this project can give you about data integrity.

    Think about what the threshold should be before you pick one, and consider
    whether a fixed share is even the right test - a genuinely low-risk portfolio
    could be 60% "Low" honestly. Write your reasoning in
    docs/data_quality_rules.md.
    """
    raise NotImplementedError("Module 1 rule DQ10 - write me")
