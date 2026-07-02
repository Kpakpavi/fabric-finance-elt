# Getting started — run the loader

Everything you need to load the operational data into SQL Server (browsed via SSMS),
using **uv** for the Python side. Do these once, top to bottom.

---

## 0. Prerequisites

- **uv** — install it if you don't have it:
  ```powershell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  uv --version
  ```
- **SQL Server** running locally. SQL Server Express is free and sufficient.
  Download: https://www.microsoft.com/en-us/sql-server/sql-server-downloads
- **SSMS** (SQL Server Management Studio) to browse and verify the data.
  Download: https://aka.ms/ssmsfullsetup
- **ODBC Driver 17 (or 18) for SQL Server** installed on this machine.
  Download: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
- A terminal opened **in this folder** (`fabric-finance-elt`).

---

## 1. Create the target database in SSMS

Open SSMS and connect to your local instance (e.g. `localhost` or `.\SQLEXPRESS`).
Run this in a New Query window:

```sql
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'bank')
    CREATE DATABASE bank;
```

The loader will create the `bank_core` schema and both tables automatically on first run.

---

## 2. Set up the Python environment with uv

From the `fabric-finance-elt` folder (PowerShell):

```powershell
uv venv
.venv\Scripts\Activate.ps1
uv pip install -r scripts/requirements.txt
```

You should now see `(.venv)` in your prompt and `pyodbc` installed.

---

## 3. Tell the script how to connect — via `.env`

A `.env` file already exists at the project root. The default uses **Windows
Authentication**, which works out of the box for a local SQL Server:

```
MSSQL_SERVER=localhost
MSSQL_DATABASE=bank
MSSQL_SCHEMA=bank_core
MSSQL_TRUSTED_CONNECTION=yes
```

If you're using **SQL Server Authentication** (sa login or a named user), switch to:

```
MSSQL_SERVER=localhost
MSSQL_DATABASE=bank
MSSQL_USERNAME=sa
MSSQL_PASSWORD=your_password_here
MSSQL_SCHEMA=bank_core
MSSQL_TRUSTED_CONNECTION=no
```

The script auto-loads this file — no exporting needed.

(`.env` is git-ignored so your password never gets committed. `.env.example` is
the shareable template.)

---

## 4. Run the full load

```powershell
python scripts/load_operational_db.py --full
```

Expected output:
```
FULL LOAD into schema 'bank_core':
  customers: 2,015 rows  (raw — duplicates intact for the dedupe exercise)
  accounts : 3,951 rows
```

---

## 5. Verify it landed

In SSMS, open a New Query window on the `bank` database and run:

```sql
SELECT COUNT(*) FROM bank_core.customers;   -- 2015
SELECT COUNT(*) FROM bank_core.accounts;    -- 3951

-- proof the messiness is intact (for your Stage 3 dedupe):
SELECT customer_id, COUNT(*) AS cnt
FROM bank_core.customers
GROUP BY customer_id
HAVING COUNT(*) > 1;   -- ~15 duplicate ids
```

---

## 6. Later — run the incremental (day-2) merge

When you want to simulate the source system changing over time:

```powershell
python scripts/load_operational_db.py --incremental
```

Expected:
```
INCREMENTAL LOAD (merge) into schema 'bank_core':
  customers: 160 delta rows merged (42 existing matched & replaced, rest inserted)
  accounts : 230 delta rows upserted (insert or update on account_id)
```

Verify the merge actually updated an existing account (no duplicate created):

```sql
SELECT COUNT(*) FROM bank_core.accounts;  -- ~4031 now

SELECT account_id, COUNT(*) AS cnt
FROM bank_core.accounts
GROUP BY account_id
HAVING COUNT(*) > 1;  -- 0 rows
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pyodbc not installed` | Activate the venv (`.venv\Scripts\Activate.ps1`) and re-run Step 2. |
| `Connection failed` / `Login failed for user` | Check `MSSQL_USERNAME` / `MSSQL_PASSWORD` in `.env`, or switch to `MSSQL_TRUSTED_CONNECTION=yes`. |
| `[IM002] Data source name not found` | Install the ODBC Driver 17 for SQL Server (see Prerequisites). |
| `Cannot open database "bank"` | Create the `bank` database in SSMS first (Step 1). |
| `Schema 'bank_core' not initialised` | Run `--full` before `--incremental`. |
| `Source file not found` | Run from the `fabric-finance-elt` folder so `data/sources/...` resolves. |

---

## What's next
With `bank_core` populated, you're ready for **Stage 1**: build the Copy job that
ingests `bank_core.customers` / `bank_core.accounts` from SQL Server into your
bronze layer. See `ROADMAP.md`.
