# Project brief — Governed ELT pipeline on Microsoft Fabric

**You're building it. This is the spec, not the solution.** It mirrors the full
scope of the webinar *"Unify and distribute data with Copy job + dbt job in
Fabric Data Factory"* so that when you're done you'll have touched every piece
the presenters demoed — and have a real story to tell.

The data is in `data/` (see `DATA_DICTIONARY.md`). The struggle is the feature.
Get stuck, search the docs, read errors, fix, repeat. That's the portfolio.

---

## The scenario

You're the data engineer at a retail bank. Critical data is scattered across an
operational SQL database (customers, accounts), a cards system (transactions),
and a merchant API feed — and it lands messy. Leadership wants **one trusted
place** for analytics and a **fraud-review** view, refreshed daily, all on a
single Microsoft Fabric capacity.

Deliver a governed **ELT** pipeline: ingest with **Copy job**, transform with a
**dbt job** through a **medallion (bronze → silver → gold)** architecture, test
everything, orchestrate it end-to-end, and serve it to Power BI.

---

## Target architecture (your north star)

```
Sources ──Copy job──▶ Bronze (OneLake)──dbt──▶ Silver ──dbt──▶ Gold ──▶ Power BI
 SQL / files / API     raw + audit cols       cleansed       dims/facts/marts
                       full + incremental                    + tests + lineage
        Orchestrated by one Fabric Data pipeline · single capacity
```

---

## Milestones

Each milestone has a **Goal**, **Build**, **Done when…** (your acceptance
criteria), and **Hints**. No code is given on purpose.

### 0 — Setup & version control
- **Goal:** a clean, reproducible workspace under source control.
- **Build:** a Fabric workspace (or local dbt project if you want to prototype first); a Git repo connected to the workspace or to GitHub/Azure DevOps.
- **Done when:** you can commit, your project skeleton is in Git, and a teammate could clone it.
- **Hints:** decide early whether silver/gold live in a Lakehouse, a Warehouse, or a mix — the webinar shows both and dbt has adapters for each.

### 1 — Ingest the full load → Bronze
- **Goal:** land `data/full_load/` into a bronze/raw zone exactly as received.
- **Build:** a Copy job per source (or one job, multiple tables) writing to a Lakehouse/Warehouse. Keep raw fidelity — don't clean here.
- **Done when:** four bronze tables exist with the right row counts, and each row carries **audit columns** (load timestamp + source identifier).
- **Hints:** in Fabric, look at Copy job's destination mapping and the new **audit columns** feature. Prefer text/string types in bronze so a bad value never fails ingestion.

### 2 — Incremental load (watermark / CDC)
- **Goal:** apply `data/incremental/` without reloading everything.
- **Build:** switch the Copy job to **incremental copy** using `last_updated_at` as the watermark; choose **merge/upsert** on the key so updated rows replace, new rows insert.
- **Done when:** re-running brings in ~8,000 new transactions and correctly **updates** the ~500 changed ones (their status flips) — with no duplicate primary keys.
- **Hints:** this is where most people struggle. Think carefully about the merge key and what "latest" means (`max(last_updated_at)`). Verify by querying a known updated `transaction_id` before and after.

### 3 — Silver: cleanse & conform (dbt)
- **Goal:** turn raw bronze into clean, typed, deduplicated staging models.
- **Build:** one `stg_` model per source. Trim whitespace, standardise casing, cast types, **de-duplicate customers** (raw has dup PKs), and normalise the messy `country` values to a canonical name.
- **Done when:** `stg_customers` has exactly one row per `customer_id`; statuses/currencies/types are standardised; types are correct (dates are dates, amounts are numbers).
- **Hints:** `ref()` / `source()`, `row_number()` for dedupe, and a reusable **Jinja macro** for the country logic so you don't repeat it in every model.

### 4 — Seeds & enrichment
- **Goal:** bring in the static reference data and use it.
- **Build:** load the three `seeds/` files as **dbt seeds**; convert every transaction amount to **USD** via the currency rates; attach **region** to customers/merchants; attach **category_group / is_high_risk** to merchants.
- **Done when:** a transaction in NGN and one in USD are comparable in a single `amount_usd` column, and merchants carry their category group.
- **Hints:** `dbt seed`; join staging models to the seeds in silver or in the gold dimensions.

