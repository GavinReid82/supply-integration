# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the full pipeline (extract → S3 → dbt seed/run/test)
python run_pipeline.py

# Run dbt steps individually (from dbt_project/ directory)
cd dbt_project && dbt seed
cd dbt_project && dbt run
cd dbt_project && dbt test
cd dbt_project && dbt run --select staging
cd dbt_project && dbt run --select marts.catalog

# Launch the Streamlit UI
streamlit run ui/app.py

# Environment setup
cp .env.example .env   # then fill in AWS + MKO credentials
pip install -r requirements.txt
```

## Architecture

This is an ELT pipeline that extracts supplier product data, stores it in S3, transforms it with dbt+DuckDB, and serves it through a Streamlit UI.

```
Supplier APIs (MKO, future: XDC, ...)
  ↓
Python Extractors (extractor/*.py)  →  AWS S3 (Parquet, date-partitioned)
  ↓
dbt + DuckDB (staging → intermediate → canonical marts)
  ↓
Streamlit UI (ui/app.py + ui/pages/)
```

### Extraction Layer (`extractor/`)

- `base.py` — `SupplierConfig` dataclass + `SupplierExtractor` abstract base class. All supplier adapters must subclass this.
- `mko.py` — `MkoExtractor`: orchestrates fetching all 5 MKO feeds and uploading to S3.
- `endpoints.py` — Five fetch functions (`fetch_products`, `fetch_price`, `fetch_stock`, `fetch_print`, `fetch_print_price`) that parse XML responses into DataFrames.
- `client.py` — HTTP retry logic with exponential backoff via `tenacity`.
- `loader.py` — `upload_dataframe()` converts DataFrames to Parquet and uploads to S3.

`run_pipeline.py` loads supplier configs from `.env`, instantiates the relevant extractor, runs it, then invokes `dbt seed && dbt run && dbt test`.

### dbt Data Model (`dbt_project/`)

Three-layer transformation, all targeting DuckDB via the `dbt-duckdb` adapter:

| Layer | Materialization | Purpose |
|-------|----------------|---------|
| `staging/stg_mko_*` | view | Raw type casting + light cleaning from S3 Parquet |
| `intermediate/int_mko_*` | view | Normalize to canonical shape, add `supplier='mko'` column |
| `marts/catalog`, `variants`, `prices`, `print_options`, `print_prices` | table | Canonical, supplier-agnostic (unions all intermediate models) |
| `marts/mko_*` (5 models) | table | Supplier-filtered views of canonical marts |

DuckDB reads S3 Parquet directly via the `httpfs` extension — no local copy of raw data. Connection config is in `dbt_project/profiles.yml`; DuckDB file defaults to `data/supply_integration.duckdb` (overridable via `DUCKDB_PATH` env var).

Seeds in `dbt_project/seeds/`: `carriers.csv` (3 MKO carriers) and `mko_carrier_zones.csv` (72 rows).

### UI Layer (`ui/`)

- `app.py` — Landing page routing to Bespoke or Catman workflows.
- `db.py` — Shared `query(sql, params)` function; connects to DuckDB in read-only mode.
- `pages/1_Catalog.py` — Catalog browser with category/price filters and product detail panel.
- `pages/2_Configure_Order.py` — 5-step Bespoke order configurator (product → variant → print options → carrier → supplier reference).
- `pages/3_Catman.py` — Category Management: configure PCM templates, assign slugs + quantity codes, export CSV.
- `supplier_reference.py` — Dispatcher that builds supplier-specific order reference strings (format varies per supplier).

Business logic reference data (PCM templates, quantity code defaults) lives in `business_logic/`.

## Adding a New Supplier

The architecture is designed so adding supplier XYZ requires:
1. A new `extractor/xyz.py` implementing `SupplierExtractor`
2. New `dbt_project/models/staging/stg_xyz_*.sql` + `intermediate/int_xyz_*.sql` models
3. Union the new intermediate models into the canonical mart `.sql` files
4. A new case in `ui/supplier_reference.py`
5. Zero changes to `run_pipeline.py`, canonical mart schemas, or the UI pages

## Environment Variables

Required in `.env`:
```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_DEFAULT_REGION=eu-south-2
S3_BUCKET=supply-integration
MKO_BASE_URL
MKO_URL_SUFFIX_PRODUCT
MKO_URL_SUFFIX_PRICE
MKO_URL_SUFFIX_STOCK
MKO_URL_SUFFIX_PRINT
MKO_URL_SUFFIX_PRINT_PRICE
DUCKDB_PATH   # optional, defaults to data/supply_integration.duckdb
```
