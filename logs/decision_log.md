# Decision log

One row per decision a reader could reasonably question. Record the decision, the reason,
and what would make you reverse it. Date every entry.

---

## 2026-09-20 - Inference target: census, not sample

**Decision.** The 50,000 customers are treated as the Issuer's entire portfolio (a census),
not a sample. Exposure figures are reported as exact counts and percentages with NO
confidence interval. Uncertainty is expressed as bounds whose width is the "unknown" share.

**Reason.** A confidence interval measures variability introduced by observing only part of a
population. Observing all of it leaves no such variability. The alternative (superpopulation
framing) is coherent but would mean reporting uncertainty about the synthetic generator's
random seed, which is not uncertainty about anything in the world.

**Consequence.** Confidence intervals survive in exactly two places: Module 4 effect sizes and
Module 5 held-out precision/recall. Module 4's primary test becomes a permutation test, whose
logic rests on random reassignment rather than on sampling.

**Would reverse if:** the project were reframed so the 50,000 are a sample of a larger notional
portfolio. It is not.

---

## 2026-09-20 - Definition of `transfer_suspicious`

**Decision.** A customer is `transfer_suspicious = 1` if any transaction in the sampled data has
`Is Laundering = 1` and their (bank_id, account_id) is either the sending or receiving party.
`suspicious_role` (sender / receiver / both / none) is stored alongside.

**Reason.** It is the dataset's own benchmark label; it mirrors what a bank actually sees at
alert time (a bank cannot distinguish originator from bystander either); and it keeps the
positive class large enough for the Module 5 holdout.

**Known cost.** Innocent counterparties inherit the flag, diluting the positive class and
understating precision. `suspicious_role` exists to measure that cost rather than assume it.

**Rejected alternatives.** Originator-only (positive class too small); pattern membership from
HI-Small_Patterns.txt (analytically stronger, but the parsing cost did not fit Day 2); any union
with `card_suspicious` (would break the separate-timelines limitation).

---

## 2026-09-20 - Repository location

**Decision.** Repository created under a OneDrive-synced Desktop folder.

**Open risk.** OneDrive will sync roughly a gigabyte of data files and can lock files inside
`.git` mid-operation. Mitigation not yet applied. Revisit before downloading the IBM dataset.

---

<!-- Next entries: Day 1 brainstorm outcomes (H1-H8 ranges, policy values),
     Day 2 market-mapping decision, Day 2 out-of-time feasibility result. -->

---

## 2026-09-20 - Environment: Python 3.14 kept, v3 advice withdrawn

**Decision.** Virtual environment built on Python 3.14.2, the version already installed.
Versions pinned in `requirements.lock.txt`.

**Reason.** CLAUDE.md v3 advised installing Python 3.13 because a package might lack a
pre-built wheel on 3.14. That was a guess, so it was tested instead of assumed: all 13
packages installed and imported cleanly. The guess was wrong and the advice is withdrawn.
Installing a second Python for no measured reason would have cost time and taught nothing.

**Carry-forward.** pandas resolved to 3.0.6, not 2.x. Core operations are unchanged, but
pandas 3 changed the default dtype for string columns. Relevant to Module 1 rules that test
for empty or malformed strings, and to any tutorial written against pandas 2.

**Machine.** 31.1 GB RAM, 12 logical CPUs, 319 GB free on C:. The 5M-row transaction file
fits in memory, so the Section 12 caution about RAM is resolved. DuckDB on Parquet remains
preferred as the better habit, not as a necessity.

---

## 2026-09-20 - Sealed-folder block: partially verified

Tested from a working session with the project directory active.

| Access path | Result |
|---|---|
| `Read` on `sealed/answer_key.json` | REFUSED on the directory rule, before the file's existence was checked. Confirms the real answer key will also be refused. |
| `Grep` on `sealed/` | REFUSED. |
| Bash write into `sealed/` | REFUSED. |
| `Glob` on `sealed/**` | INCONCLUSIVE - returned "No files found", but the folder is genuinely empty, so a block cannot be distinguished from an empty directory. |

**Outstanding.** The Glob path is unverified. Re-test once any file exists in `sealed/`:
a "No files found" result then would prove the block; a filename appearing would prove a leak.
Must be closed before the generator writes the real answer key.

