# Staging the cards CSVs in cloud storage

The cards transactions are **file extracts** — the classic "files landing in
storage" source. You can ingest them straight from disk, but to make Stage 1
realistic (and to mirror how a Fabric Copy job reads files in production), put
them in a storage location first. Pick whichever you have access to.

The files:

```
data/sources/cards-system/transactions_full.csv    (40,000 rows — initial load)
data/sources/cards-system/transactions_delta.csv   (8,500 rows — day-2 batch)
```

A good convention is to keep full and incremental drops in separate folders so a
watermark/incremental Copy job can target the new files only:

```
cards/transactions/full/transactions_full.csv
cards/transactions/incremental/transactions_delta.csv
```

---

## Option A — OneLake / Fabric Lakehouse Files (most native)

1. In your Fabric workspace, open (or create) a **Lakehouse**.
2. Under **Files**, create folders `cards/transactions/full` and `.../incremental`.
3. Upload the two CSVs (drag-and-drop in the Lakehouse UI, or use the OneLake
   file explorer / `azcopy`).
4. In the Copy job, choose **OneLake / Lakehouse Files** as the source and point
   at the folder. Fabric can read all files in a folder as one dataset.

## Option B — Azure Blob Storage

```bash
# az CLI
az storage container create --account-name <acct> --name cards
az storage blob upload --account-name <acct> --container-name cards \
  --name transactions/full/transactions_full.csv \
  --file data/sources/cards-system/transactions_full.csv
az storage blob upload --account-name <acct> --container-name cards \
  --name transactions/incremental/transactions_delta.csv \
  --file data/sources/cards-system/transactions_delta.csv
```
In the Copy job, use the **Azure Blob Storage** connector (account key, SAS, or
service principal) and point at the `transactions/full` folder.

## Option C — Amazon S3

```bash
aws s3 cp data/sources/cards-system/transactions_full.csv \
  s3://<bucket>/cards/transactions/full/
aws s3 cp data/sources/cards-system/transactions_delta.csv \
  s3://<bucket>/cards/transactions/incremental/
```
In the Copy job, use the **Amazon S3** connector. (This is also the multicloud
scenario the webinar demos — ingesting from S3 into OneLake.)

---

## Incremental strategy for files

Files don't have a watermark column you query like a database, so the common
patterns are:

- **Folder-per-load** — drop new files into `incremental/` and have the Copy job
  pick up only that folder on later runs (what the structure above sets up).
- **Watermark on the data** — every transaction row still has `last_updated_at`,
  so after landing in bronze you can compute `max(last_updated_at)` and filter
  there if you ingest everything.

For Stage 1, start with the **full** folder. When you reach Stage 2, bring in the
**incremental** folder and prove the new ~8,500 rows merge cleanly (watch the
~500 rows whose status changed).

---

## Prefer to keep it local for now?

Totally fine — point the Copy job (or your local dbt/DuckDB prototype) directly
at `data/sources/cards-system/`. Move to cloud storage when you want the full
Fabric connector experience.
