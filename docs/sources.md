# Sources

CLAUDE.md Section 6 rule: **before any regulatory fact appears in a deliverable, verify it
against an official source.** Law-firm and vendor summaries do not count.

Verification pass run 2026-09-20 by Claude Code. Status of every claim below.

**Legend**
- **VERIFIED** — confirmed against the official body's own published material. Safe to use.
- **SECONDARY ONLY** — consistent across law-firm/industry sources, but the official page could
  not be retrieved. **Do not state as fact.** Either verify manually or leave it out.
- **NEEDS REWORDING** — the underlying fact is real but the project's phrasing overstates it.

---

## Australia

| # | Claim | Status |
|---|---|---|
| S1 | AML/CTF Amendment Act 2024; obligations commenced **31 March 2026** for existing reporting entities | **VERIFIED** |
| S2 | Initial customer due diligence has a transitional period running **31 March 2026 to 30 March 2029** | **VERIFIED** |
| S3 | "Ongoing CDD applied from 31 March 2026 **with no transition**" | **NEEDS REWORDING — see below** |

Sources: [AUSTRAC, transitioning existing customers](https://www.austrac.gov.au/industry-and-business/obligations-and-guidance/your-amlctf-program/customer-due-diligence/transitioning-existing-customers) ·
[AUSTRAC, AML/CTF transitional rules 2026](https://www.austrac.gov.au/about-us/legislation/updates-legislation/amlctf-transitional-rules-2026) ·
[Attorney-General's Department, changes to customer due diligence](https://www.ag.gov.au/crime/anti-money-laundering-and-counter-terrorism-financing/anti-money-laundering-and-counter-terrorism-financing-amendment-act/changes-customer-due-diligence)

### S3 — why the wording has to change

The obligation to comply with the **new ongoing CDD requirements from 31 March 2026 is real**, and
the contrast with the three-year initial-CDD transition is real. But "with no transition" is too
strong as written, because pre-commencement customers carry specific relief:

- A reporting entity may keep serving **pre-commencement customers without performing initial CDD**,
  unless a suspicious matter reporting obligation arises, or the nature and purpose of the business
  relationship changes significantly such that the customer's risk becomes medium or high.
- Ongoing CDD for those customers is framed around monitoring for unusual transactions, reviewing and
  updating know-your-customer information at an appropriate frequency, and watching for significant
  changes in the relationship.

**Safe phrasing for the memo:** the new ongoing customer due diligence obligations applied from
31 March 2026, while initial customer due diligence has a transition to 30 March 2029 — so the
timeliness of *ongoing* review is the sharper near-term pressure. That keeps the point the scenario
needs (ongoing review timeliness matters sooner than initial identification) without claiming a
blanket absence of transitional relief.

**One caution not yet resolved.** Different commencement dates appear for different entity
populations — 31 March 2026 for existing reporting entities, and 1 July 2026 features in the
definition of a pre-commencement customer for newly regulated ("tranche 2") sectors. The fictional
Issuer is an existing reporting entity, so 31 March 2026 is the right date for this project. Do not
cite the 1 July 2026 date without checking which population it applies to.

---

## United Kingdom

| # | Claim | Status |
|---|---|---|
| S4 | Beneficial owner = an individual who ultimately owns or controls **more than 25%** of shares or voting rights | **VERIFIED** (MLR 2017 reg. 5) |
| S5 | The bank must take **reasonable measures to verify** the beneficial owner's identity, to the point of being satisfied it knows who they are | **VERIFIED** (MLR 2017 reg. 28) |
| S6 | Companies House identity verification from **18 November 2025**, with a 12-month transition | **VERIFIED** |
| S7 | That Companies House duty falls on companies and individuals, **not on banks** | **VERIFIED** |

Sources: [MLR 2017 reg. 5](https://www.legislation.gov.uk/uksi/2017/692/regulation/5) ·
[MLR 2017 reg. 28](https://www.legislation.gov.uk/uksi/2017/692/regulation/28) ·
[GOV.UK, identity verification rollout from 18 November 2025](https://www.gov.uk/government/news/companies-house-confirms-identity-verification-rollout-from-18-november-2025) ·
[GOV.UK, when you need to verify your identity](https://www.gov.uk/guidance/when-you-need-to-verify-your-identity-for-companies-house)

Note on S4: the threshold is **strictly more than 25%**, not 25% or more. A holding of exactly 25.0%
does not by itself make someone a beneficial owner on the ownership limb. `config/policy.yaml`
already encodes this as `threshold_pct_exclusive`. Any rule using `>=` is wrong.

Note on S6: 18 November 2025 is **the start of a 12-month transition, not a deadline.** Existing
directors confirm verification when they file their next confirmation statement. Saying "the deadline
was 18 November 2025" would be wrong.

### S5 — a finding that changes the UK module design

Regulation 28 also provides that a relevant person does **not** discharge its duty by relying solely
on information delivered to the registrar about registrable persons or beneficial owners.

In plain terms: **a bank cannot satisfy its beneficial-ownership duty by checking Companies House
alone.** This matters for the project because the UK scenario compares `beneficial_owners.csv`
against `uk_register_extract.csv`. That comparison is a **consistency check that raises questions**,
not a verification method, and a mismatch is a prompt to investigate rather than proof that the
bank's record is wrong. Module 1's register-consistency rules should be worded that way, and the
business-reason column should say so. It is also the substantive point about what the UK duty actually requires of a bank.

---

## Japan

| # | Claim | Status |
|---|---|---|
| S8 | FATF 2021 Mutual Evaluation placed Japan in **enhanced follow-up** | **VERIFIED** |
| S9 | FSA AML/CFT Guidelines full compliance due **end-March 2024** | **SECONDARY ONLY** |
| S10 | FATF 5th-round on-site assessment planned for **2028** | **SECONDARY ONLY** |

Sources: [FATF Japan country page](https://www.fatf-gafi.org/en/countries/detail/Japan.html) ·
[FATF Japan follow-up report 2024](https://www.fatf-gafi.org/en/publications/Mutualevaluations/japan-fur-2024.html) ·
[FATF Mutual Evaluation Report, Japan, 2021](https://www.fatf-gafi.org/content/dam/fatf/documents/reports/mer4/Mutual-Evaluation-Report-Japan-2021.pdf)

S8 detail, all confirmed: the mutual evaluation report was adopted at the June 2021 plenary and
published August 2021; Japan was placed in enhanced follow-up; the first follow-up report with
technical-compliance re-ratings was adopted June 2022; subsequent follow-ups re-rated Japan on
several recommendations from partially compliant to largely compliant.

**S9 caution.** The end-March 2024 date is consistent across law-firm and vendor commentary, and an
FSA action plan covering FY2024–2026 was formulated in April 2024, which is consistent with a
milestone having passed in March 2024. But the FSA's own page was not retrieved in this pass, so by
the project's own rule this is not yet citable. Check
[JFSA initiatives in response to the FATF 4th round MER](https://www.fsa.go.jp/en/news/2021/20211221/20211221.html)
before using it. If it cannot be confirmed, drop the date and say only that the FSA guidelines set a
framework-development milestone that has now passed.

**S10 caution.** August 2028 appears in secondary sources as the indicative on-site period, and those
sources themselves describe it as indicative and subject to change. The FATF assessment calendar
returned HTTP 403 and could not be read. **Do not put a 2028 date in the memo.** "Japan remains in
enhanced follow-up ahead of its fifth-round evaluation" is fully supported and sufficient.

---

## American Express

| # | Claim | Status |
|---|---|---|
| S11 | Amex 10-K FY2023 names the UK, EU, Australia, Japan, Canada and Mexico as jurisdictions representing a significant portion of billed business outside the US | **VERIFIED** |

Source: [American Express Form 10-K, FY2023, SEC EDGAR](https://www.sec.gov/Archives/edgar/data/4962/000000496224000013/axp-20231231.htm)

This supports the market-selection rationale only. It does **not** support any customer count,
portfolio size or market split — Amex publishes none of those, and the project's split is a stated
design choice.

---

## Dataset sources (cite exactly)

- IBM Transactions for Anti Money Laundering (AML), Kaggle:
  https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models",
  arXiv:2306.16424

---

## Facts deliberately NOT claimed

- Any customer count, market split or portfolio figure attributed to American Express.
- Any real-world laundering prevalence rate. The project's prevalence is inflated by deliberate
  oversampling.
- Any analyst throughput benchmark. No reliable public source found; all capacity numbers are
  declared assumptions.
- Any FATF fifth-round assessment date for Japan (S10).
- Any FSA compliance deadline date, pending S9 verification.
