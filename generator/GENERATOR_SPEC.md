# Generator specification — brief for the sealed session

> **This file is public by design.** Reading it tells you what *could* have been planted, never
> what *was*. Every hidden value is drawn at run time from a secret seed that exists only in
> `sealed/answer_key.json`.

**Status: ready to run. Blocked only on the IBM dataset.**

---

## How to run this

The generator must run in a **separate Claude Code session** started only for this purpose
(CLAUDE.md Section 8.5). That session writes `generator/generate.py`, runs it, and ends. It never
becomes a working session, because a session that has seen the drawn values could leak them.

1. Download `HI-Small_Trans.csv` and `HI-Small_Patterns.txt` into `data/raw/`.
2. Start a **new** session in this repository.
3. Give it this instruction, and nothing that hints at what you hope to find:

   > Read `generator/GENERATOR_SPEC.md` and `config/generator_ranges.yaml`. Write
   > `generator/generate.py` to that specification, run it, verify the acceptance checks at the
   > end of the spec, then stop. Do not summarise the drawn parameter values to me.

4. When it finishes, **end that session.** Do not ask it questions about the data.
5. Set `locked: true` in `config/generator_ranges.yaml` and commit.

---

## An ordering conflict in the spec, and its resolution

CLAUDE.md Section 13 places the sealed generation session on Day 1, but sampling the 50,000
accounts on Day 2. Those cannot both be true: the generator must create a customer record per
sampled account, so it needs the sample first.

**Resolution: the generator performs the sampling.** Section 8.3 already states that the 50,000
accounts *are* the Issuer's portfolio by construction and that this is a data-engineering step
rather than statistical sampling from a population of interest. It is construction, not analysis,
so it belongs to the generator.

**The sampling seed is public and fixed** (`sampling_seed: 20260331`) precisely so the analyst can
reproduce the identical sample independently on Day 2 and confirm their `transfer_suspicious`
derivation matches the generator's. Two derivations of the same rule from the same public data
must agree; if they do not, one is wrong and that is worth finding.

Day 2 is unaffected in substance — it becomes verifying account-key uniqueness, deriving
`transfer_suspicious` and `suspicious_role` independently, the out-of-time feasibility check, and
the currency-distribution check. That is the genuinely analytical work.

---

## Two seeds, kept separate

| Seed | Visibility | Drives |
|---|---|---|
| `sampling_seed = 20260331` | **Public**, in `config/generator_ranges.yaml` | Which 50,000 accounts are sampled; all bulk synthetic content (names, addresses, ordinary event timing) |
| `hidden_parameter_seed` | **Secret**, drawn at run time from OS entropy, written only to `sealed/answer_key.json` | Every draw from `generator_ranges.yaml`; which records carry planted defects |

Consequence to state in the README: until Day 10 the generated CSV files *are* the reproducible
artefact. Full regeneration from seed becomes possible on Day 10 when the key opens.

---

## Inputs

- `data/raw/HI-Small_Trans.csv`, `data/raw/HI-Small_Patterns.txt`
- `config/generator_ranges.yaml` — all approved ranges
- `config/policy.yaml` — `as_of_date: 2026-03-31`, cycle lengths, the 25% exclusive threshold

## Sampling

- Target 50,000 accounts, account identity = `(From Bank, Account)` / `(To Bank, Account.1)`.
- **Read `From Bank`, `To Bank` and both account columns as strings (`dtype=str`), never as integers.**
  Bank codes carry leading zeros (`00952`, `0111632`, `000`). Parsed as numbers, distinct codes such as
  `0952` and `00952` would collapse into one, silently merging different banks and corrupting the key.
  The analyst's Day 2 derivation must use the same string keys, or the two will not match.
- The raw header repeats the name `Account` for sender and receiver. pandas renames the second to
  `Account.1`; do not rely on another tool's renaming convention.
  **Verify that pair is unique before relying on it** and fail loudly if not.
- Stratified: oversample laundering-involved accounts so the positive class supports the Module 5
  holdout. Record sampling weights to `data/processed/sampling_weights.csv`.
- Keep **every** transaction where a sampled account is sender or receiver. Counterparties outside
  the sample get no customer record — that is realistic and intended.