### 5 — Gold: dimensional model
- **Goal:** a star schema an analyst can actually query.
- **Build:** conformed dimensions (`dim_customers`, `dim_accounts`, `dim_merchants`) with **surrogate keys**, and a `fct_transactions` fact at one-row-per-transaction joined to those dimensions. Decide how to handle the **orphan merchant** (`MER9999`) so you don't silently drop transactions.
- **Done when:** every fact row joins cleanly to all three dimensions; row count matches the source; no orphans lost.
- **Hints:** surrogate keys via a hash; an "Unknown" dimension member is a common pattern for orphans. Tag these models `gold`.

### 6 — Analytics marts
- **Goal:** the outputs leadership asked for.
- **Build:** `customer_360` (one row per customer: lifetime txns, spend, distinct merchants, last activity) and `flagged_transactions` (a fraud-review queue: high value, off-hours, unknown merchant, declined/reversed → an explainable risk score). Optionally a monthly account aggregate for BI.
- **Done when:** the fraud queue returns a sensible subset (not 0, not everything) with a defensible scoring rule you can explain in one sentence.
- **Hints:** derive flags in the fact, aggregate in the marts. Keep the scoring simple and explainable.

### 7 — Testing & data quality
- **Goal:** make the pipeline fail loudly instead of feeding a broken dashboard.
- **Build:** dbt tests — `not_null` and `unique` on keys, `relationships` for every FK, `accepted_values` for statuses/types, plus at least **two singular tests** (e.g. no future-dated transactions; amounts strictly positive). Add a **source freshness** check on the watermark.
- **Done when:** `dbt test` (or `dbt build`) runs green, and you can intentionally break a rule and watch the right test fail.
- **Hints:** this is your headline metric for the post — "N models, M tests, 0 failures."

### 8 — Documentation & lineage
- **Goal:** anyone can understand the pipeline without reading every model.
- **Build:** column/model descriptions in YAML; generate docs and the lineage graph.
- **Done when:** `dbt docs` shows the full bronze→silver→gold lineage and your key columns are described.

### 9 — Orchestration
- **Goal:** one pipeline runs the whole thing in order.
- **Build:** a Fabric **Data pipeline**: Copy job(s) → dbt job activity for silver (`--select tag:silver`) → dbt job activity for gold (`--select tag:gold`) → **quality gate** → refresh the Power BI semantic model only if tests passed. Parameterise where it makes sense.
- **Done when:** a single trigger produces refreshed gold tables, and a failed test stops the semantic-model refresh.
- **Hints:** dbt job is a first-class pipeline activity; tag **selectors** let you run layers independently.

### 10 — Serve
- **Goal:** close the loop to reporting.
- **Build:** a small Power BI report on the gold marts — e.g. spend by region/month, top customers, and a fraud-review page driven by `flagged_transactions`.
- **Done when:** the report reads from gold and refreshes after a pipeline run.

---

## Definition of done (the whole project)
- [ ] Bronze loaded by Copy job with audit columns
- [ ] Incremental/watermark load proven (new + updated rows handled, no dups)
- [ ] Silver cleansing + customer dedupe
- [ ] Seeds loaded and used (USD conversion, region, category group)
- [ ] Gold star schema with surrogate keys; orphans handled
- [ ] `customer_360` + `flagged_transactions` marts
- [ ] Full test suite green; you can demo a deliberate failure
- [ ] Docs + lineage generated
- [ ] One pipeline orchestrates copy → dbt (silver→gold) → quality gate → refresh
- [ ] Power BI report on gold

## Skills you'll be able to claim afterwards
Data ingestion (full + incremental / CDC / watermark) · medallion / ELT design ·
dimensional modelling (star schema, surrogate keys, SCD thinking) · dbt (models,
sources, seeds, Jinja macros, tags/selectors, schema + singular tests, docs &
lineage) · data-quality engineering · SQL · Microsoft Fabric (Copy job, dbt job,
pipeline orchestration, Power BI).

## Suggested order & pace
Milestones are roughly sequential. A realistic pace is 1–2 evenings each; don't
try to do it in one sitting. Commit after every milestone — your Git history is
itself proof of the work.

## Stretch goals (if you want to stand out)
- Implement an **SCD Type 2** history on a dimension (the webinar mentions CDC type 2 / full history).
- Add CI: run `dbt build` on every pull request.
- Distribute a gold table to a **second destination** (e.g. another cloud / Snowflake) with a Copy job, like the webinar's multicloud demo.
- Capture **screenshots at each milestone** — they make the LinkedIn post far stronger.

---

## When you're done
Bring me: your repo (or a description of what you built), your green test
summary, and a few screenshots (Fabric Copy job, dbt lineage, the Power BI
page). I'll help you turn the *real* story — including what broke and how you
fixed it — into a LinkedIn post that recruiters actually stop on.

Good luck. Embrace the errors.
