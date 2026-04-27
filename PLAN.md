# supply_integration — Multi-Supplier ELT Platform

## Overview

A standalone ELT pipeline and internal tooling platform that extracts product data from
promotional goods suppliers, stores raw files in AWS S3, transforms with dbt + DuckDB,
and serves two internal workflows via a Streamlit UI:

- **Bespoke** — browse the product catalogue, configure print options and a carrier,
  generate a supplier reference for a one-off order
- **Category Management (catman)** — select products by PCM template, auto-generate
  slugs, assign quantity codes, configure print options, and export a PCM configuration
  CSV for the website catalogue

Built as a portfolio project mirroring the supply_integration platform at Helloprint,
using personal API access and no proprietary data. Designed from the start to support
multiple suppliers with different API formats, data models, and supplier reference
conventions.

---

## Architecture

```
Supplier APIs (MKO, XDC, ...)
  → SupplierExtractor adapters    (per-supplier Python classes)
  → AWS S3 eu-south-2             (raw Parquet, date-partitioned, per-supplier prefix)
  → dbt + DuckDB                  (staging → intermediate → canonical marts)
  → Streamlit (3 pages)           (landing, Bespoke catalogue + order configurator, Catman)
  → Docker Compose                (containerised runtime — in progress)
```

---

## Supplier Support

| Supplier | Status | Endpoints |
|---|---|---|
| Makito (MKO) | Live | product, price, stock, print options, print prices |
| XDC | Planned | — |

Adding a new supplier requires:
1. One `XxxExtractor(SupplierExtractor)` adapter in `extractor/`
2. One set of `int_xxx_*` intermediate dbt models (adds `supplier` column)
3. One `_xxx()` function in `ui/supplier_reference.py`

No changes to `run_pipeline.py`, the canonical marts, or the UI.

---

## API Endpoints (MKO)

| Endpoint | Format | Contents |
|---|---|---|
| `product` | XML | Full product catalogue, variants, images |
| `price` | XML | 4-tier quantity-based pricing per product |
| `stock` | XML | Stock levels and availability dates per product |
| `print` | XML | Print techniques, areas, and max dimensions per product |
| `print_price` | XML | Global technique prices: 7 quantity tiers + cliché + min job cost |

---

## Data Model

### Extraction (S3)

```
supply-integration/
└── mko/
    └── raw/
        ├── product/YYYY-MM-DD/products.parquet
        ├── price/YYYY-MM-DD/prices.parquet
        ├── stock/YYYY-MM-DD/stock.parquet
        └── print/YYYY-MM-DD/print.parquet
                              print_price.parquet
```

### dbt Layers

**Staging** (views — read from S3 at query time):
- `stg_mko_products`, `stg_mko_variants`, `stg_mko_prices`, `stg_mko_stock`
- `stg_mko_print_options`, `stg_mko_print_prices`

**Intermediate** (views — add `supplier` column, normalise to canonical shape):
- `int_mko_products`, `int_mko_variants`, `int_mko_prices`, `int_mko_stock`
- `int_mko_print_options`, `int_mko_print_prices`

**Canonical marts** (tables — supplier-agnostic, queried by the UI):
- `catalog` — one row per supplier/product
- `variants`, `prices`, `print_options`, `print_prices`

**Seeds** (static reference data):
- `carriers` — 3 MKO carriers
- `mko_carrier_zones` — 72 rows: 24 countries × 3 carriers across 4 shipping zones

**Backwards-compatible supplier marts** (filter canonical tables):
- `mko_catalog`, `mko_variants`, `mko_prices`, `mko_print_options`, `mko_print_prices`

---

## Streamlit UI

| Page | Path | Purpose |
|---|---|---|
| Landing | `app.py` | Entry point — routes to Bespoke or Catman |
| Catalogue | `pages/1_Catalog.py` | Browse, filter, view product detail |
| Configure Order | `pages/2_Configure_Order.py` | Bespoke order configurator (5 steps) |
| Category Management | `pages/3_Catman.py` | PCM configuration export |

---

## Business Logic Config

