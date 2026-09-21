# CLAUDE.md — KYC Health & AML Monitoring Review (Portfolio Project)

> Read this whole file at the start of every session. It is the single source of truth for this project.
> If anything here conflicts with a later instruction from the analyst in chat, the chat instruction wins — but point out the conflict first.
> **Version 3.** Changes from version 2 are listed in Section 0.1.

---

## 0. TL;DR for Claude Code

- **Who:** one analyst, with Claude Code as tutor, reviewer and infrastructure builder. Learner context is in `CLAUDE.local.md` (gitignored, read automatically).
- **What:** A self-directed KYC/KYB data-integrity and AML monitoring review, modelled on a card issuer's **Financial Crime Risk (FCR)** data-integrity function. See Section 1.
- **Data:** IBM's public synthetic Anti-Money Laundering (AML) transfer dataset **plus** a sealed synthetic layer of customers, beneficial owners, card-account activity, and customer changes.
- **Why rigour matters:** every number must be reproducible, defensible in detail, and honestly caveated. A single unverified claim undermines the rest.
- **Your role:** Tutor, reviewer, critic, and infrastructure builder. **The analyst writes all analysis code.** See Section 4.
- **Standard:** Precise, critical, verified. No number, fact, or claim leaves this project unless it was produced by code run in this repo or verified against a named source.
- **Timeline:** 10 days, up to 8 hours/day (≈80 hours). Scope was cut in version 3 to fit that budget honestly. Expect to use the cut order in Section 13 anyway.

### 0.1 What changed in version 3

Six problems were found in version 2 on Day 0, before any code was written. All six are now closed.

| # | Problem in v2 | Resolution in v3 |
|---|---|---|
| 1 | Section 11 required a confidence interval on every headline number, but the 50,000 customers are a **census**, not a sample. An interval around a census proportion measures nothing. | **Census + bounds framing.** Exposure is reported as exact counts and percentages with no interval. Uncertainty is expressed as bounds derived from the *unknown* bucket. Intervals survive only where there is genuine inference: Module 4 effect sizes and Module 5 holdout performance. Module 4's primary test becomes a **permutation test**. See Module 3, Module 4, and Section 11. |
| 2 | "Suspicious-involved" was used across Modules 4 and 5 without ever being defined, while the generator must condition on it. | Two separate labels, never unioned: **`transfer_suspicious`** (defined precisely in Section 8.2) and **`card_suspicious`**. Customer **role** (sender / receiver / both) stored alongside. See Sections 8.2, 8.7. |
| 3 | Module 5 required an out-of-time split, but IBM HI-Small covers only 10 days and laundering patterns straddle any cut. Feasibility was assumed, not checked. | Explicit **Day 2 feasibility check** with a written fallback ladder. See Section 9, Module 5. |
| 4 | 15+ data-quality rules implemented **twice** (SQL and pandas) with fixtures for each — roughly double the available time. | All rules in one engine; **five representative rules** cross-implemented and reconciled. Same validation story, a third of the cost. The separate "3h learn" block is gone; learning is logged inside the build. See Section 9 Module 1, and Section 13. |
| 5 | The only coverage of "unstructured data" was Module 8, which was optional and first on the cut list. | Free-text standardisation moves into **Module 1b** (protected, no external dependency, rules-and-fuzzy-matching baseline). Module 8 becomes *Claude versus that baseline*, which is a stronger model-risk story anyway. |
| 6 | Section 8.4 claimed the analyst was blind to the planted answers, but the analyst wrote H1–H8. | Claim reworded honestly. See Section 8.5. |

Two smaller fixes: **pre-register Module 4's hypothesis** in writing before touching the data, and lock package versions in `requirements.lock.txt` so a clean run is reproducible.

**Correction, Day 1.** Version 3 also advised avoiding Python 3.14 on the grounds that a package might not have a pre-built wheel. That was tested rather than assumed, and it was wrong - all 13 packages installed and imported cleanly. The advice is withdrawn; see Section 12.

---

## 1. Project goal

Answer one leadership question for a **fictional** international card issuer: *how exposed are we
to recent customer-due-diligence regulatory changes, what do we fix first, and can the team cope
without degrading the customer experience?* The full scenario is in Section 5.

The work is modelled on a card issuer's Financial Crime Risk (FCR) data-integrity function:
KYC/KYB data-health monitoring, issue management, exposure analysis, risk prioritisation,
transaction-monitoring rule tuning and capacity planning, communicated through a dashboard and a
short leadership memo.

The method is the point: SQL and Python analytics over large structured and unstructured data,
explicit reasoning about what each number is and is not estimating, reproducible outputs, and
honest reporting of limitations and null results.
---

## 2-3. Learner context (not committed)

This is a self-directed learning project. Context about the analyst and the teaching
calibration that follows from it lives in `CLAUDE.local.md`, which is gitignored and read
automatically by Claude Code alongside this file. Session behaviour is unchanged by the split.

What belongs here, because it is about the project rather than the person: **the analyst writes
all analysis code themselves** (Section 4), and no number or claim leaves this project unless
code in this repository produced it or a named source verified it.

---

## 4. Working agreement: who does what

This project must produce **genuine skill**, not just artefacts. The work must be defensible in detail.

### The analyst writes (Claude must NOT write this code)
- All data exploration, cleaning, data-quality rule logic, free-text standardisation logic, analysis, statistical tests, monitoring rules, rule tuning, capacity model, priority score, and chart code.
- All SQL queries for data-quality checks.
- The memo, issue log entries, and findings text (Claude reviews and critiques).

### Claude may build directly
- Environment setup, folder structure, `requirements.txt`, git initialisation, `.gitignore`, `.claude/settings.json`.
- The **sealed synthetic data generator** — in a separate, isolated session only (Section 8.5).
- Test scaffolding (pytest fixtures with known-bad records) — the analyst writes the functions the tests check.
- Utility code unrelated to the skills being demonstrated (e.g. a CSV export helper for Power BI).
- Label every Claude-written file in its header: `# Written by Claude Code — infrastructure, not analysis`.

