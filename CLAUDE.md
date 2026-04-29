# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the full pipeline (extract → S3 → dbt seed/run/test)
python run_pipeline.py

# Run dbt steps individually (from project root, not dbt_project/)
dbt seed --project-dir dbt_project --profiles-dir dbt_project
dbt run --project-dir dbt_project --profiles-dir dbt_project
dbt run --project-dir dbt_project --profiles-dir dbt_project --exclude tag:xdc   # MKO-only, no XDC credentials needed
dbt test --project-dir dbt_project --profiles-dir dbt_project
dbt run --project-dir dbt_project --profiles-dir dbt_project --select staging
dbt run --project-dir dbt_project --profiles-dir dbt_project --select marts.catalog

# Run tests
pytest tests/                                          # all tests
pytest tests/extractor/test_endpoints.py               # single file
pytest tests/extractor/test_endpoints.py::test_fetch_products_returns_three_dataframes  # single test

# Launch the Streamlit UI
streamlit run ui/app.py

# Environment setup
cp .env.example .env   # then fill in AWS + supplier credentials
pip install -r requirements.txt
```

## Hooks (automatic, project-level)

Two hooks run automatically via `.claude/settings.json`:

- **PostToolUse (Edit/Write on `.py`)** — runs `python -m py_compile` on the edited file; blocks the turn if there's a syntax error.
- **Stop** — runs `dbt parse` against `dbt_project/`; blocks completion if any dbt model has a parse error.

Do not bypass these with `--no-verify`.

## Architecture

ELT pipeline: supplier APIs → S3 (Parquet) → dbt+DuckDB → Streamlit UI.

```
Supplier APIs (MKO, XDC)
  ↓
Python Extractors (extractor/*.py)  →  AWS S3 (Parquet, date-partitioned)
  ↓
dbt + DuckDB (staging → intermediate → canonical marts)
  ↓
Streamlit UI (ui/app.py + ui/pages/)
```

### Extraction Layer (`extractor/`)

- `base.py` — `SupplierConfig` dataclass + `SupplierExtractor` abstract base. All adapters subclass this.
- `mko.py` — `MkoExtractor`: fetches 5 XML feeds, uploads to S3.
- `xdc.py` — `XdcExtractor`: fetches 5 XLSX files at authenticated full URLs, normalises column names, uploads to S3.
- `endpoints.py` — Five `fetch_*` functions (MKO-specific) that parse XML → DataFrames.
- `client.py` — `get_with_retry()`: HTTP with exponential backoff via `tenacity`.
- `loader.py` — `upload_dataframe()`: DataFrame → Parquet → S3.

`run_pipeline.py` builds the supplier list from env vars. XDC is opt-in: it only activates when `XDC_BASE_URL` is set.

### dbt Data Model (`dbt_project/`)

Three-layer transformation targeting DuckDB via `dbt-duckdb`:

| Layer | Materialization | Purpose |
|-------|----------------|---------|
| `staging/stg_{mko,xdc}_*` | view | Type casting + light cleaning from S3 Parquet |
| `intermediate/int_{mko,xdc}_*` | view | Normalise to canonical column shape, add `supplier` column |
| `marts/catalog`, `variants`, `prices`, `print_options`, `print_prices`, `production_days` | table | Canonical, supplier-agnostic (unions all intermediate models) |
| `marts/mko_*` | table | Supplier-filtered views of canonical marts |

DuckDB reads S3 Parquet directly via the `httpfs` extension — no local copy of raw data. DuckDB file defaults to `data/catalog_data_platform.duckdb` (override via `DUCKDB_PATH`).

Seeds in `dbt_project/seeds/`: `carriers.csv`, `mko_carrier_zones.csv`, `pcm_templates.csv`, `mko_product__hscode.csv`, `xdc_availability_thresholds.csv`, `xdc_production_days.csv`.

### UI Layer (`ui/`)

- `app.py` — Landing page routing.
- `db.py` — Shared `query(sql, params)` helper; DuckDB read-only connection.
- `basket.py` — Session-state basket for the Bespoke workflow (`add_to_basket`, `show_basket`).
- `pages/0_Home.py` — Home page.
- `pages/1_Catalog.py` — Catalog browser with category/price filters and product detail panel.
- `pages/2_Configure_Order.py` — 5-step Bespoke order configurator (product → variant → print options → carrier → supplier reference). Uses `basket.py`.
- `pages/3_Catman.py` — Category Management: configure PCM templates, assign slugs + quantity codes, export CSV.
- `supplier_reference.py` — Builds supplier-specific order reference strings (format varies by supplier and product type).

Business logic reference data (PCM templates, quantity code defaults) lives in `business_logic/`. Domain terminology is in `CONTEXT.md`.

## Adding a New Supplier

1. New `extractor/xyz.py` implementing `SupplierExtractor`
2. New `dbt_project/models/staging/stg_xyz_*.sql` + `intermediate/int_xyz_*.sql` models
3. Union the new intermediate models into the canonical mart `.sql` files
4. New case in `ui/supplier_reference.py`
5. `run_pipeline.py`, canonical mart schemas, and UI pages need zero changes

## Environment Variables

MKO (required):
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
DUCKDB_PATH   # optional, defaults to data/catalog_data_platform.duckdb
```

XDC (optional — set these to activate XDC extraction):
```
XDC_BASE_URL
XDC_URL_SUFFIX_PRODUCT
XDC_URL_SUFFIX_PRODUCT_PRICE
XDC_URL_SUFFIX_PRINT_OPTION
XDC_URL_SUFFIX_PRINT_OPTION_PRICE
XDC_URL_SUFFIX_STOCK
```
