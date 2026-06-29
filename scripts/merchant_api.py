#!/usr/bin/env python3
"""
merchant_api.py
===============
A tiny REST API (FastAPI + uvicorn) that serves the merchant reference feed —
standing in for a real SaaS / API source system in this project. This gives you
a genuine HTTP endpoint to ingest from with a Copy job's REST connector, instead
of a static file.

Setup & run
-----------
    uv pip install -r scripts/requirements-api.txt
    # from the Fabric_Finance folder:
    uvicorn scripts.merchant_api:app --reload --port 8000
    # ...or just:
    python scripts/merchant_api.py

Then open / call:
    http://localhost:8000/                 -> service info
    http://localhost:8000/merchants        -> all merchants
    http://localhost:8000/merchants?category=Travel
    http://localhost:8000/merchants?updated_since=2025-06-30T23:59:59   (incremental pulls)
    http://localhost:8000/merchants/MER0001
    http://localhost:8000/docs             -> interactive Swagger UI
"""
import json
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "..", "data", "sources", "merchant-api", "merchants.json")

with open(FEED) as f:
    MERCHANTS = json.load(f)["merchants"]


# ---- response models (these drive the Swagger schema + example values) ----
class Merchant(BaseModel):
    merchant_id: str = Field(..., examples=["MER0001"])
    merchant_name: str = Field(..., examples=["Electronics Co 1"])
    category: str = Field(..., examples=["Electronics"])
    country: str = Field(..., examples=["USA"])
    last_updated_at: str = Field(..., examples=["2025-06-30 23:59:59"])


class MerchantList(BaseModel):
    count: int = Field(..., examples=[150])
    merchants: List[Merchant]


class ServiceInfo(BaseModel):
    service: str = Field(..., examples=["merchant-feed"])
    count: int = Field(..., examples=[150])
    endpoints: List[str]


app = FastAPI(
    title="Merchant Feed API",
    version="1.0",
    description="Mock SaaS/API source for the Fabric ELT project (serves merchants.json).",
)


@app.get("/", response_model=ServiceInfo, summary="Service info")
def root():
    return {
        "service": "merchant-feed",
        "count": len(MERCHANTS),
        "endpoints": ["/merchants", "/merchants/{merchant_id}", "/docs"],
    }


@app.get("/merchants", response_model=MerchantList, summary="List merchants")
def list_merchants(
    category: Optional[str] = Query(None, description="filter by category (case-insensitive)"),
    updated_since: Optional[str] = Query(
        None,
        description="ISO timestamp; returns rows with last_updated_at > this value "
                    "(use this to simulate incremental / watermark API pulls)",
    ),
):
    rows = MERCHANTS
    if category:
        rows = [m for m in rows if m.get("category", "").lower() == category.lower()]
    if updated_since:
        rows = [m for m in rows if str(m.get("last_updated_at", "")) > updated_since]
    return {"count": len(rows), "merchants": rows}


@app.get(
    "/merchants/{merchant_id}",
    response_model=Merchant,
    summary="Get one merchant",
    responses={404: {"description": "Merchant not found"}},
)
def get_merchant(merchant_id: str):
    for m in MERCHANTS:
        if m["merchant_id"] == merchant_id:
            return m
    raise HTTPException(status_code=404, detail=f"merchant {merchant_id} not found")


if __name__ == "__main__":
    import uvicorn
    # pass the app object directly so it works regardless of the current directory
    uvicorn.run(app, host="0.0.0.0", port=8000)
