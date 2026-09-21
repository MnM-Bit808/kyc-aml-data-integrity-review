# Day 1 — proposal for the eight open decisions (Section 19)

Written by Claude Code, 2026-09-20, as recommendations for the analyst to approve or amend.
**Nothing here is decided.** Each item has a recommendation and the reasoning behind it.
Approve, amend or reject each one, then the values move into `config/` and
`logs/decision_log.md` and the generator session can run.

**Read item 1 most carefully.** Once the generator runs with these ranges, changing them means
regenerating the data and discarding any analysis built on it.

---

## Item 8 — Machine setup (RESOLVED, no decision needed)

Python 3.14.2, virtual environment built, all 13 packages verified, versions locked.
31.1 GB RAM, 12 logical CPUs, 319 GB free. The 5M-row file fits in memory comfortably.
Power BI Desktop availability is still unconfirmed — check before Day 8.

---

## Item 1 — Hidden patterns H1–H8 and their ranges

### The design principle these ranges serve

Each range must satisfy three things at once. It has to be **wide enough that you genuinely
cannot guess the drawn value**. It has to **include a null for most hypotheses**, so that
correctly reporting "no effect" is a possible and honest outcome. And it has to span from
*obvious* to *subtle*, so that some findings are easy, some are missable, and Day 10 tells you
something.

With eight hypotheses drawn independently at roughly a 25% null rate each, expect about two
genuine nulls. Reporting those correctly is the hardest skill in the project and the best
answer you will have to "what did the answer key show you missed?"

### One thing that changes because of the census framing

**H1 is not a hypothesis test.** Under the census decision, "which market is worst on
completeness" is answered by looking — the counts are exact, so any difference is a real
difference in the portfolio. There is nothing to test. The skill H1 exercises is
*judgement*: recognising when a gap of 0.3 percentage points is too small to act on even
though it is exactly real. Do not run a significance test on H1; say plainly that it is a
census ranking and that small gaps are not worth a remediation issue.

### Proposed ranges

| ID | Parameter | Proposed range | Null possible? |
|---|---|---|---|
| H1 | Base defect rate per dimension | uniform [0.05, 0.15] | — |
| H1 | Penalty multiplier for the worst market, drawn per dimension independently | uniform [1.0, 2.5] | Yes, at 1.0 |
| H2 | Odds ratio, data gaps vs `transfer_suspicious` | 30% chance of exactly 1.0; otherwise uniform [1.2, 2.2] | **Yes, 30%** |
| H3 | Default-value trap present at all | 80% chance present | **Yes, 20%** |
| H3 | Share of the chosen market's records auto-filled | uniform [0.25, 0.70] | — |
| H4 | Extra staleness probability per year of tenure (Japan) | uniform [0.0, 0.06] | **Yes, near 0** |
| H5 | Number of duplicate business clusters (UK) | uniform integer [0, 120] | **Yes, at 0** |
| H5 | Cluster size | 2 to 4 | — |
| H6 | Share of `transfer_suspicious` customers forced to risk_rating = Low | uniform [0.0, 0.45] | **Yes, near 0** |
| H7 | Baseline trigger-neglect rate, all markets | uniform [0.05, 0.20] | — |
| H7 | Concentration multiplier for one randomly chosen market | uniform [1.0, 3.0] | Yes, at 1.0 |
| H8 | Share of truly suspicious card accounts left unlabelled | uniform [0.20, 0.60] | **No — by design** |

### Why each range is set where it is

**H2 at [1.2, 2.2] plus a 30% null.** This is the headline test, so it carries the highest null
probability. The lower bound matters: with roughly 50,000 customers and a suspicious class in
the low thousands, an odds ratio of 1.2 is detectable but not obvious, while 2.2 is
unmistakable. Anything below about 1.15 would be indistinguishable from the null in practice,
which would make a "non-null" draw functionally identical to a null and muddy the Day 10
comparison. Keeping the non-null range clearly above that line means a null is a null and an
effect is an effect.

**H3 at [0.25, 0.70].** A default-value trap is only interesting if completeness looks *good*
while validity is poor. Below about 25% the spike in one value is easy to dismiss as natural;
above 70% it is so blatant that finding it proves nothing. The real test is whether you check
value *distributions* rather than only null counts — miss that and you miss H3 entirely
regardless of the drawn value. This is the single most likely miss in the project.

