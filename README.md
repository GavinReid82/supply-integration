# supply_integration

A multi-supplier ELT pipeline and internal tooling platform for promotional goods catalogue management.

Extracts product data from supplier APIs, stores raw files in AWS S3, transforms with dbt + DuckDB, and serves two internal workflows via a Streamlit UI: **Bespoke** (one-off order configuration) and **Category Management** (PCM export for website catalogues).

Built as a portfolio project mirroring the supply_integration platform at Helloprint, using real API access and no proprietary data.

---

## Architecture

```
Supplier APIs (MKO/Makito, XDC/Xindao, ...)
  ↓
SupplierExtractor adapters       extractor/
  ↓
AWS S3  (Parquet, date-partitioned, per-supplier prefix)
  ↓
dbt + DuckDB                     dbt_project/models/
  staging  →  intermediate  →  canonical marts
  ↓
Streamlit UI                     ui/
  Landing · Catalogue · Configure Order · Category Management
```

---

## Features

### Extraction layer

- **MKO:** fetches five XML feeds (product catalogue, tiered pricing, stock levels, print options, print technique prices)
- **XDC:** fetches five XLSX feeds (product/variants in one file, pricing, print options, print prices, stock); normalises headers on read
- Uploads raw data to S3 as date-partitioned Parquet files
- `SupplierExtractor` abstract base class — adding a new supplier requires one new adapter class, zero changes to the orchestrator

### dbt transformation layer

33 models across three layers, all targeting DuckDB via the `dbt-duckdb` adapter:

| Layer | Type | Purpose |
|---|---|---|
| `stg_mko_*` (6 models) | view | Type casting and light cleaning from MKO S3 Parquet |
| `stg_xdc_*` (5 models) | view | Type casting and unit conversion from XDC S3 Parquet |
| `int_mko_*` (6 models) | view | Normalise to canonical shape, add `supplier='mko'` |
| `int_xdc_*` (6 models) | view | Normalise to canonical shape, add `supplier='xdc'`; `int_xdc_products` derived from variants |
| `catalog`, `variants`, `prices`, `print_options`, `print_prices` | table | Canonical, supplier-agnostic (conditional Jinja unions — XDC active when `XDC_BASE_URL` is set) |
| `mko_*` (5 models) | table | Supplier-filtered views of the canonical tables |

Seeds: `carriers.csv`, `mko_carrier_zones.csv`, `pcm_templates.csv`, `xdc_availability_thresholds.csv`. XDC models carry `{{ config(tags=["xdc"]) }}` — use `dbt run --exclude tag:xdc` for MKO-only builds.

DuckDB reads S3 Parquet directly via the `httpfs` extension — no local copy of raw data.

### Streamlit UI

| Page | Purpose |
|---|---|
| Landing | Routes to Bespoke or Category Management |
| Catalogue | Browse products with category/price filters, images, tiered pricing, variant details |
| Configure Order | 5-step Bespoke flow: product → variant → quantity → print options → carrier → supplier reference |
| Category Management | Select products by PCM template, auto-generate slugs, assign quantity codes, configure print options, export CSV |

---

## Stack

- **Python 3.11** — extraction and orchestration
- **boto3** — S3 uploads
- **requests + tenacity** — HTTP with retry and exponential backoff
- **dbt-duckdb 1.8** — transformation layer
- **DuckDB** — analytical engine, reads Parquet from S3 via httpfs
- **Streamlit** — internal UI
- **PyYAML** — business logic config
- **Docker Compose** — containerised runtime

---

## Project structure

```
catalog_data_platform/
├── run_pipeline.py               # extract → dbt seed/run/test
├── extractor/
│   ├── base.py                   # SupplierConfig dataclass + SupplierExtractor ABC
│   ├── mko.py                    # MkoExtractor (XML feeds)
│   ├── xdc.py                    # XdcExtractor (XLSX feeds)
│   ├── endpoints.py              # MKO fetch_* functions
│   ├── client.py                 # HTTP retry logic
│   └── loader.py                 # S3 upload
├── dbt_project/
│   ├── models/
│   │   ├── staging/              # stg_mko_*.sql (6), stg_xdc_*.sql (5)
│   │   ├── intermediate/         # int_mko_*.sql (6), int_xdc_*.sql (6)
│   │   └── marts/                # canonical (5) + supplier-specific (5)
│   └── seeds/                    # carriers, mko_carrier_zones, pcm_templates, xdc_availability_thresholds
├── ui/
│   ├── app.py                    # st.navigation router + sidebar page_links
│   ├── db.py                     # shared query() function
│   ├── supplier_reference.py     # build() dispatcher — MKO + XDC
│   ├── basket.py                 # session state basket
│   └── pages/
│       ├── 0_Home.py             # landing page
│       ├── 1_Catalog.py
│       ├── 2_Configure_Order.py
│       └── 3_Catman.py
└── business_logic/
    └── quantity_codes.yaml       # 33 MKO PCM template quantity code defaults
```

---

## Running locally

**1. Set up credentials**

```bash
cp .env.example .env
# Fill in AWS credentials, S3 bucket, and MKO API URLs
```

Required variables:

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
DUCKDB_PATH          # optional, defaults to data/catalog_data_platform.duckdb
```

**2. Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Run the pipeline**

```bash
python run_pipeline.py
```

This extracts all five MKO feeds, uploads to S3, then runs `dbt seed && dbt run && dbt test`.

**4. Launch the UI**

```bash
streamlit run ui/app.py
```

Open [http://localhost:8501](http://localhost:8501).

**Note:** DuckDB is single-writer. Stop the UI before re-running the pipeline.

---

## Running with Docker Compose

```bash
cp .env.example .env   # fill in credentials
docker compose up
```

The `pipeline` service runs `run_pipeline.py` first. The `ui` service starts after and serves Streamlit on port 8501.

---

## Adding a new supplier

The architecture is designed so that adding supplier XYZ requires changes in exactly five places and nowhere else:

1. `extractor/xyz.py` — implement `XyzExtractor(SupplierExtractor)` with a `run(date)` method
2. `dbt_project/models/staging/stg_xyz_*.sql` — type-cast the raw S3 feeds
3. `dbt_project/models/intermediate/int_xyz_*.sql` — normalise to canonical shape, add `supplier = 'xyz'`
4. `dbt_project/models/marts/*.sql` — add a conditional Jinja union branch (`{% if env_var('XYZ_BASE_URL', '') != '' %}`) to each canonical mart
5. `ui/supplier_reference.py` — add an `_xyz()` case to the `build()` dispatcher

`run_pipeline.py` and all UI pages require no changes. XDC demonstrates this pattern end-to-end.

---

## Status

| Component | Status |
|---|---|
| AWS S3 + IAM | Done |
| Python extractor (MKO — 5 XML feeds) | Done |
| Python extractor (XDC — 5 XLSX feeds) | Done |
| dbt staging layer (MKO: 6 models, XDC: 5 models) | Done |
| dbt intermediate layer (MKO: 6 models, XDC: 6 models) | Done |
| dbt canonical marts (5 tables, conditional Jinja unions) | Done |
| dbt seeds (carriers, carrier zones, pcm_templates, xdc_availability_thresholds) | Done |
| SupplierExtractor ABC + MkoExtractor + XdcExtractor | Done |
| Streamlit UI (4 pages + landing) | Done |
| Shopping basket (session state, CSV export) | Done |
| Dockerfile + Docker Compose | Done |
| Unit tests for extractor layer (28 tests) | Done |
| Airflow DAG | Planned |
| CI/CD with GitHub Actions | Planned |