### When the analyst is stuck — the hint ladder (one rung at a time)
1. Ask what they have tried and what they expect to happen.
2. Explain the concept in plain language.
3. Point to the relevant function/documentation.
4. Give pseudocode.
5. Give a partial snippet with gaps.
6. Only if they explicitly ask: a full solution — then they retype it and explain it back line by line before moving on.

### Every session ends with a check (non-negotiable)
Quiz the analyst for 10–15 minutes on what was built: explain code, interpret a number, defend a choice. Log gaps in `logs/learning_log.md`.

**Version 3 note:** version 2 budgeted three hours a day of separate "learning" before building. That was fiction — nobody learns pandas for three hours and then applies it for four. Learning now happens inside the build and is recorded in `logs/learning_log.md` as it occurs. The explain-back hour is the protected block; if a day runs long, cut build scope, never the explain-back.

---

## 5. The scenario (the story every module serves)

> A new analyst joins FCR Data Integrity at a **fictional** international card issuer ("the Issuer"). Recent regulatory changes in three markets raise the bar on customer due diligence. Leadership asks:
> **"How exposed are we, what do we fix first, and can the team cope — without degrading the customer experience?"**

### The five questions (each module answers part of one story)

1. **Can we even measure our exposure?** (data integrity) — If risk ratings, review dates, or beneficial-owner records are missing or defaulted, compliance status is unknowable. *Data integrity determines whether the Issuer can comply at all.*
2. **How exposed are we?** (analysis) — Customers overdue on **periodic** reviews and **trigger-based** reviews, by market and segment, with the unknown share stated explicitly as a bound.
3. **Who do we re-verify first?** (risk prioritisation) — Transparent priority score + statistical test of whether poor-data customers are more likely to show suspicious activity.
4. **Can the team cope?** (capacity) — Backlog vs analyst capacity, time to clear, scenarios.
5. **Where do we find capacity, and at what cost to customers?** (monitoring rule tuning) — Cut false alerts while preserving detection; convert saved hours into review capacity; measure customer contacts and card blocks avoided. **Closes the loop back to Questions 2 and 4:** alerts create trigger-based reviews and consume analyst time.

---

## 6. Markets, regulatory hooks, and the policy scenario

Markets chosen because American Express's Form 10-K for fiscal year 2023 names the UK, EU, Australia, Japan, Canada and Mexico as jurisdictions representing a significant portion of billed business outside the US.

| Market | Real context (verify on official sources before citing) | Data problem it tests |
|---|---|---|
| **Australia** | Anti-Money Laundering and Counter-Terrorism Financing (AML/CTF) Amendment Act 2024; reforms commenced 31 March 2026 for existing reporting entities; initial customer due diligence (CDD) has a transition to 30 March 2029, while the **new ongoing CDD obligations applied from 31 March 2026** - so ongoing review timeliness is the sharper near-term pressure. **Verified 2026-09-20, with a correction:** pre-commencement customers carry specific relief from initial CDD, so "no transition" overstates it. Read `docs/sources.md` note S3 before wording this in any deliverable. Reforms shift toward an outcomes- and risk-based approach. | Timeliness of ongoing reviews, especially **trigger-based** ones; backlog; capacity |
| **United Kingdom** | The **bank's** duty comes from the Money Laundering, Terrorist Financing and Transfer of Funds Regulations 2017 (MLR 2017): identify beneficial owners (generally those owning or controlling **more than 25%**) and take reasonable measures to verify their identity. Separately, the Economic Crime and Corporate Transparency Act 2023 introduced mandatory identity verification of directors and People with Significant Control (PSCs) **at Companies House** from 18 November 2025 (12-month transition). That duty falls on companies and individuals, not banks — its relevance is that the register banks check against becomes more reliable. **Verified 2026-09-20, important:** MLR 2017 reg. 28 also provides that a bank does **not** discharge its duty by relying on the register alone. The register comparison is therefore a **consistency check that raises questions, not a verification method**, and a mismatch is a prompt to investigate rather than proof the bank's record is wrong. Module 1's register rules and their business-reason column must say so. See `docs/sources.md` note S5. | Beneficial-owner completeness, verification evidence, and consistency with a (simulated) register extract (KYB) |
| **Japan** | Financial Action Task Force (FATF) 2021 Mutual Evaluation placed Japan in enhanced follow-up (weaknesses incl. politically exposed persons and beneficial ownership); full compliance with the Financial Services Agency (FSA) AML/CFT Guidelines was due end-March 2024; FATF fifth-round assessment still ahead. **Verified 2026-09-20:** the 2021 evaluation and enhanced follow-up are confirmed, but the end-March 2024 FSA date and the 2028 assessment date are **secondary-source only and not citable** - see `docs/sources.md` notes S9 and S10. Use "Japan remains in enhanced follow-up" instead of any date. | Stale information on long-tenured customers |

**Rules for regulatory content:**
- The project **simplifies** these regimes into a fictional internal policy "inspired by" them. Never present it as an accurate legal model.
- Real regimes are **risk-based and often event-driven**, not purely calendar-based. The scenario must reflect both routes (below).
- Before any regulatory fact appears in a deliverable, verify it against an **official source** (AUSTRAC, legislation.gov.uk, GOV.UK / Companies House, FSA Japan, FATF). Several facts above came from law-firm and industry summaries. Record verified sources in `docs/sources.md`.
- If a fact cannot be verified, say so and leave it out.

### Fictional Issuer policy (all parameters are assumptions in `config/policy.yaml` — never hard-code)

Every customer is subject to **two review routes**:
1. **Periodic review** — due within a risk-based cycle (illustrative: High = 1 year, Medium = 3 years, Low = 5 years).
2. **Trigger-based review** — due within N days (illustrative: 30) of a trigger event: a monitoring alert (transfer or card rule), a material change (address, ownership, name, occupation), or a Politically Exposed Person (PEP) status change.