`business_logic/quantity_codes.yaml` — 33 MKO template quantity code defaults, derived
from the live PCM data. Used by the catman UI to pre-fill the Qty Code column on
template selection.

---

## Build Status

| Phase | Status |
|---|---|
| AWS S3 + IAM setup | Done |
| Python extractor (product, price, stock) | Done |
| Python extractor (print options, print prices) | Done |
| dbt staging layer (6 MKO models) | Done |
| dbt intermediate layer (6 models, supplier column) | Done |
| dbt canonical mart models (5 tables) | Done |
| dbt seeds (carriers + carrier zones) | Done |
| SupplierExtractor ABC + MkoExtractor adapter | Done |
| Shared UI modules (db.py, supplier_reference.py) | Done |
| Streamlit landing page | Done |
| Streamlit Bespoke catalogue + Configure Order | Done |
| Streamlit Category Management (catman) | Done |
| Dockerfile + Docker Compose | Not started |
| README for GitHub repository | Not started |
| Airflow DAG (replace run_pipeline.py) | Not started |
| Unit tests for extractor layer | Not started |
| XDC as second supplier (validate architecture end-to-end) | Not started |
| CI/CD with GitHub Actions | Not started |

---

## Stack

- **Python 3.11** — extraction, orchestration
- **boto3** — S3 uploads
- **requests** — HTTP with retry + exponential backoff
- **dbt-duckdb 1.8** — transformation layer
- **DuckDB** — analytical query engine, reads Parquet from S3 via httpfs
- **Streamlit** — internal UI (landing page + Bespoke + Catman)
- **PyYAML** — business logic config
- **Docker Compose** — containerised runtime (in progress)

---

## Running Locally

```bash
cp .env.example .env          # fill in AWS + MKO credentials
pip install -r requirements.txt
python run_pipeline.py        # extract → S3 → dbt seed/run/test
streamlit run ui/app.py       # open UI at localhost:8501
```

Required environment variables:

```
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
S3_BUCKET, DUCKDB_PATH (optional, defaults to data/supply_integration.duckdb)
MKO_BASE_URL, MKO_URL_SUFFIX_PRODUCT, MKO_URL_SUFFIX_PRICE
MKO_URL_SUFFIX_STOCK, MKO_URL_SUFFIX_PRINT, MKO_URL_SUFFIX_PRINT_PRICE
```

---

## Project File Structure

```
supply_integration/
├── PLAN.md
├── CONTEXT.md                      (domain glossary)
├── run_pipeline.py
├── extractor/
│   ├── base.py                     (SupplierConfig dataclass, SupplierExtractor ABC)
│   ├── mko.py                      (MkoExtractor adapter)
│   ├── endpoints.py                (fetch_products, fetch_price, fetch_stock,
│   │                                fetch_print, fetch_print_price)
│   ├── client.py                   (HTTP retry logic)
│   └── loader.py                   (S3 upload)
├── dbt_project/
│   ├── profiles.yml
│   ├── dbt_project.yml
│   ├── seeds/
│   │   ├── carriers.csv
│   │   └── mko_carrier_zones.csv
│   └── models/
│       ├── staging/                (stg_mko_*.sql — 6 models)
│       ├── intermediate/           (int_mko_*.sql — 6 models)
│       └── marts/                  (canonical + supplier-specific — 10 models)
├── ui/
│   ├── app.py                      (landing page)
│   ├── db.py                       (shared query() function)
│   ├── supplier_reference.py       (build() dispatcher)
│   └── pages/
│       ├── 1_Catalog.py
│       ├── 2_Configure_Order.py
│       └── 3_Catman.py
├── business_logic/
│   ├── quantity_codes.yaml         (33 MKO template quantity code defaults)
│   └── *.csv / *.xlsx              (PCM reference files)
└── docs/
    ├── catalog_platform_journal.md / .docx
    ├── day1_aws_setup.md / .docx
    ├── day2_extraction.md / .docx
    ├── day3_transform.md / .docx
    ├── day4_streamlit_ui.md / .docx
    ├── day5_multi_supplier_architecture.md / .docx
    └── day6_catman_ui.md / .docx
```
