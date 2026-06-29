# Stage 1 — Land the sources into Fabric (bronze) — **Mac / gateway-free**

**Goal:** get all sources into a raw **bronze** layer in OneLake, as-is, with
audit columns — ready for the dbt job.

**Why this version:** the on-premises data gateway is **Windows-only**, so on a
Mac we skip it. Instead of pulling live from local Postgres/API, we **upload the
source files to OneLake** and use **Copy jobs (Files → tables)** to build bronze.
You still use Fabric Copy jobs and the full medallion flow — you just don't pull
from the live database.

```
Source files (already on disk) ──upload──▶ Lakehouse Files ──Copy job──▶ bronze tables ──▶ dbt job
  operational-db/*.csv                      (OneLake)                     customers · accounts ·
  cards-system/*.csv                                                      transactions · merchants
  merchant-api/merchants.json
```

> Postgres stays your *local* source system (you loaded it earlier, and you can
> still use it for a local dbt prototype). For the **Fabric** path we land its
> CSV extracts — same data, no gateway needed.

This is yours to build in the Fabric portal (all browser-based, Mac-fine).

---

## 0. Create the landing zone
In your Fabric workspace, create a **Lakehouse** (e.g. `lh_bronze`). This holds
both the uploaded files (Files area) and the bronze Delta tables.

## 1. Upload the source files to OneLake (no gateway)
You have these already in `data/`:

| Upload to Lakehouse Files | From |
|---|---|
| `Files/raw/customers/` | `data/sources/operational-db/customers_full.csv` (+ `_delta`) |
| `Files/raw/accounts/`  | `data/sources/operational-db/accounts_full.csv` (+ `_delta`) |
| `Files/raw/transactions/` | `data/sources/cards-system/transactions_full.csv` (+ `_delta`) |
| `Files/raw/merchants/` | `data/sources/merchant-api/merchants.json` |

Three Mac-friendly ways to upload (OneLake File Explorer is Windows-only — use one of these instead):
- **Browser (simplest):** in the Lakehouse, *Get data → Upload files* / drag-and-drop into the Files pane.
- **azcopy** (has a macOS build) to the OneLake ABFS endpoint.
- **Python** (`azure-storage-file-datalake` + `az login`) if you want to script it.

## 2. Build bronze tables with Copy jobs (Files → tables)
For each dataset, create a **Copy job** (or use the Lakehouse "Load to Tables"):
- Source = the file(s) in `Files/raw/...`
- Destination = a new Delta table: `bronze_customers`, `bronze_accounts`,
  `bronze_transactions`, `bronze_merchants`
- Keep columns raw/text on landing — cleansing happens later in silver.
- Turn on **audit columns** so each row records load time + source.
- For the JSON, set the row/collection path to `merchants` so the array flattens
  into rows.

## 3. Incremental (Stage 2, later)
No live DB watermark here, so use the **folder-per-load** pattern: drop the
`*_delta` files into a separate `Files/raw/.../incremental/` folder and have a
later Copy job pick up only that folder, then **merge** on the key. Every row
still has `last_updated_at`, so you can also compute `max(last_updated_at)` in
bronze and filter from there.

---

## Done when…
`lh_bronze` has four tables — customers, accounts, transactions, merchants —
raw, with audit columns, row counts roughly ~2,015 / ~3,951 / 40,000 / 150.

## Where you'll wrestle (the real learning)
- Uploading to OneLake from a Mac (browser vs azcopy).
- Flattening the merchant **JSON array** into table rows.
- Designing the **folder-per-load** incremental pattern (Stage 2).

## Then → the dbt job
Once bronze exists, the dbt job (dbt-fabric adapter) reads these tables as its
`sources` and builds silver → gold (Stage 3+). Ping me to scaffold the dbt
project when you're ready.

---

### If you later want the *live* Postgres → Fabric Copy job
You'd need the source reachable from the cloud (no gateway on Mac): host Postgres
on a free cloud tier (Neon / Supabase / Azure Database for PostgreSQL) and re-run
the loader with that host in `.env`. Then a Copy job's PostgreSQL connector
reaches it directly. Optional — the file path above is enough for the project.