**Note.** `.claude/settings.json` denies Read, Bash cat, Bash type, Glob and Grep against
`sealed/**` - wider than the single `Read` rule specified in CLAUDE.md Section 8.5, because a
directory listing leaks planted-record IDs as effectively as a read does.

---

## 2026-09-20 - Regulatory source verification: two claims changed

Verification pass over the 11 claims in `docs/sources.md`. Seven verified against official
sources, two need rewording, two are not citable. Full detail in `docs/sources.md`.

**Change 1 - Australia (S3).** CLAUDE.md said ongoing CDD applied from 31 March 2026 "with no
transition". The commencement date is confirmed, but the phrase overstates it: pre-commencement
customers carry specific relief from initial CDD, and their ongoing CDD obligations are framed
around monitoring and periodic KYC refresh rather than immediate reverification. Reworded in
Section 6. The point the scenario needs - that ongoing review timeliness bites sooner than
initial identification - survives intact.

**Change 2 - United Kingdom (S5), affects module design.** MLR 2017 reg. 28 provides that a bank
does not discharge its beneficial-ownership duty by relying solely on information delivered to
the registrar. So the comparison between `beneficial_owners.csv` and `uk_register_extract.csv`
is a **consistency check that raises questions, not a verification method**. A mismatch means the
two sources disagree and someone must look - not that the bank's record is wrong. Module 1's
register rules and their business-reason column must be worded accordingly. This is also the
substantive point about what the UK duty actually requires of a bank.

**Not citable.** The FSA end-March 2024 date (S9) and the FATF fifth-round 2028 date (S10) are
supported only by law-firm and vendor commentary; the official pages could not be retrieved
(the FATF assessment calendar returns HTTP 403). Both removed from Section 6. "Japan remains in
enhanced follow-up" is fully supported and sufficient for the scenario.

**Boundary confirmed.** The beneficial-owner threshold is strictly MORE THAN 25% (reg. 5), not
25% or more. `config/policy.yaml` encodes this as `threshold_pct_exclusive`, and
`tests/conftest.py` includes a fixture at exactly 25.0% that must NOT be flagged. A rule written
with `>=` fails that test and would overstate the Issuer's exposure.

---

## 2026-09-20 - Test scaffolding written (Claude), rules unwritten (the analyst)

15 failing tests over 10 stubbed rules covering the record-level errors named in Section 8.8.
Verified red: all 15 fail with NotImplementedError, so the harness, fixtures and imports work
and only the rule bodies are missing. Per Section 4, Claude writes the failing tests and the
known-bad fixtures; the analyst writes the functions.

Two fixtures are traps rather than straightforward bad rows, and are the ones worth reading
before coding: C004 holds a whitespace-only risk rating (not null, so `.isna()` misses it), and
C012 holds a beneficial owner at exactly 25.0% who must not be flagged.

---

## 2026-09-20 - H1-H8 ranges approved; generator spec written

The analyst approved the ranges proposed in `docs/plans/day1_decisions_proposal.md`. They are now
locked in `config/generator_ranges.yaml`. Policy values confirmed in `config/policy.yaml` with
`as_of_date = 2026-03-31`. Capacity values written as PROPOSED, to be confirmed on Day 8
alongside the sensitivity analysis.

**Expected outcome of the draws.** Five of the eight hypotheses can come out null (H2 at a
deliberate 30%, H3 at 20%, and H4, H5, H6 at the bottom of their ranges), so roughly two genuine
nulls are expected. Reporting those correctly is the hardest skill in the project and the best
Day 10 material. H8 is never null - incomplete card labelling is a permanent design feature, not
a hypothesis, so measured card-rule precision is a floor rather than an estimate.

**Added: a decoy.** One randomly chosen data-quality dimension gets no planted defects at all.
Costs nothing to generate. Its value is that a clean result somewhere proves the rules are not
simply flagging everything - "I checked six dimensions and one was genuinely clean" is far more
credible than "everything was broken".

---

## 2026-09-20 - Ordering conflict resolved: the generator does the sampling

**The conflict.** CLAUDE.md Section 13 places the sealed generation session on Day 1 but the
sampling of 50,000 accounts on Day 2. Both cannot hold - the generator must create one customer
record per sampled account, so it needs the sample to exist first.

**Decision.** The generator performs the sampling. Section 8.3 already states the 50,000 accounts
*are* the portfolio by construction and that this is a data-engineering step rather than
statistical sampling from a population of interest. Construction belongs to the generator;
analysis belongs to the analyst.

