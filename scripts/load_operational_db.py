#!/usr/bin/env python3
"""
load_operational_db.py
======================
Loads the bank's operational data (customers + accounts) into **SQL Server** so
that SQL Server can act as the SOURCE operational database for this ELT project —
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
    uv pip install -r scripts/requirements.txt

    # Windows Authentication (recommended for a local SQL Server):
    set MSSQL_SERVER=localhost
    set MSSQL_DATABASE=bank
    set MSSQL_TRUSTED_CONNECTION=yes
    python scripts/load_operational_db.py --full
    python scripts/load_operational_db.py --incremental

    # SQL Server Authentication:
    set MSSQL_SERVER=localhost
    set MSSQL_DATABASE=bank
    set MSSQL_USERNAME=sa
    set MSSQL_PASSWORD=your_password
    python scripts/load_operational_db.py --full

    # Or pass a full ODBC connection string directly:
    python scripts/load_operational_db.py --full --conn "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=bank;Trusted_Connection=yes"

Prerequisites
-------------
* Microsoft ODBC Driver 17 (or 18) for SQL Server must be installed.
  Download: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

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
    import pyodbc
except ImportError:
    sys.exit("pyodbc not installed. Run:  uv pip install -r scripts/requirements.txt")

DEFAULT_SCHEMA = "bank_core"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "..", "data", "sources", "operational-db")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, "..", ".env"))
except ImportError:
    pass

# (column_name, sql_server_type)
CUSTOMER_COLS = [
    ("customer_id",     "varchar(50)"),
    ("first_name",      "varchar(100)"),
    ("last_name",       "varchar(100)"),
    ("email",           "varchar(255)"),
    ("country",         "varchar(100)"),
    ("kyc_status",      "varchar(50)"),
    ("signup_date",     "date"),
    ("last_updated_at", "datetime2"),
]
ACCOUNT_COLS = [
    ("account_id",      "varchar(50)"),
    ("customer_id",     "varchar(50)"),
    ("account_type",    "varchar(50)"),
    ("currency",        "varchar(10)"),
    ("opened_date",     "date"),
    ("status",          "varchar(50)"),
    ("credit_limit",    "decimal(18,2)"),
    ("last_updated_at", "datetime2"),
]


def read_csv(filename):
    """Return (column_names, rows) from a CSV source extract. Empty strings become NULL."""
    path = os.path.join(SRC_DIR, filename)
    if not os.path.exists(path):
        sys.exit(f"Source file not found: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        cols = next(reader)
        rows = [tuple(None if v == "" else v for v in r) for r in reader]
    return cols, rows


def build_conn_string(args):
    if args.conn:
        return args.conn
    driver   = "ODBC Driver 17 for SQL Server"
    server   = os.getenv("MSSQL_SERVER",   "localhost")
    database = os.getenv("MSSQL_DATABASE", "bank")
    trusted  = os.getenv("MSSQL_TRUSTED_CONNECTION", "no").lower() in ("yes", "true", "1")
    if trusted:
        return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes"
    username = os.getenv("MSSQL_USERNAME", "sa")
    password = os.getenv("MSSQL_PASSWORD", "")
    return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={username};PWD={password}"


def connect(args):
    conn_str = build_conn_string(args)
    try:
        conn = pyodbc.connect(conn_str)
        conn.autocommit = False
        return conn
    except pyodbc.Error as e:
        sys.exit(f"Connection failed.\n{e}\nConnection string: {conn_str}")


def ddl(cur, schema):
    cur.execute(f"""
        IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{schema}')
            EXEC('CREATE SCHEMA [{schema}]')
    """)

    # customers: NO unique key (raw snapshot has duplicate customer_ids on purpose)
    cur.execute(f"DROP TABLE IF EXISTS [{schema}].[customers]")
    cust = ", ".join(f"[{n}] {t}" for n, t in CUSTOMER_COLS)
    cur.execute(f"CREATE TABLE [{schema}].[customers] ({cust})")
    cur.execute(f"CREATE INDEX ix_customers_id ON [{schema}].[customers] (customer_id)")

    # accounts: real primary key on account_id (enables clean upsert)
    cur.execute(f"DROP TABLE IF EXISTS [{schema}].[accounts]")
    acct = ", ".join(f"[{n}] {t}" for n, t in ACCOUNT_COLS)
    cur.execute(f"""
        CREATE TABLE [{schema}].[accounts] (
            {acct},
            PRIMARY KEY (account_id)
        )
    """)


def bulk_insert(cur, schema, table, cols, rows, batch_size=500):
    if not rows:
        return 0
    col_list     = ", ".join(f"[{c}]" for c in cols)
    placeholders = ", ".join("?" * len(cols))
    # Temp tables are referenced without schema brackets
    if schema == "#":
        sql = f"INSERT INTO #{table} ({col_list}) VALUES ({placeholders})"
    else:
        sql = f"INSERT INTO [{schema}].[{table}] ({col_list}) VALUES ({placeholders})"
    for i in range(0, len(rows), batch_size):
        cur.executemany(sql, rows[i:i + batch_size])
    return len(rows)


def full_load(args):
    conn = connect(args)
    cur  = conn.cursor()
    try:
        ddl(cur, args.schema)
        c_cols, c_rows = read_csv("customers_full.csv")
        a_cols, a_rows = read_csv("accounts_full.csv")
        nc = bulk_insert(cur, args.schema, "customers", c_cols, c_rows)
        na = bulk_insert(cur, args.schema, "accounts",  a_cols, a_rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print(f"FULL LOAD into schema '{args.schema}':")
    print(f"  customers: {nc:,} rows  (raw — duplicates intact for the dedupe exercise)")
    print(f"  accounts : {na:,} rows")


def incremental_load(args):
    """Apply the day-2 changes as a merge.
    accounts  -> MERGE via a staging temp table (upsert on account_id).
    customers -> delete-then-insert by customer_id (no unique key available)."""
    conn = connect(args)
    s    = args.schema
    cur  = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM sys.schemas WHERE name = ?", (s,))
        if cur.fetchone()[0] == 0:
            sys.exit(f"Schema '{s}' not initialised. Run --full first.")

        # --- customers: delete matching keys, then insert delta rows ---
        c_cols, c_rows = read_csv("customers_delta.csv")
        key_idx      = c_cols.index("customer_id")
        cust_keys    = list({r[key_idx] for r in c_rows})
        placeholders = ", ".join("?" * len(cust_keys))
        cur.execute(
            f"DELETE FROM [{s}].[customers] WHERE customer_id IN ({placeholders})",
            cust_keys,
        )
        deleted_c = cur.rowcount
        bulk_insert(cur, s, "customers", c_cols, c_rows)

        # --- accounts: stage into a temp table, then MERGE ---
        a_cols, a_rows = read_csv("accounts_delta.csv")
        tmp_cols = ", ".join(f"[{n}] {t}" for n, t in ACCOUNT_COLS)
        cur.execute(f"CREATE TABLE #accounts_stage ({tmp_cols})")
        bulk_insert(cur, "#", "accounts_stage", a_cols, a_rows)

        col_list   = ", ".join(f"[{c}]" for c in a_cols)
        src_vals   = ", ".join(f"src.[{c}]" for c in a_cols)
        update_set = ", ".join(
            f"tgt.[{c}] = src.[{c}]" for c in a_cols if c != "account_id"
        )
        cur.execute(f"""
            MERGE [{s}].[accounts] AS tgt
            USING #accounts_stage AS src
                ON tgt.[account_id] = src.[account_id]
            WHEN MATCHED THEN
                UPDATE SET {update_set}
            WHEN NOT MATCHED THEN
                INSERT ({col_list}) VALUES ({src_vals});
        """)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print(f"INCREMENTAL LOAD (merge) into schema '{s}':")
    print(f"  customers: {len(c_rows):,} delta rows merged "
          f"({deleted_c:,} existing matched & replaced, rest inserted)")
    print(f"  accounts : {len(a_rows):,} delta rows upserted (insert or update on account_id)")


def main():
    p = argparse.ArgumentParser(
        description="Load the operational DB (customers, accounts) into SQL Server."
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full",        action="store_true", help="create schema + load initial snapshot")
    mode.add_argument("--incremental", action="store_true", help="apply day-2 changes as a merge")
    p.add_argument(
        "--schema",
        default=os.getenv("MSSQL_SCHEMA", DEFAULT_SCHEMA),
        help="target schema (default: $MSSQL_SCHEMA or bank_core)",
    )
    p.add_argument("--conn", help="full ODBC connection string; overrides MSSQL_* env vars")
    args = p.parse_args()
    if args.full:
        full_load(args)
    else:
        incremental_load(args)


if __name__ == "__main__":
    main()
