# Data sources

This project deliberately gives you **three different source systems in three
different formats** — exactly the situation the webinar describes ("your data is
in an operational database, in files, in a SaaS/API feed…"). Part of the
exercise is connecting to each one differently with a Copy job.

Everything is synthetic and safe to share publicly. The raw data is
**deliberately messy** (mixed casing, padded whitespace, empty strings,
duplicate keys, a few orphan foreign keys). Cleaning it is the job.

```
data/
├── sources/
│   ├── operational-db/      ← Source 1: a relational database (SQL Server)
│   │   ├── customers_full.csv  + accounts_full.csv    (full snapshot)
│   │   └── customers_delta.csv + accounts_delta.csv   (day-2 changes)
│   ├── cards-system/        ← Source 2: file extracts from the cards platform
│   │   ├── transactions_full.csv    (initial load, 40,000 rows)
│   │   └── transactions_delta.csv   (day-2 batch, ~8,500 rows)
│   └── merchant-api/        ← Source 3: a JSON API/SaaS feed
│       └── merchants.json           (150 merchants)
└── reference-data/          ← static lookups → load as dbt SEEDS
    ├── currency_rates.csv
    ├── country_reference.csv
    └── merchant_categories.csv
```

---

## Source 1 — Operational database (SQL Server)  ·  `sources/operational-db/`

This is your bank's operational system. The data ships as **CSV extracts** that
you load into **SQL Server** with the provided script — SQL Server then *is* the
source system your Copy job ingests from.

**Load it (one-time setup):**

```powershell
uv pip install -r scripts/requirements.txt
# Edit .env with your connection details (see GETTING_STARTED.md)
python scripts/load_operational_db.py --full          # creates schema bank_core + loads snapshot
python scripts/load_operational_db.py --incremental   # later: applies the day-2 changes (merge)
```

This creates schema `bank_core` with tables **customers** and **accounts**.

- **Maps to in Fabric:** a Copy job with the **SQL Server** connector. Point it at
  `bank_core.customers` / `bank_core.accounts`.
- **Incremental:** the `--incremental` run applies ~120 new customers, ~40 profile
  updates, ~80 new accounts and ~150 account updates — all carrying a fresh
  `last_updated_at`. That's what your Copy job's watermark/CDC step then detects.
- **Why it's loaded "raw":** `customers` keeps its ~15 duplicate `customer_id`s on
  purpose (no unique key) so you have a real dedupe job in Stage 3; `accounts`
  has a primary key on `account_id`.

**customers**: `customer_id` (key — has duplicates in the raw snapshot!),
`first_name`, `last_name`, `email` (padded/mixed case), `country` (messy free
text), `kyc_status` (`VERIFIED`/`PENDING`/`REJECTED`/blank), `signup_date`,
`last_updated_at` (watermark).

**accounts**: `account_id` (key), `customer_id` (FK), `account_type`
(CHECKING/SAVINGS/CREDIT, mixed case), `currency`, `opened_date`, `status`
(ACTIVE/FROZEN/CLOSED), `credit_limit`, `last_updated_at`.

## Source 2 — Cards system file extracts (CSV)  ·  `sources/cards-system/`

The high-volume **transactions**, delivered as CSV file drops — the classic
"files landing in storage" pattern.

- **Maps to in Fabric:** a Copy job from a file source (OneLake Files / ADLS /
  S3 / Blob). Read directly as CSV.
- **Incremental:** `transactions_delta.csv` is the day-2 batch — ~8,000 *new*
  transactions **plus ~500 updates** to existing `transaction_id`s whose status
  changed (e.g. `PENDING`→`POSTED`, `POSTED`→`REVERSED`). Watch the watermark.

**columns**: `transaction_id` (key), `account_id` (FK), `merchant_id` (FK —
~0.3% are the orphan `MER9999`, not present in the merchant feed),
`txn_timestamp`, `amount` (positive; ~2% are large 8k–40k), `currency` (messy),
`txn_type` (PURCHASE/WITHDRAWAL/TRANSFER/REFUND/DEPOSIT), `status`
(POSTED/PENDING/DECLINED/REVERSED), `last_updated_at`.

## Source 3 — Merchant API feed (JSON)  ·  `sources/merchant-api/`

Merchant reference data as a **JSON** document: `{ count, merchants: [ … ] }`.

- **Maps to in Fabric:** a Copy job from a REST/JSON source (or land the file and
  parse it). You'll need to flatten the `merchants` array.
- **columns** (per element): `merchant_id` (key), `merchant_name`, `category`
  (joins to `merchant_categories`), `country` (messy), `last_updated_at`.

---

## Reference data → dbt seeds  ·  `reference-data/`

Small, clean, slow-changing lookups. Load these with `dbt seed`, not a Copy job.

- **currency_rates.csv** — `currency_code, to_usd_rate`. Convert every amount to a
  comparable `amount_usd`.
- **country_reference.csv** — `country_name, iso2, region`. Standardise/enrich the
  messy country fields and add a region for reporting.
- **merchant_categories.csv** — `category, category_group, is_high_risk`. Group
  categories and flag high-risk ones (useful for the fraud mart).

---

## How the two loads fit together

1. **Initial (full) load** — SQL Server `bank_core` (via the loader),
   `transactions_full.csv`, `merchants.json` → land everything into bronze.
2. **Incremental load** — SQL Server day-2 changes (loader `--incremental`),
   `transactions_delta.csv` → bring in only what changed since
   `max(last_updated_at)` and **merge** it.

Prove the incremental worked by picking one `transaction_id` that appears in
both the full and delta files and confirming its status changed after the merge —
with no duplicate row created.