**H4 at [0.0, 0.06] per year.** Japan has 11,000 customers with tenure spanning roughly a
decade, so a slope of 0.06 produces around a 60-point spread between newest and oldest — very
visible. A slope of 0.005 produces about 5 points, which is subtle but real. Including the
bottom of the range means "no relationship with tenure" is a live outcome.

**H5 at [0, 120] clusters.** UK business customers number roughly 5,250, so 120 clusters of
2–4 records is about 5–9% of them — enough to matter, not so much that the portfolio looks
absurd. Zero is included because a bank with clean entity resolution is a realistic state, and
reporting "I looked for duplicates and found none" is a legitimate finding.

**H6 at [0.0, 0.45].** Above roughly half, the misclassification would be so systematic that
it stops resembling a control failure and starts resembling a broken pipeline.

**H8 never zero.** The spec treats incomplete labelling as a permanent feature of the card
layer, not a hypothesis — it exists so that measured card-rule precision is understated and you
have to say so. The range only controls how badly understated.

### Recommended addition: one decoy

Consider planting **one dimension where nothing is wrong at all** — a field with no missingness,
no defaults, no staleness. It costs nothing to generate. Its value is that a clean result
somewhere proves your rules are not simply flagging everything, and "I checked six dimensions
and one was genuinely clean" is a much more credible sentence than "everything was broken".

---

## Item 2 — Policy values

**Recommendation: confirm the illustrative values already in `config/policy.yaml` unchanged.**
High = 365 days, Medium = 1095, Low = 1825, trigger deadline = 30 days. They are defensible,
they are already labelled as a fictional policy, and spending brainstorm time tuning invented
numbers buys nothing.

**One value does need deciding: `as_of_date`.**

**Recommendation: 2026-03-31**, with the card layer covering the twelve months ending that day.

The reason is that it makes the scenario internally coherent with a fact we verified today.
31 March 2026 is the date Australia's new ongoing customer due diligence obligations commenced.
Setting the portfolio's "today" to that date means the leadership question — *how exposed are
we?* — is being asked on the exact day the obligation bites. That is a far better story than an
arbitrary date, and it costs nothing.

Everything overdue-related keys off this one value. Set it once and never let it drift; a
moving as-of date is the most common way this kind of analysis becomes irreproducible.

---

## Item 3 — Card-layer parameters

Volume, sized to stay well under the 2M-row ceiling in Section 8.7:

| Event type | Proposed rate | Approx. rows |
|---|---|---|
| `payment` | ~1.2 per customer-month | ~720,000 |
| `merchant_refund` | ~0.15 per customer-month | ~90,000 |
| `cash_advance` | ~0.08 per customer-month | ~48,000 |
| `refund_request` | ~0.02 per customer-month | ~12,000 |
| **Total** | | **~870,000** |

Plus 600,000 statement rows (50,000 customers × 12 months). Comfortably inside budget, and the
margin matters because the planted typologies add events on top.

Typology prevalence — each drawn independently, each able to come out at zero:

| Typology | Proposed range (share of customers) |
|---|---|
| Overpayment and refund cycling | uniform [0.000, 0.020] |
| Third-party funding | uniform [0.000, 0.020] |
| Refunds without matching purchases | uniform [0.000, 0.012] |
| Cash-advance velocity | uniform [0.000, 0.012] |

At the top of the range that is about 1,000 customers per typology, which is plenty to measure
precision and recall against. At zero, the honest finding is that the rule fired and caught
nothing real — which is exactly the sort of result that gets under-reported and shouldn't be.

**Note the interaction with H8.** The two required card rules are graded against
`card_suspicious`, which is deliberately incomplete. If a typology is drawn near zero *and* H8 is
drawn near 0.6, that rule will look terrible on paper. That is not a bug — it is the scenario
teaching you why precision measured against incomplete labels is a floor, not an estimate.

---

## Item 4 — Capacity and customer-impact assumptions

**These are the numbers you must be most careful about.** There is no public benchmark for
analyst review throughput. Anything you find will be vendor marketing.

The honest approach is not to refuse to pick numbers — a model needs inputs to run — but to
label every one as a chosen assumption, cite nothing, and **lead the memo with the sensitivity
rather than the point estimate.** "Time to clear the backlog is between 9 and 26 months
depending on two assumptions I could not source" is a stronger and more senior sentence than a
false precision like "14.3 months".

Proposed starting values, every one an assumption with no benchmark:

| Input | Proposed | Note |
|---|---|---|
| Analyst headcount | 12 | |
| Working days per month | 20 | |
| Productive hours per day | 6 | Not 8 — meetings, training, admin |
| Periodic review, High risk | 90 min | |
| Periodic review, Medium risk | 45 min | |
| Periodic review, Low risk | 20 min | |
| Trigger review | 60 min | |
| Alert triage | 25 min | |
| Customer contacts per alert | 0.6 | Not every alert reaches the customer |
| Temporary block rate per alert | 0.08 | |
| Documents requested per review | 0.5 | |

**Sweep these two in the sensitivity analysis:** alert triage minutes and the block rate per
alert. Triage minutes because alert volume is large, so the number multiplies hardest. Block
rate because it drives the entire customer-experience argument and is the number you have least
basis for. If the recommendation flips when either moves within a plausible range, that is the
finding — say so.

---

## Item 5 — Market mapping (cannot be decided until Day 2)

**Prediction, to be tested rather than assumed:** currency-based mapping will not work.

The target split is 21,000 / 18,000 / 11,000 UK / Australia / Japan. For currency to produce
that, the IBM file's British Pound, Australian Dollar and Yen transactions would have to fall in
roughly 42/36/22 proportion among sampled accounts, which there is no reason to expect. Forcing
it would mean discarding accounts to hit quota and distorting the sample.

**Recommended default: generator-assigned markets.** Run the Day 2 currency check anyway — it
takes ten minutes, it is the kind of check that should be recorded, and writing down "I tested
the cheaper option and it did not work" is worth more than silently choosing the harder path.
Record the actual distribution in `logs/decision_log.md` either way.

---

## Item 6 — Primary engine and the five reconciled rules

**Recommendation: pandas primary, DuckDB SQL for the five reconciled rules.**

pandas is the primary engine because the fifteen implementations are fifteen repetitions of the
skill the project is building, and repetition is how that skill becomes fluent. The second
implementation of five rules goes in SQL, which is quick to write, so the reconciliation costs
little and still produces the cross-engine validation story.

Proposed five, one per dimension plus the hardest:

| Rule | Dimension | Why this one |
|---|---|---|
| Missing risk rating | Completeness | The simplest possible case — if the two engines disagree here, something is wrong with the harness, not the rule |
| Beneficial ownership total exceeds 100% | Validity | Requires grouping and aggregation, where pandas and SQL diverge most easily on how they treat missing values |
| Periodic review overdue against the risk-based cycle | Timeliness | Date arithmetic plus a per-row lookup of the cycle length; the most common place to get an off-by-one |
| Beneficial owners inconsistent with the register extract | Consistency | A join across two tables with imperfect keys |
| Suspicious uniformity in a field (the H3 detector) | Validity | **The hardest.** Not a per-record test at all — it looks at a distribution and asks whether one value appears implausibly often. Getting the same answer from both engines is a genuine check |

That last one deserves attention: it is the rule most likely to be the difference between finding
H3 and missing it, and it is the one a reviewer will find most interesting, because
"completeness looked fine and the data was still wrong" is the whole point of data integrity.

---

## Item 7 — Does Module 8 survive?

**Recommendation: plan for no, decide on Day 8.**

Module 1b already covers the unstructured-data requirement with no external dependency, which
was the reason Module 8 mattered in version 2. What Module 8 adds now is a model-risk assessment
for the GenAI Model Risk role — genuinely valuable, but secondary to the main target, and it
sits on Day 9 where schedule slippage accumulates.

If you are on schedule on Day 8, do it — the comparison against a working baseline is a much
stronger artefact than most people's "I used AI" claims. If you are behind, cut it without
regret and say in the memo that a measured baseline existed and an LLM comparison was scoped but
not run. That is a more credible position than a rushed evaluation on 100 records.

---

## What I need from you before the generator can run

1. Approve or amend the H1–H8 ranges above. **This is the blocking item.**
2. Confirm `as_of_date = 2026-03-31` and the policy values.
3. Approve the card-layer volumes and prevalence ranges.
4. **Download the IBM dataset** — `HI-Small_Trans.csv` and `HI-Small_Patterns.txt` into
   `data/raw/`. Needs your Kaggle login; I cannot do this and should not have your credentials.
5. Decide the OneDrive question before that download, not after.

Items 1–3 are ten minutes of reading. Item 4 is the real gate.