- Market split: UK 21,000 / AU 18,000 / JP 11,000. Business share 25% / 15% / 12%.
  **Assign markets in the generator** (see the Day 2 currency check — currency-based mapping is
  predicted to fail, but that prediction is the analyst's to test, so assign here regardless).

## The label the whole project depends on

Derive exactly as CLAUDE.md Section 8.2 states, with no variation:

- `transfer_suspicious = 1` if **any** transaction has `Is Laundering = 1` and the customer's
  `(bank_id, account_id)` is **either** the sending **or** the receiving party.
- `suspicious_role` ∈ {`sender`, `receiver`, `both`, `none`}.

Write both to `data/processed/customer_labels.csv`. These are **not** secret — the analyst derives
them independently on Day 2 and the two must match.

H2 and H6 condition on `transfer_suspicious`.

## Outputs to `data/raw/` (gitignored)

`customers.csv`, `beneficial_owners.csv`, `uk_register_extract.csv`, `customer_changes.csv`,
`card_statements.csv`, `card_activity.csv` — schemas in CLAUDE.md Sections 8.6 and 8.7.

Synthetic identities via `Faker`, locales `en_GB`, `en_AU`, `ja_JP`. No real people, companies or
registration numbers. Registration numbers use a format that is obviously fictional.

## Output to `sealed/answer_key.json`

The secret seed; every drawn parameter value; planted-issue counts per hypothesis and market; the
record ids carrying each planted defect; true card typology labels **including the share
deliberately left unlabelled** (H8); which dimension was chosen as the decoy.

---

## What must not leak

1. **No column in `data/raw/` may encode whether a record was planted.** No `is_planted`, no
   suspicious ordering, no id pattern that correlates with defect status. Planted and clean
   records must be indistinguishable except by the defect itself.
2. **Do not print drawn values to stdout.** The session transcript is readable. Print only
   aggregate row counts and the acceptance-check results.
3. **Do not write drawn values into any file outside `sealed/`** — not into logs, not into a
   summary, not into `generate.py` as a constant.
4. `generate.py` must contain **no hard-coded drawn value.** Every hidden parameter is read from
   `generator_ranges.yaml` and drawn at run time. Someone reading the committed code must learn
   nothing about the outcome.

---

## Acceptance checks the sealed session must run before it ends

**Run every check from inside Python** - in `generate.py` or a companion script. The project's
`.claude/settings.json` denies Claude's Read, Glob and Grep tools on `sealed/**`, and this is deliberate.
The session must therefore verify `answer_key.json` by loading it within Python, **not** by opening it
with a tool, and **must not try to work around the denial.** When checking it, print only PASS/FAIL,
never the values it contains.

Print each as PASS or FAIL. Any FAIL means fix and regenerate.

1. `(bank_id, account_id)` is unique across `customers.csv`; row count is exactly 50,000.
2. Market split matches 21,000 / 18,000 / 11,000; business counts within ±2% of target shares.
3. `card_activity.csv` is **under 2,000,000 rows**; `card_statements.csv` is exactly
   50,000 × 12 = 600,000.
4. `transfer_suspicious` and `suspicious_role` are mutually consistent — every `none` has
   `transfer_suspicious = 0`, every other role has 1.
5. No output file in `data/raw/` contains a column name matching
   `planted|hidden|true_|answer|seed|typology_actual`.
6. `sealed/answer_key.json` exists, parses as JSON, and records the seed plus every drawn value.
7. The decoy dimension has **zero** planted defects in every market.
8. Beneficial-owner data contains at least one owner at **exactly 25.0%** who is unverified — the
   boundary case that must not be flagged (MLR 2017 reg. 5 is *more than* 25%; see
   `docs/sources.md` note S4 and fixture C012 in `tests/conftest.py`).
9. A share of "missing" values are whitespace rather than null, per `whitespace_not_null`, so a
   completeness rule built only on `.isna()` under-reports.
10. Re-running with the same secret seed reproduces byte-identical output.

---

## A note for whoever writes `generate.py`

The point of this data is not realism for its own sake. It is that a competent analyst working
carefully should find **most** of what was planted, miss **some**, and be able to tell which is
which on Day 10. Defects that are trivially visible teach nothing; defects that are impossible to
find teach nothing either. When a choice is open, aim for the middle — findable by someone who
looks properly, missable by someone who does not.
