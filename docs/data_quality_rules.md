# Data-quality rules (Module 1)

Written by the analyst. One row per rule, filled in BEFORE the rule is coded - the business
reason is what a reviewer will challenge, and writing it first stops the rule from
becoming "whatever the code happens to do".

Target: at least 15 rules spanning all four dimensions.

## Dimensions

- **Completeness** - is the value there at all?
- **Validity** - is the value well-formed and plausible? (Includes suspicious uniformity:
  a field that is always the same value is complete but probably invalid.)
- **Timeliness** - is the value current enough to rely on?
- **Consistency** - does it agree with a related record or an external source?

## Rules

| ID | Dimension | Rule (plain English) | Business reason | Severity | Cross-engine? |
|---|---|---|---|---|---|
| DQ01 | | | | | |
| DQ02 | | | | | |

<!--
Fill "Cross-engine?" with YES for the five rules implemented twice (DuckDB SQL and pandas)
and reconciled under test. CLAUDE.md Module 1 requires at least one per dimension, including
the hardest rule, and requires this document to state WHY those five were chosen.
-->

## Why these five rules were chosen for cross-engine reconciliation

<!-- TODO (the analyst, Day 4) -->

## SQL

<!-- One block per rule. Keep the rule ID in a comment above each query. -->