Market emphasis:
- **Australia:** trigger-based review timeliness is the headline measure, plus periodic reviews.
- **UK:** every business customer must have all beneficial owners above 25% identified (**strictly more than 25%** - MLR 2017 reg. 5 verified; a rule using `>=` is wrong and overstates exposure), with verification evidence recorded; records should be consistent with the register extract - treating disagreement as a question to investigate, not as proof of error.
- **Japan:** customer information (address, occupation, purpose of account) must be refreshed within the periodic cycle; customers onboarded before a cutoff date are the focus.

---

## 7. Deliverables

| # | Deliverable | Format | Cuttable? |
|---|---|---|---|
| D1 | KYC/KYB data health report (scores by market × customer type × dimension) | Notebook + CSV outputs | No |
| D2 | Free-text standardisation baseline + coverage/error report | Notebook + `outputs/standardisation_baseline.csv` | No |
| D3 | Issue log (≥10 issues) | `outputs/issue_log.csv` + markdown | No |
| D4 | Exposure analysis (periodic + trigger-based) with explicit unknown bounds | Notebook | No |
| D5 | Prioritised review list + pre-registered statistical test | Notebook + CSV | No |
| D6 | Monitoring rule tuning (transfer rules + card rules) incl. customer-experience metrics | Notebook | Transfer rules no; card rules yes |
| D7 | Capacity model with scenarios | Notebook + `config/capacity.yaml` | No |
| D8 | Power BI dashboard (3 pages) | `.pbix` + screenshots | Page 3 yes |
| D9 | 2-page leadership memo (incl. limitations and merchant-side gap) | `docs/memo.md` (+ PDF) | No |
| D10 | Answer-key comparison ("found vs planted") | `docs/answer_key_review.md` | No |
| D11 | README (story, how to run, limitations) | `README.md` | No |
| D12 (optional) | Claude-assisted standardisation **measured against the D2 baseline** + validation note | Notebook + `docs/validation_note.md` | Yes — first cut |

---

## 8. Data