**Why the sampling seed stays public.** `sampling_seed = 20260331` is committed in
`config/generator_ranges.yaml`. That lets the analyst reproduce the identical sample independently on
Day 2 and check their own `transfer_suspicious` derivation against the generator's. Two derivations
of the same published rule over the same public data must agree; if they disagree, one is wrong,
and finding that is worth more than the check costs.

**Two seeds, deliberately separate.** The public sampling seed drives the sample and all bulk
synthetic content. A secret seed, drawn at run time from operating-system entropy and written
only to `sealed/answer_key.json`, drives every draw from the ranges and the placement of planted
defects. Reading the committed generator code therefore reveals nothing about the outcome.

**Day 2 is unaffected in substance:** account-key uniqueness, independent derivation of
`transfer_suspicious` and `suspicious_role`, the out-of-time feasibility check, and the
currency-distribution check. That is the genuinely analytical part.

---

## 2026-09-21 - Repository moved out of OneDrive

**Decision.** Moved from the OneDrive-synced Desktop folder to `C:\Users\user\Projects\`, outside
the sync root.

**What the measurement showed.** The repository itself is 630 KB, of which `.git` is 347 KB. The
virtual environment was **860 MB** - and OneDrive had been syncing all of it. That is before the
IBM dataset, which adds roughly another gigabyte. A directory-size check against the OneDrive copy
also hung past a two-minute timeout, which is the behaviour that makes synced folders a poor home
for a working repository.

**The virtual environment was NOT moved.** Virtual environments bake absolute paths into their
scripts and console entry points, so a relocated one is broken in ways that surface later as
confusing import and tooling errors. It was rebuilt from `requirements.lock.txt` at the new
location, which is what the lock file exists for - this is the first real test that the project is
reproducible from a clean environment, and it passed.

**Verification before deletion.** Git integrity checked with `fsck` (clean), identical HEAD commit
hash, 4 commits, clean working tree, all 32 tracked files present. Environment rebuilt and the
test suite re-run at the new location before the OneDrive copy was removed.

**Backup now comes from git, not from file sync**, which is the better arrangement anyway - a
commit history is version control, whereas file sync only ever holds the latest state. Consider
pushing to GitHub: it is real off-machine backup, and a public repository is itself part of the
project when it is shared.

---

## 2026-09-21 - IBM dataset acquired and verified

Downloaded from Kaggle by the analyst and moved into `data/raw/` (gitignored, not redistributed).
Checked against the figures IBM publishes on the dataset page before anything is built on it.

| Check | Published | Downloaded file |
|---|---|---|
| `HI-Small_Trans.csv` size | 475.66 MB | 475,664,283 bytes |
| `HI-Small_Patterns.txt` size | 323.84 kB | 323,844 bytes |
| Columns | 11 | 11 |
| Transactions | ~5M | 5,078,345 |
| Laundering transactions | ~5.1K | 5,177 |
| Laundering rate | 1 per 981 | 1 per 981 (5,078,345 / 5,177) |
| Pattern blocks | - | 370 BEGIN, 370 END, file ends on a closing line |

Line endings are CRLF; pandas and DuckDB both handle this.

**Near-miss worth recording.** The first file selected on Kaggle was `HI-Large_Trans.csv` (17.05 GB),
because the Data Explorer lists files alphabetically, so every Large file precedes the Small ones and
the names differ by one word. Caught by comparing the displayed size against the expected 475.66 MB.
The on-screen preview of the patterns file is also truncated, so copy-pasting from the page would have
produced a silently incomplete file; it was downloaded whole instead. Both are the same lesson: verify a
file against an independent expectation (size, row count, published statistic) before trusting it.

**Two Day 2 carry-forwards.**

1. The raw header names two columns `Account` (sender and receiver). pandas renames the second to
   `Account.1` on load; DuckDB may name it differently. Five Module 1 rules must reconcile exactly across
   the two engines, so confirm each engine's column name before joining on it.
2. The dataset author notes that transactions exist **after** the stated 1-10 September 2022 range and
   that all of them are laundering. Not yet measured. Added to the Module 5 feasibility check in
   CLAUDE.md as a fourth measurement - if those rows fall in the evaluation window they inflate every
   rule's apparent performance.

**Licence:** Community Data License Agreement - Sharing 1.0. Recorded in `docs/sources.md`.
