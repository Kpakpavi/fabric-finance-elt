#!/usr/bin/env python3
"""
load_operational_db.py
======================
Loads the bank's operational data (customers + accounts) into **PostgreSQL** so
that Postgres can act as the SOURCE operational database for this ELT project —
the system your Fabric Copy job will later ingest from (Stage 1).

It reads the source extracts that ship with the project:
    data/sources/operational-db/customers_full.csv  + accounts_full.csv   (snapshot)
    data/sources/operational-db/customers_delta.csv + accounts_delta.csv  (day-2)

Two modes:
    --full          create the schema/tables and load the initial snapshot
    --incremental   apply the day-2 batch as a MERGE/UPSERT (new rows inserted,
                    changed rows updated) keyed on the natural key + watermark

Quick start
-----------
    pip install psycopg2-binary
    # set your connection (env vars shown with their defaults):
    export PGHOST=localhost PGPORT=5432 PGDATABASE=bank PGUSER=postgres PGPASSWORD=postgres
    python scripts/load_operational_db.py --full
    python scripts/load_operational_db.py --incremental
    # ...or pass a DSN directly:
    python scripts/load_operational_db.py --full --dsn "postgresql://postgres:postgres@localhost:5432/bank"

Notes
-----
* The data is intentionally messy (mixed casing, padded whitespace, blank KYC,
  and DUPLICATE customer_id rows). That is on purpose — cleaning it is Stage 3.
  Because of the duplicates, `customers` is loaded WITHOUT a unique key;
  `accounts` keeps a primary key on account_id.
* Dates / numbers / timestamps are typed; the free-text columns stay messy.
"""

import argparse
import csv
import os
import sys

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    sys.exit("psycopg2 not installed. Run:  uv pip install -r scripts/requirements.txt")

DEFAULT_SCHEMA = "bank_core"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "..", "data", "sources", "operational-db")

# Load connection settings from a .env file at the project root, if present.
# (Falls back silently to real env vars / --dsn when python-dotenv isn't installed.)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, "..", ".env"))
except ImportError:
    pass

# (column_name, postgres_type)
CUSTOMER_COLS = [
    ("customer_id", "text"), ("first_name", "text"), ("last_name", "text"),
    ("email", "text"), ("country", "text"), ("kyc_status", "text"),
    ("signup_date", "date"), ("last_updated_at", "timestamp"),
]
ACCOUNT_COLS = [
    ("account_id", "text"), ("customer_id", "text"), ("account_type", "text"),
    ("currency", "text"), ("opened_date", "date"), ("status", "text"),
    ("credit_limit", "numeric"), ("last_updated_at", "timestamp"),
]


def read_csv(filename):
    """Return (column_names, rows) from a CSV source extract."""
    path = os.path.join(SRC_DIR, filename)
    if not os.path.exists(path):
        sys.exit(f"Source file not found: {path}")
    with open(path, newline="") as f:
        reader = csv.reader(f)
        cols = next(reader)
        rows = [tuple(r) for r in reader]
    return cols, rows


def connect(args):
    if args.dsn:
        return psycopg2.connect(args.dsn)
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "bank"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )


def ddl(cur, schema):
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
    cust = ", ".join(f"{n} {t}" for n, t in CUSTOMER_COLS)
    acct = ", ".join(f"{n} {t}" for n, t in ACCOUNT_COLS)
    # customers: NO unique key (raw snapshot contains duplicate customer_ids on purpose)
    cur.execute(f"DROP TABLE IF EXISTS {schema}.customers;")
    cur.execute(f"CREATE TABLE {schema}.customers ({cust});")
    cur.execute(f"CREATE INDEX ix_customers_id ON {schema}.customers (customer_id);")
    # accounts: real primary key on account_id (enables clean upsert)
    cur.execute(f"DROP TABLE IF EXISTS {schema}.accounts;")
    cur.execute(f"CREATE TABLE {schema}.accounts ({acct}, PRIMARY KEY (account_id));")


def bulk_insert(cur, schema, table, cols, rows):
    if not rows:
        return 0
    collist = ", ".join(cols)
    execute_values(cur, f"INSERT INTO {schema}.{table} ({collist}) VALUES %s", rows)
    return len(rows)


def full_load(args):
    conn = connect(args)
    with conn, conn.cursor() as cur:
        ddl(cur, args.schema)
        c_cols, c_rows = read_csv("customers_full.csv")
        a_cols, a_rows = read_csv("accounts_full.csv")
        nc = bulk_insert(cur, args.schema, "customers", c_cols, c_rows)
        na = bulk_insert(cur, args.schema, "accounts", a_cols, a_rows)
    conn.close()
    print(f"FULL LOAD into schema '{args.schema}':")
    print(f"  customers: {nc:,} rows  (raw — duplicates intact for the dedupe exercise)")
    print(f"  accounts : {na:,} rows")


def incremental_load(args):
    """Apply the day-2 changes as a merge.
    accounts -> UPSERT via ON CONFLICT(account_id).
    customers -> delete-then-insert by customer_id (no unique key available)."""
    conn = connect(args)
    s = args.schema
    with conn, conn.cursor() as cur:
        cur.execute(f"SELECT to_regclass('{s}.customers');")
        if cur.fetchone()[0] is None:
            sys.exit(f"Schema '{s}' not initialised. Run --full first.")

        # --- customers merge ---
        c_cols, c_rows = read_csv("customers_delta.csv")
        cust_keys = [r[c_cols.index("customer_id")] for r in c_rows]
        cur.execute(f"DELETE FROM {s}.customers WHERE customer_id = ANY(%s);", (cust_keys,))
        deleted_c = cur.rowcount
        bulk_insert(cur, s, "customers", c_cols, c_rows)

        # --- accounts upsert ---
        a_cols, a_rows = read_csv("accounts_delta.csv")
        collist = ", ".join(a_cols)
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in a_cols if c != "account_id")
        sql = (f"INSERT INTO {s}.accounts ({collist}) VALUES %s "
               f"ON CONFLICT (account_id) DO UPDATE SET {updates};")
        execute_values(cur, sql, a_rows)
    conn.close()
    print(f"INCREMENTAL LOAD (merge) into schema '{s}':")
    print(f"  customers: {len(c_rows):,} delta rows merged "
          f"({deleted_c:,} existing matched & replaced, rest inserted)")
    print(f"  accounts : {len(a_rows):,} delta rows upserted (insert or update on account_id)")


def main():
    p = argparse.ArgumentParser(description="Load the operational DB (customers, accounts) into PostgreSQL.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="create schema + load initial snapshot")
    mode.add_argument("--incremental", action="store_true", help="apply day-2 changes as a merge")
    p.add_argument("--schema", default=os.getenv("PGSCHEMA", DEFAULT_SCHEMA),
                   help="target schema (default: $PGSCHEMA or bank_core)")
    p.add_argument("--dsn", help="full Postgres DSN; overrides PG* env vars")
    args = p.parse_args()
    if args.full:
        full_load(args)
    else:
        incremental_load(args)


if __name__ == "__main__":
    main()
