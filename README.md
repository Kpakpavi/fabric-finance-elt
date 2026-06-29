# Finance Data Migration — Microsoft Fabric ELT (in progress)

A governed **ELT pipeline** that migrates messy retail-banking data from three
source systems into **Microsoft Fabric**, cleans it through a **medallion
architecture** (bronze → silver → gold) with **dbt**, tests it, and serves it to
Power BI. Built as a hands-on portfolio project modelled on the Fabric Data
Factory "Copy job + dbt job" pattern.

> Status: **Stage 1 — landing data into Fabric bronze.** See `docs/progress.png`.

## The sources (three different connectors, on purpose)
- **Operational DB** — PostgreSQL (`customers`, `accounts`) loaded by `scripts/load_operational_db.py`
- **Cards platform** — CSV file extracts (`transactions`)
- **Merchant feed** — a live REST API (FastAPI + uvicorn, `scripts/merchant_api.py`)
- **Reference data** — currency / country / category lookups (dbt seeds)

## What's here
| Path | What it is |
|---|---|
| `WORK_ORDER` → `docs/WORK_ORDER.md` | The project brief / scope and the 10 data issues to fix |
| `ROADMAP.md` | The 10-stage plan, at a glance |
| `docs/data_migration_map.png` | Source → bronze → silver → gold transformation map |
| `docs/STAGE1_land_in_fabric.md` | How to land the sources into Fabric (Mac / gateway-free) |
| `GETTING_STARTED.md` | Set up Postgres + the loader with uv |
| `data/` | The (synthetic) source data + `SOURCES.md` |
| `scripts/` | Postgres loader + merchant REST API |
| `docs/progress.png` | Live progress tracker |

## Quick start
```bash
uv venv && source .venv/bin/activate
uv pip install -r scripts/requirements.txt
python scripts/load_operational_db.py --full     # load Postgres source
uv pip install -r scripts/requirements-api.txt
uvicorn scripts.merchant_api:app --port 8000      # run the merchant API
```
Full setup in `GETTING_STARTED.md`.

## Tech
Microsoft Fabric (Lakehouse, Copy job, dbt job, pipelines) · dbt · PostgreSQL ·
Python (FastAPI/uvicorn) · medallion / ELT · data-quality testing · Power BI.

*All data is synthetic and safe to share publicly.*
