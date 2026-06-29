# WORK ORDER — Finance Data Migration to Microsoft Fabric

**From:** Office of the General Manager, Data & Analytics
**To:** Data / Analytics Engineer (you)
**Project:** `DATA_ENGINEER_TRAINING` · Lakehouse `Finance_Bronze`
**Status:** Active — Stage 1 (landing) in progress

---

## 1. Why you're doing this (business context)

Our finance data is scattered across three systems — the **core banking database**
(customers, accounts), the **cards platform** (transactions), and a **merchant
feed** — and it lands inconsistent and untrusted. Leadership cannot get a reliable
view of customer activity, and Risk has no usable fraud-review queue.

Your job: stand up **one governed source of truth** in Microsoft Fabric, refreshed
reliably, that produces (a) clean conformed finance data, (b) a **customer-360**
view, and (c) a **fraud-review** queue. You own this end to end.

## 2. Scope

Migrate all source data into Fabric and transform it through a **medallion
architecture (bronze → silver → gold)** using **dbt**, with automated
**data-quality testing**, **lineage**, orchestration, and a **Power BI** serving
layer. Treat the data problems as real — fixing them is the job, not a footnote.

## 3. The data reality — issues you MUST handle

These are deliberately present in the source data. Do not ignore or silently drop
them; each must be handled and, where possible, proven with a test.

| # | Data issue | Where it shows up | Required handling | Fixed in layer |
|---|---|---|---|---|
| 1 | **Duplicate primary keys** (~15) | customers | De-duplicate to one row per `customer_id` (keep latest) | Silver |
| 2 | **Inconsistent country text** (`USA`,`usa`,`" United States "`) | customers, merchants | Normalise to a canonical country (+ join region) | Silver |
| 3 | **Mixed casing / padded whitespace** | most text columns | Trim + standardise case | Silver |
| 4 | **Blank / missing KYC status** | customers | Default empty → `UNKNOWN` | Silver |
| 5 | **Wrong data types** (dates/amounts as text) | all | Cast to date / timestamp / numeric | Silver |
| 6 | **Multi-currency amounts** (USD/EUR/GBP/NGN…) | transactions | Convert to a common `amount_usd` via the currency seed | Silver/Gold |
| 7 | **Orphan foreign key** (`MER9999` not in merchants) | transactions | Route to an "Unknown" merchant member — do **not** drop the row | Gold |
| 8 | **Status/type variants** (`posted`/`POSTED`…) | accounts, transactions | Standardise to an accepted set | Silver |
| 9 | **Late-arriving / changed rows** (day-2 delta) | all | Incremental load + merge on key + watermark | Bronze→Silver |
| 10 | **Suspicious transactions** (large / off-hours / declined) | transactions | Derive risk flags + score for the fraud queue | Gold |

## 4. Layer-by-layer requirements (the build)

### 4.1 Bronze — landing (`Finance_Bronze`)
- Land each source **as-is**. No cleansing here.
- Four tables: `bronze_customers`, `bronze_accounts`, `bronze_transactions`,
  `bronze_merchants`.
- Each row carries **audit columns** (load timestamp + source).
- Reference/seed files (`currency_rates`, `country_reference`,
  `merchant_categories`) are lookup data — load them as dbt **seeds** (or small
  lookup tables), not as core bronze sources.

### 4.2 Silver — cleanse & conform (dbt `stg_` models)
Per-table rules:
- **stg_customers** — de-dupe (issue 1); trim; lower-case email; normalise country
  (2); blank KYC → `UNKNOWN` (4); cast `signup_date`.
- **stg_accounts** — upper-case `account_type`/`status`/`currency` (3,8); cast
  `opened_date`, `credit_limit`.
- **stg_transactions** — cast `txn_timestamp`/`amount`; derive `txn_date`;
  standardise `txn_type`/`status` (8).
- **stg_merchants** — trim; normalise country (2); attach `category_group` /
  `is_high_risk` from the seed.
- **Enrichment** — convert every amount to `amount_usd` via `currency_rates` (6);
  attach `region` from `country_reference`.
- Use a reusable **Jinja macro** for country normalisation (write once, reuse).

### 4.3 Gold — model (dbt marts)
- Conformed dimensions with **surrogate keys**: `dim_customers`, `dim_accounts`,
  `dim_merchants` (include a synthetic **Unknown** merchant member — issue 7).
- `fct_transactions` — one row per transaction, conformed to dims, with
  `amount_usd` and risk flags (`is_high_value`, `is_offhours`, …).
- Marts: **`customer_360`** (lifetime activity per customer) and
  **`flagged_transactions`** (fraud-review queue with an explainable 0–4 risk
  score — issue 10). Optional: `fct_account_monthly`.

### 4.4 Quality gates (non-negotiable)
- dbt tests: `not_null` + `unique` on keys, `relationships` on every FK,
  `accepted_values` on statuses/types, **≥2 singular tests** (e.g. no future-dated
  txns; amounts > 0), and a **source freshness** check on the watermark.
- The Power BI semantic model refreshes **only if tests pass**.

## 5. Deliverables
1. Bronze tables landed in `Finance_Bronze` (with audit columns).
2. A dbt project (silver + gold) under Git, building cleanly.
3. **Green** test suite — report me the "N models, M tests, 0 failures" number.
4. dbt **docs + lineage** generated.
5. One Fabric **pipeline** orchestrating: land → dbt(silver) → dbt(gold) → quality
   gate → refresh semantic model.
6. A **Power BI** report on the gold marts.
7. Screenshots at each milestone + a clean Git history.

## 6. Definition of done
- [ ] All 10 data issues above are handled and (where applicable) covered by a test
- [ ] bronze → silver → gold builds end to end, tests green
- [ ] customer_360 + flagged_transactions produce sensible results
- [ ] one pipeline runs the whole thing; failed tests block the refresh
- [ ] Power BI report reads from gold
- [ ] repo + screenshots ready

## 7. Milestones (report progress at each)
Stage 1 Land → 2 Incremental → 3 Silver → 4 Seeds/enrich → 5 Gold → 6 Marts →
7 Test → 8 Docs/lineage → 9 Orchestrate → 10 Serve. (See `ROADMAP.md`.)

## 8. How I want to be updated
At each milestone: a screenshot (Fabric/Power BI), your test summary, and one line
on what broke and how you fixed it. The "what broke" is the part I care about — it's
what makes you an engineer, and it's what we'll put in the write-up.

*— GM, Data & Analytics*
