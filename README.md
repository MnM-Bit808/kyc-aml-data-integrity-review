# KYC Health and AML Monitoring Review

**Status: in progress.** The project scaffold, specification, configuration and test suite are in
place. Analysis is being built module by module; findings will be added here as each module
completes.

## What this is

A self-directed project using IBM's public synthetic anti-money-laundering benchmark and a
synthetic multi-market customer and card-activity dataset, with a fictional policy scenario
inspired by recent regulatory changes in the UK, Australia and Japan.

It does not use real customer data, does not model any real institution's systems, and is not
legal advice. The policy is fictional and deliberately simplified.

## The question

A fictional international card issuer asks: **how exposed are we to recent customer-due-diligence
regulatory changes, what do we fix first, and can the team cope — without degrading the customer
experience?**

That breaks into five questions, each answered by one part of the work: can exposure even be
measured given the state of the data; how large is it; who should be re-verified first; can the
team clear the backlog; and where can monitoring rules free capacity without harming customers.
The full specification is in [`CLAUDE.md`](CLAUDE.md).

## Findings

Not yet available. Every number that appears here will be traceable to a file in `outputs/`, and
null results will be reported as plainly as positive ones.

## How to run

Requires Python 3.12 or later and Power BI Desktop (Windows) for the dashboard.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

To reproduce the exact package versions this project was built with, install from the lock
file instead:

```
pip install -r requirements.lock.txt
```

The IBM dataset is **not** in this repository (it is large and requires a Kaggle login).
Download `HI-Small_Trans.csv` and `HI-Small_Patterns.txt` from
https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
and place them in `data/raw/`.

Run the notebooks in `notebooks/` in numerical order. Tests:

```
pytest
```

## Method decisions worth knowing about

Two choices shape every number in this project and are argued in full in `logs/decision_log.md`:

1. **There are no confidence intervals on the exposure figures.** The 50,000 customers are the
   Issuer's entire portfolio, not a sample of it, so those percentages are exact counts rather
   than estimates. Uncertainty is reported instead as a bound whose width is the share of
   customers whose compliance status cannot be determined from the Issuer's own records.
   Confidence intervals appear in exactly two places: effect sizes in the prioritisation
   analysis, and precision and recall measured on held-out data.

2. **A customer counts as suspicious if they were either party to a flagged transaction.**
   That includes innocent counterparties who merely received a payment, which understates
   measured precision. This mirrors what a bank sees at alert time. The `suspicious_role`
   column measures how much of the positive class this accounts for.

## Limitations

<!-- Transcribed from CLAUDE.md Section 10 so they are not forgotten. Rewrite these in your
     own words before publishing - you have to defend every one of them out loud. -->

1. **Transfers are not cards.** The IBM data simulates bank transfers. It demonstrates
   monitoring method, not card-issuer behaviour. The card layer partly addresses this but is
   self-generated.
2. **Partial circularity.** Relationships in the synthetic layer exist because the generator
   planted them. The statistical test shows whether the method recovers a known truth, not
   facts about real customers.
3. **Separate timelines.** Transfers cover 10 days, card activity covers 12 months. They are
   joined only by customer, and their two suspicion labels are never combined.
4. **The positive class contains bystanders.** See method decision 2 above.
5. **Simplified regulation.** The policy is fictional and inspired by real regimes. It is not
   legal advice and not a legal model.
6. **Issuing only.** Merchant (acquiring-side) due diligence is out of scope and is named in
   the memo as the next thing to build.
7. **Assumption-driven capacity.** Capacity and customer-impact results depend on stated
   assumptions; sensitivity is shown.
8. **Oversampled prevalence.** Laundering prevalence here is inflated by design and is not a
   real-world rate.
9. **Known defect classes.** The hypotheses were written before generation, so the classes of
   defect were known; the sealed answer key hid their magnitude, location, and whether each
   was present at all. This is not a blind analysis and is not described as one.

## Repository layout

See CLAUDE.md Section 12.