### 8.1 Transfers — IBM synthetic AML dataset (public benchmark)
- Source: Kaggle, "IBM Transactions for Anti Money Laundering (AML)" — `https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml`. Paper: Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models" (arXiv 2306.16424).
- Use **HI-Small** (≈5M transactions, ≈515K accounts, ≈5.1K laundering transactions, 10 days in September 2022) and `HI-Small_Patterns.txt`.
- Expected columns (verify on load): Timestamp, From Bank, Account, To Bank, Account.1, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering.
- **The analyst downloads it manually** (it requires the analyst's Kaggle login). Claude never handles the analyst's credentials or API keys.
- Account identity = (Bank, Account) pair. Verify uniqueness before relying on it.
- **Role in the project:** an independent, labelled benchmark for learning transaction-monitoring **method**. It simulates bank transfers, not card activity — see Section 10.

### 8.2 The `transfer_suspicious` label — exact definition

Modules 4 and 5 both depend on this, and the generator conditions H2 and H6 on it, so it is defined once here and used everywhere without variation.

> A customer is **`transfer_suspicious = 1`** if **any** transaction in the sampled transfer data has `Is Laundering = 1` and that customer's `(bank_id, account_id)` appears as either the sending or the receiving party.

Alongside it, store **`suspicious_role`** ∈ {`sender`, `receiver`, `both`, `none`}. Both the generator and the analyst's Day 2 exploration derive these from the same public IBM data using this same rule, independently — they must match, and that is worth checking.

**Why this definition, and what is wrong with it.** IBM flags a *transaction*, which has two parties. An entirely innocent counterparty who merely received a payment from a launderer inherits the flag. That dilutes the positive class with bystanders. This was chosen deliberately over an originator-only definition for three reasons: it is the dataset's own benchmark label; it mirrors what a bank actually sees, since a bank cannot tell originator from bystander at alert time either; and it keeps the positive class large enough for the Module 5 holdout. The `suspicious_role` column exists so the effect of this choice can be measured rather than assumed — check on Day 2 how many accounts are receiver-only, and report it.

**Never union `transfer_suspicious` with the card layer's `card_suspicious`.** They cover different periods (10 days vs 12 months) and mean different things. Section 10.3 forbids treating them as one timeline; a union label would quietly break that. Module 4 tests against `transfer_suspicious` only.

### 8.3 Sampling rules
- Target universe: **50,000 accounts**, which by construction **are** the Issuer's entire portfolio. This is a data-engineering step to build a fictional portfolio, not statistical sampling from a population of interest. That distinction drives Section 11.
- Stratified sample: oversample laundering-involved accounts so enough exist for rule evaluation. **Record sampling weights.** Report the portfolio's prevalence as what it is, and state plainly wherever it appears that it is inflated by oversampling and is not a real-world rate. Do not present it as an estimate of anything.
- Keep **every transaction where a sampled account is sender or receiver.** Counterparties outside the sample have no customer record (realistic).
- Fixed random seed; sampling code committed; sample reproducible.
- Day 2 exploration: check whether currency distribution could support a currency-based market mapping (UK Pound → UK, Australian Dollar → Australia, Yen → Japan). If it cannot produce the target split cleanly, markets are assigned by the generator. Record the decision in `logs/decision_log.md`.

### 8.4 Market split (design choice, not fact — Amex does not publish customer counts by market)

| Market | Customers | Business share | ≈Business customers |
|---|---|---|---|
| UK | 21,000 | 25% | 5,250 |
| Australia | 18,000 | 15% | 2,700 |
| Japan | 11,000 | 12% | 1,320 |
| **Total** | **50,000** | | **≈9,270** |

**Why small cells still matter under a census framing.** Version 2 justified a minimum cell size with a margin-of-error calculation. That reasoning does not apply: these are counts of every customer in the cell, so they are exact. The real reasons to flag cells below ~300 are different and should be stated that way:
1. A single record moves the percentage by more than a third of a point, so the number is brittle to one data error.
2. Market-to-market and segment-to-segment **comparisons** drawn from small cells are unstable, and a difference between a 1,320-customer cell and a 5,250-customer cell can look large while resting on a handful of records.
3. Any Module 4 test restricted to a small cell has little power to detect a real effect.

Flag cells below ~300 in outputs and never build a headline claim on one.

### 8.5 Sealed synthetic layer — generation protocol

**What this solves, stated honestly:** the analyst wrote hypotheses H1–H8, so they know which **classes** of defect were planted. The seal hides magnitudes, locations, and presence. The honest claim is therefore:

> "I knew which classes of defect existed in the data. I did not know whether any given one was actually present, which records carried it, or how large it was — and several could be drawn as zero effect, so the null results are real."

That is a weaker claim than "blind analysis," and it is the true one. Do not let it be overstated in the README or the memo.

1. Generation happens in a **separate Claude Code session** started only for this purpose. That session writes `generator/generate.py`, runs it, and ends.
2. The generator **draws hidden parameters at random at run time** (within the ranges agreed in brainstorming) using a secret seed stored only in the answer key, so reading the generator code does **not** reveal the answers.
3. The generator derives `transfer_suspicious` and `suspicious_role` from the IBM data using the Section 8.2 rule, and conditions H2 and H6 on `transfer_suspicious`.
4. Outputs to `data/raw/`: `customers.csv`, `beneficial_owners.csv`, `uk_register_extract.csv`, `customer_changes.csv`, `card_statements.csv`, `card_activity.csv`, and `card_labels.csv` (`customer_id`, `card_suspicious` - one row per account, kept out of the event-level activity file so the label is not repeated per event). To `data/processed/`: `customer_labels.csv`, `sampling_weights.csv`, `sampled_transactions.parquet`.
5. Output to `sealed/answer_key.json`: drawn parameters, planted-issue counts, IDs of planted records, true typology labels (including those deliberately left unlabelled).
6. `.claude/settings.json`: `{"permissions": {"deny": ["Read(./sealed/**)"]}}`. **Test on Day 1 that this block works** (ask a working session to read the file and confirm it is refused). Add `sealed/` to `.gitignore` until Day 10.
7. **Working sessions must never read, grep, list, or infer from `sealed/`.** If asked, refuse and remind the analyst.
8. Honour system for the analyst too: they do not open `sealed/` **or `generator/generate.py` and `generator/acceptance_checks.py`** until Day 10. The code reveals *how* defects were planted - including the exact messy-text variants - which would contaminate Module 1b's synonym map and the H5 duplicate detection. Working sessions are blocked from reading them by `.claude/settings.json`. `GENERATOR_SPEC.md` is fine to read; it describes design, not mechanism.
9. Synthetic names via `Faker` (locales `en_GB`, `en_AU`, `ja_JP`). No real people, companies, or registration numbers.

### 8.6 Customer schemas (generator output)

`customers.csv`
| Column | Notes |
|---|---|
| customer_id | Primary key |
| bank_id, account_id | Link to IBM transfers |
| market | UK / AU / JP |
| customer_type | Individual / Business |
| onboarding_date | |
| last_periodic_review_date | Can be missing / defaulted (planted) |
| risk_rating | High / Medium / Low; can be missing / defaulted (planted) |
| id_doc_type, id_doc_expiry | Individuals |
| date_of_birth | Individuals |
| full_name / business_name | Faker, locale-appropriate |
| registration_number | Businesses; fake format |
| address_line, city, postcode | Messy variants planted |
| occupation_text, industry_text, purpose_of_account_text | Free text, messy (unstructured) — input to Module 1b |
| pep_flag | Politically Exposed Person flag |
| info_last_refreshed_date | Japan freshness test |

`beneficial_owners.csv` — bo_id, customer_id, bo_name, ownership_pct, id_verified_flag, verification_evidence_type, verification_date. Planted: missing owners, totals >100%, unverified owners above 25%.

`uk_register_extract.csv` — simulated Companies House-style extract for UK business customers: registration_number, registered_name, psc_name, psc_ownership_band, psc_identity_verified. Planted: mismatches with `beneficial_owners.csv`.

`customer_changes.csv` — change_id, customer_id, change_date, change_type (address / ownership / name / occupation / pep_status), review_completed_date (nullable). Trigger source for trigger-based reviews.

### 8.7 Card-activity layer (card-specific typologies)

Purpose: show understanding of how laundering works **through card accounts**, which the IBM transfer data does not cover.

`card_statements.csv` — customer_id, statement_month, statement_balance, credit_limit, currency. 12 months.

`card_activity.csv` — event_id, customer_id, event_date, event_type, amount, currency, counterparty_id, channel. Event types:
- `payment` (payment into the card account; `counterparty_id` = payer; third-party payers possible)
- `refund_request` (customer requests a credit-balance refund)
- `merchant_refund` (credit from a merchant)
- `cash_advance`
- (Everyday purchases are summarised in statements, not stored as events, to keep volume manageable — target under 2M rows.)

Planted typologies (prevalence randomised; may be zero):
- **Overpayment and refund cycling:** payments well above the statement balance followed by credit-balance refund requests.
- **Third-party funding:** payments from multiple unrelated payers into one card account.
- **Refunds without matching purchases:** merchant refunds exceeding plausible purchase history (hint of merchant collusion).
- **Cash-advance velocity:** clustered cash advances soon after large payments.

**`card_suspicious` label:** provided at account level, **deliberately incomplete** — a hidden share of truly suspicious accounts is unlabelled (as in real life, where much laundering is never detected). Measured precision on card rules is therefore understated; the true figure is revealed on Day 10. This label is entirely separate from `transfer_suspicious` and is never combined with it.

**Honest limitation:** the card layer covers 12 months; IBM transfers cover 10 days. They are separate behaviour sources joined only by customer. Never analyse them as one timeline.

### 8.8 Hidden patterns (proposed — confirm in the first brainstorming session before generation)

Each has a randomised magnitude, and **each may be drawn as "no effect"**, so null results are possible and must be reported honestly.

- **H1 — Market quality ranking:** which market is worst on each data-quality dimension.
- **H2 — Gaps ↔ suspicious activity link:** association between KYC data gaps and `transfer_suspicious` as defined in Section 8.2 (odds ratio drawn from a range that includes 1.0).
- **H3 — Default-value trap:** in one market a field is auto-filled (e.g. risk_rating = "Low", or last_periodic_review_date = onboarding_date), making completeness look high while validity is poor.
- **H4 — Stale long-tenure customers:** Japanese information freshness degrades with tenure.
- **H5 — Duplicate business entities:** UK businesses duplicated under name/address variants.
- **H6 — Risk misclassification:** accounts with `transfer_suspicious = 1` carry a Low rating.
- **H7 — Trigger neglect:** a share of change events never produced a completed review, concentrated in one market.
- **H8 — Label incompleteness:** share of truly suspicious card accounts left unlabelled.
- **Record-level errors:** invalid formats, future dates, expired documents, orphan beneficial owners, ownership >100%, missing mandatory fields, register mismatches.

---

## 9. Modules — specification and acceptance criteria

Each module gets a written plan in `docs/plans/` before coding (Superpowers `writing-plans`) and closes only after `verification-before-completion`.

### Module 1 — KYC/KYB data integrity (answers Q1)
- ≥15 rules across **completeness, validity, timeliness, consistency** (including UK register consistency). Each rule in `docs/data_quality_rules.md`: ID, dimension, plain-English rule, business reason, SQL, severity.
- **Implementation (changed in v3):** implement all rules in **one engine** of the analyst's choice. Then pick **five representative rules** — at least one per dimension, including the hardest one — and implement those a second time in the other engine, reconciling exactly under test.
- Output: pass/fail per record per rule; health scores by market × customer type × dimension.
- **Acceptance:** pytest tests with known-bad fixtures for every rule (Test-Driven Development); the five-rule cross-engine reconciliation passes; at least one rule detects suspicious uniformity (default values), not just nulls; `docs/data_quality_rules.md` states *why* those five were chosen as representative.

### Module 1b — Free-text standardisation baseline (unstructured data, protected)
Moved into the protected set in version 3, because it was the project's only coverage of the "unstructured data" requirement and was previously first on the cut list.
- Standardise `occupation_text`, `industry_text`, and `business_name` using **rules and fuzzy matching only** — normalisation, token cleanup, a hand-built synonym map, and a string-similarity match (e.g. `rapidfuzz`). No external application programming interface (API), no network dependency, nothing that can fail on Day 9.
- Feeds H5 (duplicate business entities) directly: name-variant matching is the detection method.
- Report **coverage** (share of records mapped to a standard value), **residual** (share left unmapped), and a hand-inspected sample of errors in both directions.
- the analyst hand-labels ~100 records to measure against. These same 100 labels are reused by Module 8 if it survives.
- **Acceptance:** measured coverage and error rate, not asserted; the ~100 hand labels committed; error examples logged with the reason each failed.

### Module 2 — Issue management
- ≥10 issues in `outputs/issue_log.csv`: issue_id, title, description, rule_ids, affected_count, affected_pct, market, severity (criteria defined first), suspected root cause, proposed remediation, owner (role), status, date_raised.
- **Acceptance:** severity criteria written before rating; every affected_count traceable to a query.

### Module 3 — Exposure analysis (answers Q2)
- Periodic exposure: customers outside their risk-based cycle.
- Trigger exposure: change events and alerts without a timely completed review.
- Three states always: **compliant, non-compliant, unknown (data insufficient)**. Unknown is never dropped or counted as compliant.
- **No confidence intervals on exposure figures.** The 50,000 customers are the whole portfolio (Section 8.3). A proportion computed over every unit is an exact count, not an estimate, and an interval around it measures nothing. Report counts and percentages exactly.
- **Express uncertainty as bounds instead.** Every headline exposure figure is reported as a range whose width is the unknown share:
  > "Between X% and Y% of the portfolio is non-compliant. The spread is not statistical noise — it is the share of customers whose compliance status cannot be determined from the Issuer's own records."

  This is exactly true, it answers Question 1 in one sentence, and it feeds Module 2 directly.
- **Acceptance:** every headline number has a count and a bound; the lower bound assumes all unknowns compliant and the upper bound assumes all non-compliant, and this is stated; unknowns explicit everywhere; periodic and trigger exposure reported separately and combined without double-counting; no confidence interval appears anywhere in this module, and the README explains why.

### Module 4 — Prioritisation + statistical test (answers Q3)
- **Pre-register first.** Before loading any data, write into `docs/plans/module4_preregistration.md`: the hypothesis, the exact definition of "has data gaps", the test, the significance threshold, and what result would count as a null. Commit it. This converts "I tested my own generator" into "I stated a prediction and tested it" — which is what makes the result defensible at all: a prediction stated before the data was seen.
- **Primary test: a permutation test.** Shuffle the "has data gaps" labels many times (10,000), recompute the association each time, and locate the observed value in that distribution. This is the correct test on census data, because its logic rests on random reassignment rather than on sampling from a population. It is also easier to understand and to explain out loud than the chi-square distribution.
- **Chi-square is optional and secondary.** If reported, state that it approximates the permutation result and that its usual justification (random sampling) does not hold here; check expected cell counts ≥5.
- Report **effect sizes with confidence intervals** (risk ratio, odds ratio). Intervals are legitimate here: the target of inference is the relationship in the generating process, not a count of the portfolio.
- Holm correction when testing across markets/segments.
- Optional: logistic regression (statsmodels) controlling for market and customer type; interpret as odds ratios; association, not causation.
- Priority score: transparent weighted formula; **sensitivity analysis** (how much the top-1,000 list changes if weights move ±25%).
- **Acceptance:** the pre-registration was committed before the data was touched (check the git history); the permutation test is implemented and its logic explained in the notebook in plain language; effect sizes reported with intervals; sampling weights handled or limitation stated; no causal language; the result is framed as "recovered/not recovered the planted relationship", not a real-world finding.

### Module 5 — Monitoring rules, tuning, and customer experience (answers Q5)
**Transfer rules (IBM data), 3–4 of:** large single transfer; fan-out; fan-in; structuring just below a threshold; unusual payment format or cross-currency activity. Document currency handling.
**Card rules (card layer), at least 2:** overpayment-and-refund cycling; third-party funding. Optional: refunds without matching purchases; cash-advance velocity.
- Ground truth: `transfer_suspicious` for transfer rules, `card_suspicious` for card rules. Never mixed.
- Metrics per rule and combined: alerts, true/false positives, **precision, recall**, alerts per 1,000 accounts, analyst hours. Precision and recall measured on held-out data get confidence intervals — this is genuine inference about unseen data.
- **Customer-experience metrics:** customer contacts per 1,000 accounts (alert follow-ups + review document requests) and temporary card blocks per 1,000 accounts (block rate per alert is an assumption in `config/capacity.yaml`).
- Threshold sweep → precision/recall trade-off chart, with customer contacts on the same view.
- Report how many flagged accounts are **receiver-only** (`suspicious_role`), and what that does to precision. This is the honest consequence of the Section 8.2 label choice.

**Out-of-time validation — Day 2 feasibility check (added in v3).** HI-Small covers only 10 days. Before committing to a time split, measure three things and record them in `logs/decision_log.md`:
1. How many `transfer_suspicious` accounts fall in the proposed holdout window.
2. How many laundering patterns in `HI-Small_Patterns.txt` straddle the cut point (a fan-out running from day 4 to day 8 becomes two unlabelled fragments).
3. Whether laundering is distributed evenly across the 10 days or concentrated.
4. How many transactions fall **after 10 September 2022**, and whether they are all laundering. The dataset author notes that transactions beyond the stated date range exist and are all laundering. If they land in the evaluation window, the tail of the holdout is 100% laundering and every rule looks better than it is. Decide explicitly whether to exclude them, and record why.

Then take the first rung of this ladder that the data supports, and state in the README which one was used and why:
1. **Time split** — preferred. Tune on the earlier period, evaluate once on the later period. Requires enough positives in the holdout for the precision estimate to be stable.
2. **Time split with pattern-aware cut** — assign each whole pattern to one side to avoid severed sequences.
3. **Account-level cross-validation** — split by account, not time. Weaker (it cannot detect drift) but stable. Must be labelled as a fallback, with the reason.

Whichever is used: **never report tuned performance on tuning data.**
- Explain why accuracy is meaningless at ~1-in-1,000 base rates, and why card-rule precision is understated (H8).
- **Acceptance:** the feasibility check is recorded with numbers; the chosen validation rung is named in the README with its justification; out-of-sample results reported; hours saved and customer impact derived from stated assumptions; alerts feed Module 3 trigger reviews.

### Module 6 — Capacity model (answers Q4)
- Inputs in `config/capacity.yaml` (labelled assumptions, sourced where a public benchmark exists — and where none exists, say so rather than citing vendor marketing): analyst headcount, working days, reviews per analyst-day by type/risk, minutes per alert, block rate per alert.
- Demand = periodic backlog + trigger reviews + alert handling.
- Outputs: backlog size, months to clear, scenarios (baseline / +headcount / rule tuning frees hours / phased deadline).
- **Acceptance:** every scenario reproducible from config; sensitivity to the two most uncertain assumptions shown; the memo leads with the sensitivity, not the point estimate.

### Module 7 — Power BI dashboard + leadership memo
- Pages: (1) Data health by market/type/dimension; (2) Exposure and backlog burndown; (3) Rule performance, trade-off, and customer impact.
- Exposure visuals show the unknown band explicitly — it is a finding, not a gap to hide.
- Power BI reads exported CSVs in `outputs/powerbi/`. The analyst builds it.
- Memo (2 pages max): answers the leadership question; states assumptions and limitations; recommends actions with expected effect; names the **merchant/acquiring-side gap** as out of scope and a next step.
- **Acceptance:** every number traceable to an output file; abbreviations spelled out.

### Module 8 (optional, first to cut) — Claude-assisted standardisation vs the Module 1b baseline
- Use the Claude API to standardise the same free text Module 1b handled, and **compare against that baseline** on the same ~100 hand-labelled records. A model-risk assessment with no baseline is much weaker than one with a baseline; that comparison is the point of the module.
- On Day 10, evaluate both against the answer key.
- Validation note (2–3 pages, model-risk style): objective, design, **results versus baseline**, failure modes (hallucination, inconsistency, sensitivity to phrasing), a basic prompt-injection test via free-text fields, risk rating, recommended controls, scale / don't-scale decision.
- **Acceptance:** error cases logged with examples; no accuracy claim without a measured number; the scale/don't-scale decision references the baseline comparison, and "don't scale" is an acceptable — possibly the better — answer.

### Module 9 — Answer-key review (Day 10)
- Only now open `sealed/answer_key.json`. Compare every finding with the planted truth: found, missed, or wrongly "found". Write `docs/answer_key_review.md` honestly. Misses are the most valuable material the project produces - they show where the method has blind spots.

---

## 10. Known limitations (state these in README and memo; never hide them)

1. **Transfers ≠ cards.** IBM data simulates bank transfers. It demonstrates monitoring method, not card-issuer behaviour. The card layer partly addresses this but is self-generated.
2. **Partial circularity.** Relationships in the synthetic layer exist because the generator planted them. Statistical tests show whether the method **recovers a known truth**, not facts about real customers. Module 4 is pre-registered to make that test honest, not to make it real-world evidence.
3. **Separate timelines.** IBM transfers (10 days) and card activity (12 months) are joined only by customer, and their two suspicion labels are never combined.
4. **The positive class contains bystanders.** `transfer_suspicious` flags both parties to a laundering transaction, so innocent counterparties are counted as suspicious (Section 8.2). This understates precision. The `suspicious_role` breakdown quantifies it.
5. **Simplified regulation.** The policy is fictional and inspired by real regimes; not legal advice or a legal model.
6. **Issuing only.** Merchant (acquiring-side) due diligence — a major financial-crime area for the team — is out of scope.
7. **Assumption-driven capacity and customer impact.** Results depend on stated assumptions; sensitivity shown.
8. **Oversampled prevalence.** Laundering prevalence in the portfolio is inflated by design and is not a real-world rate. It is never presented as an estimate of one.
9. **Known defect classes.** The analyst wrote H1–H8; the seal hides magnitude, location and presence, not the categories (Section 8.5).

---

## 11. Statistical rigour checklist (every analysis)

Rewritten in version 3 around one question that version 2 never asked: **what is this number estimating?**

- [ ] State the question and the null hypothesis **in writing, before** running the test.
- [ ] **Decide whether the number is a census fact or an estimate.** A count over every customer in the portfolio is exact — report it exactly, with no interval. A quantity inferred about a relationship or about unseen data is an estimate — report it with an interval.
- [ ] Report counts alongside percentages, always.
- [ ] Express uncertainty on exposure as **bounds from the unknown bucket**, never as a confidence interval.
- [ ] Confidence intervals appear in exactly two places: **Module 4 effect sizes** and **Module 5 held-out precision and recall**. If one appears anywhere else, justify it or delete it.
- [ ] Effect sizes, not only p-values. Never say "significant" without the effect size.
- [ ] On census data, prefer a **permutation test**. If using chi-square, say it is an approximation whose usual justification does not apply, and check expected cell counts ≥5.
- [ ] Holm correction when testing across markets/segments.
- [ ] Rare events: precision and recall, never accuracy.
- [ ] Out-of-sample evaluation for anything tuned; if a time split was not feasible, name the fallback used and why.
- [ ] Association ≠ causation. Synthetic data ≠ real-world evidence.
- [ ] Oversampling inflates prevalence — say so wherever prevalence appears.
- [ ] Flag any cell below ~300 and never build a headline on one.
- [ ] Seeds fixed; results reproducible from a clean run.

---

## 12. Tech stack and repository

- **Python 3.14.2** in a virtual environment at `.venv/`. Verified working on Day 1: pandas 3.0.6, numpy 2.5.3, pyarrow 25.0.1, duckdb 1.5.5, scipy 1.18.1, statsmodels 0.15.0, matplotlib 3.11.2, seaborn 0.13.2, rapidfuzz 3.14.6, faker, pyyaml 6.0.3, pytest 9.1.1, anthropic 1.7.0. Exact versions are pinned in `requirements.lock.txt`; install from that file to reproduce a clean run.
- **Note on pandas 3.** This is pandas 3.0, not 2.x. Filtering, grouping, merging and missing-value handling are unchanged, but pandas 3 changed the default dtype for string columns. Most tutorials online still target pandas 2.x, so if a tutorial says a text column should show as `object` and it shows as something else, that is the version difference, not a mistake. Relevant to the data-quality rules in Module 1, which test for empty and malformed strings.
- Jupyter notebooks in VS Code for learning; reusable logic moved into `src/` functions with tests.
- Libraries: pandas, numpy, duckdb, pyarrow, scipy, statsmodels, matplotlib, seaborn, faker, rapidfuzz, pyyaml, pytest, anthropic (Module 8 only).
- Power BI Desktop (Windows).
- Check machine RAM before loading the full 5M-row file into pandas; prefer DuckDB directly on Parquet. Convert raw CSV to Parquet once.

```
kyc-aml-data-integrity-review/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .claude/settings.json        # deny Read(./sealed/**)
├── config/                       # policy.yaml, capacity.yaml, rules.yaml
├── data/raw/                     # IBM files (gitignored) + generated CSVs
├── data/processed/               # parquet, sampled tables, customer_labels
├── sealed/                       # answer_key.json — DO NOT READ until Day 10
├── generator/                    # sealed-session generator (Claude-written)
├── notebooks/                    # 01_explore … 09_answer_key_review
├── src/                          # dq_rules.py, standardise.py, transfer_rules.py, card_rules.py, stats_utils.py, capacity.py
├── tests/                        # pytest, known-bad fixtures
├── outputs/                      # issue_log.csv, powerbi/*.csv, charts
├── docs/                         # plans/, data_quality_rules.md, memo.md, sources.md, validation_note.md
└── logs/                         # decision_log.md, assumption_log.md, learning_log.md, error_log.md
```

Commit at the end of every working block with a meaningful message. Large data files are gitignored.

---

## 13. 10-day plan

Version 2 split each day into 3 hours of learning and 4 of building. That is replaced by a single build track with a named concept per day that the analyst must be able to explain by the evening. Learning happens inside the build and is logged in `logs/learning_log.md`.

| Day | Build | Must be able to explain by evening |
|---|---|---|
| 1 | Repo, environment (Python 3.14, verified), brainstorm remaining Section 19 decisions; **sealed generation session**; test the sealed-folder block; download IBM data | What each table and column means; why the answer key is sealed and what the seal does and does not hide |
| 2 | Explore all tables; account-key uniqueness; build `transfer_suspicious` + `suspicious_role`; **out-of-time feasibility check (Module 5)**; sampling + linking; market-mapping decision | Five pandas operations from memory; why the label includes bystanders and what that costs |
| 3 | Module 1: 15+ rules in one engine, pytest fixtures | Three rules and the business reason for each |
| 4 | Module 1: five-rule cross-engine reconciliation, health scores; **Module 1b** standardisation baseline + 100 hand labels; Module 2 issue log | The worst issue end to end; why those five rules were chosen to reconcile |
| 5 | Module 5: transfer rules + 2 card rules; baseline metrics | Why accuracy misleads at a 1-in-1,000 base rate; how overpayment laundering works |
| 6 | Module 5: tuning, out-of-sample evaluation, customer-experience metrics; Module 3 exposure with unknown bounds | Why there is no confidence interval on the exposure number, and what the bound means instead |
| 7 | Module 4: commit the pre-registration **first**, then permutation test, effect sizes, priority score + sensitivity | What a permutation test does, in plain words; what p = 0.03 means and does not mean |
| 8 | Module 6 capacity model; Power BI exports; dashboard | Each scenario's assumptions and which two the answer is most sensitive to |
| 9 | Memo; (optional) Module 8 against the Module 1b baseline | Scale Claude standardisation or not — defend it against the baseline numbers |
| 10 | Open answer key; Module 9; README; full end-to-end rehearsal | End-to-end walkthrough without notes |

**Cut order if behind (expect to use it):** Module 8 → optional card rules beyond the two required → logistic regression → priority-score sensitivity → dashboard page 3 polish → the two required card rules (keep the card data and describe the typologies in the memo).

**Never cut:** Modules 1, 1b, 2, 3; transfer-rule tuning with out-of-sample evaluation (or the stated fallback); the Module 4 pre-registration and permutation test; the answer-key review; the daily explain-back.

---

## 14. Using Superpowers (obra/superpowers plugin)

Install (verify current instructions in the repository README first):
```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

Superpowers is designed for autonomous coding; adapt it to a **learning** project:

| Skill | Use here | Adaptation |
|---|---|---|
| `brainstorming` | Session 1 (Section 19 decisions); start of each module | One question at a time; the analyst decides |
| `writing-plans` | A plan per module in `docs/plans/` | Tasks sized for a learner; each names the concept it teaches |
| `executing-plans` | Default execution mode | Human checkpoint after every task; the analyst types analysis code |
| `subagent-driven-development` | **Only** Claude-owned infrastructure (Section 4) | Never for analysis code the analyst must explain |
| `test-driven-development` | Data-quality rules, monitoring rules, stats utilities | Claude may write failing tests + fixtures; the analyst writes code to pass them |
| `systematic-debugging` | Every bug | Walk the analyst through the four phases; log root cause in `logs/error_log.md` |
| `verification-before-completion` | Before declaring any module or number done | Fresh run from clean state; show actual output |
| `requesting-code-review` / `receiving-code-review` | End of each module | Critical review of correctness, clarity, statistical validity |
| `using-git-worktrees`, `dispatching-parallel-agents` | Generally not needed | Single learner, sequential work |

---

## 15. Honesty and framing rules

- Describe the project as: *"a self-directed project using IBM's public synthetic AML benchmark and a synthetic multi-market customer and card-activity dataset, with a fictional policy scenario inspired by recent regulatory changes in the UK, Australia and Japan."*
- Never imply real compliance experience, access to any card issuer's data, legal accuracy, or real-world findings.
- Never claim the analysis was blind. The honest claim is in Section 8.5.
- Never invent statistics, sources, citations, or regulatory details. If unsure, say so.
- Every published number comes from `outputs/` and is reproducible.
- Report null and negative results honestly. A drawn-as-zero hypothesis that was correctly *not* found is a good result, not a failure.


---

## 16. Defensibility

Every number, rule, statistical test and limitation in this project must be explainable in
detail by the analyst who built it, without notes. The specific review questions used to
rehearse that are kept in `CLAUDE.local.md` and are not committed.

---

## 17. Glossary (spell out on first use in all deliverables)

- **AML** — Anti-Money Laundering · **CTF / CFT** — Counter-Terrorism Financing / Combating the Financing of Terrorism
- **KYC** — Know Your Customer · **KYB** — Know Your Business
- **CDD** — Customer Due Diligence · **EDD** — Enhanced Due Diligence
- **PEP** — Politically Exposed Person · **PSC** — Person with Significant Control (UK)
- **FCR** — Financial Crime Risk · **FATF** — Financial Action Task Force
- **MLR 2017** — UK Money Laundering, Terrorist Financing and Transfer of Funds (Information on the Payer) Regulations 2017
- **ECCTA** — Economic Crime and Corporate Transparency Act 2023 (UK)
- **AUSTRAC** — Australian Transaction Reports and Analysis Centre · **FSA** — Financial Services Agency (Japan)
- **SAR / STR / SMR** — Suspicious Activity / Transaction / Matter Report
- **PMO** — Project Management Office · **TDD** — Test-Driven Development · **CI** — Confidence Interval
- **API** — Application Programming Interface
- **Census** — data covering every unit in the population of interest, so proportions are exact rather than estimated
- **Permutation test** — a test that builds its own null distribution by repeatedly reshuffling the labels, rather than assuming a theoretical distribution

---

## 18. Scope control — out of scope

- Machine-learning detection models beyond one logistic regression.
- Merchant / acquiring-side due diligence (named in memo as next step).
- Sanctions screening against real lists.
- Any real personal or company data.
- More than 3 dashboard pages.
- New modules prompted by scope creep — map them onto existing modules instead.

---

## 19. Open decisions (resolve in the first brainstorming session; record in `logs/decision_log.md`)

Closed in version 3: the inference target and use of confidence intervals (Section 11); the definition of `transfer_suspicious` (Section 8.2); the Module 1 double-implementation scope (Module 1); the home of unstructured-data work (Module 1b); the out-of-time validation approach (Module 5 ladder, resolved by data on Day 2).

Still open:
1. Hidden patterns H1–H8 and their parameter ranges.
2. Periodic cycle lengths and trigger-review deadline (`config/policy.yaml`).
3. Card-layer parameters: payment and refund volumes, typology prevalence ranges, label-incompleteness range.
4. Capacity and customer-impact assumptions with sources (`config/capacity.yaml`).
5. Market mapping: currency-based vs generator-assigned (after Day 2).
6. Which five Module 1 rules get cross-engine reconciliation, and which engine is primary.
7. Whether Module 8 stays in scope (decide on Day 8).
8. Machine setup: RAM and Power BI Desktop availability. (Python resolved on Day 1: 3.14.2, virtual environment built, all packages verified, versions locked.)

---

## 20. Sources (verify before citing; record official links in `docs/sources.md`)

- American Express Form 10-K, fiscal year 2023 — international jurisdictions with significant billed business.
- IBM AML dataset (Kaggle): https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models," arXiv 2306.16424.
- AUSTRAC (Australia): https://www.austrac.gov.au — reform commencement 31 March 2026; ongoing CDD without transition; initial CDD transition to 2029.
- UK MLR 2017: https://www.legislation.gov.uk — beneficial owner definition and verification duties.
- Companies House identity verification (UK): GOV.UK — from 18 November 2025, 12-month transition.
- FATF Japan country page: https://www.fatf-gafi.org/en/countries/detail/Japan.html — 2021 Mutual Evaluation, enhanced follow-up.
- Superpowers: https://github.com/obra/superpowers
