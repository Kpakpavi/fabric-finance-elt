# Getting started — run the loader

Everything you need to load the operational data into PostgreSQL, using **uv**
for the Python side. Do these once, top to bottom.

> Note: `uvicorn` is a web server and isn't used here. The tool you want is
> **uv** (Astral's package/environment manager).

---

## 0. Prerequisites

- **uv** — install it if you don't have it:
  ```bash
  brew install uv          # or:  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv --version
  ```
- **PostgreSQL** running with a database called `bank` (Step 1).
- A terminal opened **in this folder** (`Fabric_Finance`).

---

## 1. Get PostgreSQL running

> Already have Postgres running (you do — the `SQL` database on `localhost:5432`)?
> **Skip to Step 2.** The options below are only for setting it up from scratch.

Pick ONE option.

### Option A — Docker (easiest; matches the script's defaults exactly)
```bash
docker run --name bank-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=bank \
  -p 5432:5432 -d postgres:16
```
This gives you host `localhost`, port `5432`, db `bank`, user `postgres`,
password `postgres` — which is exactly what the script assumes, so you won't
need any extra config. (Start it again later with `docker start bank-pg`.)

### Option B — Homebrew (native install)
```bash
brew install postgresql@16
brew services start postgresql@16
createdb bank
```
With Homebrew the superuser is your macOS username (no password), so you'll pass
a DSN when you run the script — see the note in Step 4.

**Check it's up:**
```bash
pg_isready -h localhost -p 5432    # should say "accepting connections"
```

---

## 2. Set up the Python environment with uv

From the `Fabric_Finance` folder:

```bash
uv venv                                  # creates .venv/
source .venv/bin/activate                # activate it
uv pip install -r scripts/requirements.txt
```

You should now see `(.venv)` in your prompt and `psycopg2` installed.

---

## 3. Tell the script how to connect — via `.env`

A `.env` file already exists at the project root with your settings:

```
PGHOST=localhost
PGPORT=5432
PGDATABASE=SQL
PGUSER=postgres
PGPASSWORD=CHANGE_ME      ← put your real Postgres password here
PGSCHEMA=bank_core        ← the loader creates/uses this schema inside SQL
```

**Edit `.env` and replace `CHANGE_ME` with your password.** That's the only thing
you have to change. The script auto-loads this file — no exporting needed.

(`.env` is git-ignored so your password never gets committed. `.env.example` is
the shareable template.)

---

## 4. Run the full load

```bash
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

Open a SQL prompt (or just browse it in DataGrip):
```bash
psql "postgresql://postgres:YOUR_PASSWORD@localhost:5432/SQL"
```
Then:
```sql
\dt bank_core.*
SELECT count(*) FROM bank_core.customers;   -- 2015
SELECT count(*) FROM bank_core.accounts;    -- 3951
-- proof the messiness is intact (for your Stage 3 dedupe):
SELECT customer_id, count(*) FROM bank_core.customers
GROUP BY customer_id HAVING count(*) > 1;   -- ~15 duplicate ids
\q
```

---

## 6. Later — run the incremental (day-2) merge

When you want to simulate the source system changing over time:
```bash
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
SELECT count(*) FROM bank_core.accounts;  -- ~4031 now
SELECT account_id, count(*) FROM bank_core.accounts
GROUP BY account_id HAVING count(*) > 1;  -- 0 rows
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `psycopg2 not installed` | Activate the venv (`source .venv/bin/activate`) and re-run Step 2. |
| `could not connect to server` / `Connection refused` | Postgres isn't running. Re-check Step 1 (`pg_isready`, `docker start bank-pg`). |
| `password authentication failed` | Wrong password in `.env` — fix `PGPASSWORD`. |
| `database "SQL" does not exist` | Check `PGDATABASE` in `.env` matches your actual database name. |
| `Source file not found` | Run from the `Fabric_Finance` folder so `data/sources/...` resolves. |

---

## What's next
With `bank_core` populated, you're ready for **Stage 1**: build the Copy job that
ingests `bank_core.customers` / `bank_core.accounts` from Postgres into your
bronze layer. See `ROADMAP.md`.
