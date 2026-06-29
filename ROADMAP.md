# Roadmap — Governed ELT pipeline on Microsoft Fabric

Your at-a-glance map. Each stage builds on the last. `PROJECT_BRIEF.md` has the
detailed acceptance criteria and hints for every stage; this file is the
"where am I and what's next" view. Commit to Git after each stage.

```
        YOU ARE HERE
            │
  Stage 0 ──┴── Stage 1 ──── Stage 2 ──── Stage 3 ──── Stage 4 ──── Stage 5
  Setup        Ingest        Incremental   Silver       Seeds &      Gold
               (Copy job)    load          (cleanse)    enrich       (star schema)
                                                                        │
  Stage 9 ──── Stage 8 ──── Stage 7 ──── Stage 6 ────────────────────────┘
  Orchestrate  Docs &       Test &        Marts
  + Serve(10)  lineage      data quality  (customer_360, fraud)
```

---

## Stage 0 — Setup *(start here)*
Get the workspace and tooling ready and under version control.
- Fabric workspace created; this folder is a Git repo (and/or connected to Fabric Git).
- Decide your local-vs-Fabric plan: many people prototype the dbt models locally first (fast feedback), then point the same project at Fabric. Either is fine.
- **Next:** look at the data in `data/` (see `data/SOURCES.md`).

## Stage 1 — Ingest to Bronze (Copy job)
Land all three sources *as-is* into a raw/bronze zone with audit columns.
- You have 3 different source types on purpose — a database, file extracts, and an API feed. Each needs a different Copy job source connector.
- **Output:** `bronze.customers`, `bronze.accounts`, `bronze.transactions`, `bronze.merchants` — raw, plus load-timestamp + source columns.

## Stage 2 — Incremental load
Re-ingest only what changed, using the `last_updated_at` watermark + merge.
- Use the `*_changes.db` / `*_delta.csv` files as the "day 2" batch.
- **Output:** new rows inserted, changed rows updated, zero duplicate keys.

## Stage 3 — Silver (cleanse & conform)
First dbt models: trim/standardise, cast types, **de-duplicate customers**, normalise countries.
- **Output:** one clean `stg_` model per source; `stg_customers` is unique per customer.

## Stage 4 — Seeds & enrichment
Load `reference-data/` as dbt seeds and use them.
- **Output:** amounts converted to USD; region + merchant category group attached.

## Stage 5 — Gold (dimensional model)
Star schema: `dim_customers`, `dim_accounts`, `dim_merchants`, `fct_transactions` with surrogate keys.
- **Output:** every fact row joins to all dimensions; orphan merchant handled (not dropped).

## Stage 6 — Analytics marts
The business outputs: `customer_360` and a `flagged_transactions` fraud queue with a risk score.

## Stage 7 — Test & data quality
`not_null`/`unique`/`relationships`/`accepted_values` + 2 singular tests + source freshness.
- **Output:** `dbt build` green — your headline metric for the post.

## Stage 8 — Docs & lineage
Describe models/columns; generate dbt docs + the lineage graph.

## Stage 9 — Orchestrate
One Fabric pipeline: Copy job → dbt (tag:silver) → dbt (tag:gold) → quality gate → refresh semantic model.

## Stage 10 — Serve
Power BI report on the gold marts (spend by region/month, top customers, fraud page).

---

## Definition of done
All ten stages complete, `dbt build` green, one pipeline runs it end-to-end, a
Power BI report reads from gold — and you've kept screenshots + a Git history
along the way. Then come back and we'll write the LinkedIn post from your *real*
experience.

**Right now:** finish Stage 0, then open `data/SOURCES.md` and explore the three sources before you build a single Copy job.
