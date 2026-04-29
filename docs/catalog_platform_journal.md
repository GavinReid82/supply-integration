# supply_integration — Learning Journal

A running record of what I built, what I learned, and what went wrong. Written in
chronological order.

**Project:** Standalone ELT pipeline — Makito API → AWS S3 → dbt/DuckDB → Streamlit
**GitHub:** https://github.com/GavinReid82/supply-integration

---

## 24 April 2026 — Week 1: Full Pipeline Build (Days 1–4)

**Context:** First week after deciding to build a portfolio project. I'm being made
redundant from Helloprint and want to rebuild a simplified, standalone version of the
supply_integration platform I worked on there — using a real supplier API (Makito),
AWS S3, dbt, DuckDB, and Streamlit, all containerised in Docker.

### What I Built

- AWS S3 bucket (`supply-integration`, eu-south-2) and IAM user for programmatic access
- Python extractor: fetches product catalogue, prices, and stock from Makito's XML API
  and uploads raw Parquet files to S3
- dbt + DuckDB transformation layer: 5 staging models + 4 mart tables
- Streamlit UI: product catalogue with sidebar filters, product images, tiered pricing,
  and variants
- Git repository pushed to GitHub: github.com/GavinReid82/supply-integration
- Learning docs for each day (Days 1–4) stored in `docs/`

### Key Things I Learned

**AWS and cloud storage:**
- The difference between root account and IAM users — always use IAM, never root for
  day-to-day work
- What the principle of least privilege means in practice
- Access key pairs: Access Key ID (not secret) + Secret Access Key (shown once only)
- S3 is object storage — paths look like folders but are just long filenames
- Newer AWS regions (eu-south-2) need explicit endpoint configuration in tools like DuckDB

**Python and extraction:**
- Virtual environments isolate project dependencies — activate with
  `source .venv/bin/activate`
- Credentials go in `.env`, never in code or git
- Exponential backoff retry logic: why you wait longer between each retry
- XML parsing with ElementTree: `fromstring`, `findall`, `find`, `.text`
- Why I split products/variants/images into three DataFrames (different granularities)
- Parquet vs CSV: columnar, compressed, preserves types, readable by DuckDB from S3

**dbt and DuckDB:**
- dbt models are just SELECT statements — dbt handles CREATE TABLE/VIEW
- `{{ ref() }}` builds a dependency graph so models run in the right order
- Staging layer: rename, cast, deduplicate. Mart layer: join, aggregate, serve.
- `QUALIFY ROW_NUMBER() OVER (PARTITION BY ...)` for deduplication
- Unpivoting wide price data (4 columns) to tall rows with UNION ALL
- `try_cast` vs `cast` — `try_cast` returns NULL on failure, `cast` raises an error
- LEFT JOIN is safer than INNER JOIN in marts — does not silently drop products with
  missing data
- Staging models are views (live S3 queries). Marts are tables (written to DuckDB).
  UI reads marts only.

**Streamlit and the UI:**
- Streamlit reruns the whole script on every user interaction
- `@st.cache_data` caches query results so DuckDB is not hit on every rerun
- `try/finally` on DuckDB connections ensures they close and release file locks
- DuckDB is single-writer — stop the UI before running the pipeline
- `sys.executable` is the right way to derive co-installed tool paths (e.g. dbt)

**Git and GitHub:**
- git is the tool, GitHub is the hosting service
- `.gitignore` must include `.env`, `.venv/`, `data/` — never commit credentials
- Commit messages should explain WHY, not WHAT
- GitHub PATs replace passwords for command-line access — revoke immediately if exposed

### Issues I Hit and How I Fixed Them

1. **Product endpoint structure wrong:** I assumed the Makito product API returned a
   manifest (list of file URLs) based on the Helloprint production code. It actually
   returns the full catalogue XML directly. Diagnosed by printing the raw API response.
   Rewrote the parser.

2. **`_parse_namespace` missing after rewrite:** When rewriting `endpoints.py`, I
   accidentally deleted a helper function still used by `fetch_price` and `fetch_stock`.
   Caused a `NameError`. Fixed by adding it back. Lesson: test after rewrites.

3. **DuckDB path was a Docker path:** `profiles.yml` had `/app/data/supply_integration.duckdb`.
   Fixed by using `env_var()` with a local fallback.

4. **DuckDB S3 HTTP 400 error:** DuckDB's httpfs uses the global S3 endpoint by default.
   The eu-south-2 region returns HTTP 400 from the global endpoint. Fixed by adding
   `s3_endpoint: s3.eu-south-2.amazonaws.com` to `profiles.yml`.

5. **Column names were DLT-style:** The staging model used `categories__category_ref_1`
   (DLT's double-underscore naming). My extractor produces `category_ref_1`. Updated
   the model to match.

6. **3 duplicate product refs:** The uniqueness dbt test failed — 3 product refs
   appeared more than once in Makito's source data. Fixed with
   `QUALIFY ROW_NUMBER() OVER (PARTITION BY ref ORDER BY ref) = 1` in the staging model.

7. **Staging view queried from UI caused S3 error:** The UI originally queried
   `stg_mko_prices` (a view with `read_parquet('s3://...')`). The plain DuckDB
   connection does not have S3 configured. Fixed by materialising mart tables.

8. **DuckDB lock conflict between UI and pipeline:** Streamlit held an open DuckDB
   connection while I ran the pipeline. Fixed with `try/finally` to close connections
   immediately. Had to kill the lingering process.

9. **dbt not found in subprocess:** `subprocess.run(['dbt', ...])` failed because dbt
   is in the venv, not on the system PATH. Fixed by deriving the dbt path from
   `sys.executable`.

10. **Personal Access Token exposed:** Pasted the GitHub PAT into the username field
    instead of the password field when pushing. Revoked immediately and generated a new
    one.

### Current Project State (end of Week 1)

- Pipeline runs end-to-end: `python run_pipeline.py` extracts from Makito, uploads to
  S3, runs dbt, runs tests
- 7 dbt models (5 staging views + 4 mart tables), 8 tests all passing
- Streamlit UI running at localhost:8501 with product images, tiered pricing, variant
  details
- Code on GitHub: github.com/GavinReid82/supply-integration
- Docker containerisation not yet done

---

## 27 April 2026 — Print Options, Order Configurator & Carrier Pricing

### What I Built

Extended the extraction layer with two new Makito API endpoints: `ItemPrintingFile.php`
(print options) and `PrintJobsPrices.php` (print technique prices). Added `fetch_print()`
and `fetch_print_price()` to `extractor/endpoints.py` following the same XML parsing
pattern already used for products, prices, and stock.

`fetch_print()` parses the product → printjob → area hierarchy and flattens it to one
row per product/technique/area combination. Extracted 24,827 rows covering print
techniques and areas across the full product range.

`fetch_print_price()` parses a global price list of 128 print techniques, each with up
to 7 quantity-tiered prices plus a fixed cliché setup cost and minimum job cost.

Added two new dbt staging views (`stg_mko_print_options`, `stg_mko_print_prices`) reading
from the new S3 Parquet files, plus two mart pass-through tables (`mko_print_options`,
`mko_print_prices`) so Streamlit can query them without needing live S3 access.

Created two dbt seeds: `carriers.csv` (the 3 Makito carriers, extracted from an internal
Helloprint BigQuery table) and `mko_carrier_zones.csv` (72 rows mapping 24 destination
countries across 4 shipping zones to carrier prices). Added `dbt seed` as the first
transform step.

Converted the Streamlit app to multipage structure. The existing catalogue gains a
"Configure Order →" button that saves the selected product to session state and switches
pages. The new page (`ui/pages/2_Configure_Order.py`) implements the full Bespoke order
configuration flow: select variant → enter quantity → select print option(s) → select
destination country → select carrier → see price breakdown → copy supplier reference.

### Concepts I Learned / Consolidated

- **dbt seeds:** CSV files in `dbt_project/seeds/` are loaded as tables via `dbt seed`.
  Ideal for small static reference datasets like carrier lists that do not need to live
  in S3.
- **Streamlit multipage apps:** pages live in a `pages/` subdirectory. `st.switch_page()`
  navigates programmatically; `st.session_state` persists data across page switches.
- **Print pricing model:** two-part cost — fixed cliché (setup) cost per run + variable
  per-unit cost subject to a minimum job cost floor.
- **Supplier reference format (MKO):** `variant_id__teccode#areacode` with extra
  `__teccode#areacode` segments for each additional print area.

### Issues Encountered

1. Empty `<printjobs/>` elements in the print XML — correctly produce zero rows and
   are filtered naturally by `WHERE teccode IS NOT NULL AND areacode IS NOT NULL`.
2. Print price tiers use `amountunder` as an upper bound (not a minimum). Tiers with
   `amountunder=0` are unused placeholders, filtered in staging. UI falls back to the
   last tier if quantity exceeds all thresholds.
3. `run_pipeline.py` already had `fetch_print`/`fetch_print_price` imports written in
   anticipation — the functions just did not exist yet in `endpoints.py`.

### Current Project State (end of 27 April, session 1)

- Full pipeline: products, variants, prices, stock, print options, print prices,
  carriers, carrier zones → S3 → dbt (11 models + 2 seeds) → DuckDB → Streamlit (2 pages)
- Bespoke order configurator functional
- All 17 dbt tests passing

---

## 27 April 2026 — Multi-Supplier Architecture Refactor & Category Management UI

### Overview

This session extended the previous day's work in two phases: a structural refactor to
support multiple suppliers, and a new Category Management UI replacing the Google Sheets
PCM workflow.

### Architecture Refactor

The codebase had been entirely MKO-specific. I used the `/improve-codebase-architecture`
skill to surface five deepening opportunities, then implemented all five.

**Extractor layer:** A new `SupplierExtractor` abstract base class with a single
`run(date)` method, and a `SupplierConfig` dataclass. `MkoExtractor` is the first
concrete adapter. Adding XDC means writing `XdcExtractor(SupplierExtractor)` and
registering it in `run_pipeline.py` — nothing else changes.

**dbt intermediate layer:** Six new `int_mko_*` views sit between staging and marts.
Each adds `'mko' as supplier` and passes everything through. This is where a future
`int_xdc_*` layer would slot in — the canonical marts do not care what shape the XDC
staging models have, as long as the intermediate models produce the right columns.

**Canonical mart models:** `catalog`, `variants`, `prices`, `print_options`, and
`print_prices` are now supplier-agnostic UNION tables. The old `mko_catalog`,
`mko_variants` etc. become simple `WHERE supplier = 'mko'` filters on the canonical
tables, preserving backwards compatibility.

**Shared UI modules:** `ui/db.py` provides a single `query()` function. `ui/supplier_reference.py`
encapsulates the `build()` dispatcher — MKO and XDC have completely different
supplier_reference formats, and this logic must live in one place.

Result: 22 dbt models (12 views, 10 tables), all 17 tests passing.

A gotcha: dbt's Jinja parser processes `{{ ref() }}` everywhere in a SQL file,
including inside comments. Any `{{ ref('int_xdc_...') }}` in a comment causes a compile
error because the model does not exist yet. Comments must use plain English only.

### Category Management UI

The catman team selects products per PCM template in a Google Sheet, typing slugs,
quantity codes, and print dimensions — all of which can be automated. I built a
Streamlit UI that replaces this.

- **Landing page** separates the two user journeys (Bespoke and Category Management)
- **Template selector** drives quantity code defaults from a YAML config
  (`business_logic/quantity_codes.yaml`) derived from the live PCM data — 33 MKO
  templates, each with the most common quantity code used by the current selection
- **Editable product table** (`st.data_editor`) with auto-generated slugs and
  pre-filled quantity codes; per-product session state keys persist edits across filter
  changes
- **Print options panel** shows all available techniques and areas (max dimensions
  pre-filled from the `print_options` table); "No print" always available for sample
  configurations
- **Validated export** blocks download until every selected product has a quantity code
  and at least one print option; produces a CSV one row per product × print option

The key state management pattern: Streamlit widget state (managed by `key`) and
application state (managed by `st.session_state`) are separate. For edits that must
survive filter changes, values must be written explicitly to `st.session_state` after
each `data_editor` render — the widget cannot be trusted to hold them across resets.

### Current Project State

The pipeline now covers products, variants, prices, stock, print options, print prices,
carriers, and carrier zones (22 dbt models + 2 seeds, 17 tests). The Streamlit app has
three pages: a landing page, a Bespoke catalogue with Configure Order, and a Category
Management tool.

The architecture supports adding a second supplier by writing one new extractor adapter,
one new set of intermediate dbt models, and one new supplier reference builder. The
canonical marts, the UI, and `run_pipeline.py` require no changes.

### Next Areas to Consider

- Dockerfile and containerisation
- Airflow DAG to schedule the pipeline
- Unit tests for the extractor layer
- Adding XDC as a second supplier to validate the architecture in practice
- CI/CD with GitHub Actions

---

## 28 April 2026 — README, Docker Hardening, and Unit Tests

**Focus:** Engineering quality — documentation, containerisation, and the test suite.

The pipeline and UI have been functionally complete since 27 April. Today I turned
attention to the things that make the project defensible in an interview: a clear
README that explains the architecture to someone arriving cold, a containerisation
setup that actually works cleanly, and a unit test suite that proves the extraction
logic is correct without requiring API credentials or AWS access.

**README.** Written from scratch. A review surfaced a factual error in the "Adding a
new supplier" section — the step of updating the canonical mart SQL files (to add
`UNION ALL` branches for the new intermediate models) had been omitted. That is a
real change required when XDC is added, so the README now correctly lists five steps.

**Docker.** The `Dockerfile` and `docker-compose.yml` were already committed. On
review I added a `.dockerignore` — without it `COPY . .` would have included `.env`
(credentials), `.venv/` (hundreds of MB), and `data/` (the DuckDB file). The
`docker-compose.yml` correctly uses `condition: service_completed_successfully` for
the UI's dependency on the pipeline, which is the right pattern for a single-writer
database.

**Unit tests.** 28 tests across four files, all passing in under a second. Every
test mocks the I/O boundary — either the HTTP client or the S3 client — so the suite
runs without network access or AWS credentials. The tests cover all five MKO endpoint
parsers, the retry client, the S3 loader (including verifying the uploaded bytes are
valid Parquet), and the `MkoExtractor` orchestration logic (verifying the correct
date-partitioned S3 keys are used).

A side fix: the project venv had been created when the directory was named
`supply_integration/`. After the rename to `catalog_data_platform/`, the `pip`
shebang was broken. The venv was recreated cleanly with `python3 -m venv .venv --clear`.

### Current Project State

| Component | Status |
|---|---|
| AWS S3 + IAM | Done |
| Python extractor (MKO — 5 feeds) | Done |
| dbt staging + intermediate + canonical marts | Done |
| dbt seeds (carriers + carrier zones) | Done |
| SupplierExtractor ABC + MkoExtractor | Done |
| Streamlit UI (3 pages + landing) | Done |
| Dockerfile + Docker Compose | Done |
| README | Done |
| Unit tests (extractor layer, 28 tests) | Done |
| XDC as second supplier | Planned |
| CI/CD with GitHub Actions | Planned |
| Airflow DAG | Planned |

---

## 28 April 2026 — UI Navigation, Print Colour Data Model, and Shopping Basket

**Focus:** Refining both UI workflows and fixing data model issues surfaced by real
usage.

This session produced no new pipeline stages or API endpoints. The focus was entirely
on making the existing Bespoke and Category Management tools work correctly and look
credible.

### Navigation

Replaced Streamlit's auto-generated sidebar with `st.navigation(position="hidden")` and
explicit `st.sidebar.page_link()` calls. This hides the Configure Order page from the
sidebar (it is only reachable via the Catalog page) while still keeping it registered
so `st.switch_page()` resolves it. `st.set_page_config()` now lives only in `app.py`.

### Print colour data model

The `technique_name` field in `print_options` had `(FULLCOLOR)` embedded as a text
suffix. This is a data modelling mistake — colour type is a separate fact from
technique name. I derived a new `print_color BIGINT` column: `-1` for full colour, the
spot-colour count otherwise. The technique names are cleaned with `REGEXP_REPLACE`.

A subtle dbt/SQL point: a column alias defined in the same SELECT list is not visible
to other expressions in that list. The CASE WHEN that produces `print_color` had to
reference the original `technique_name` column, not the cleaned alias.

### Variant deduplication

Variants were appearing twice in the UI. The cause: the staging model reads from an
S3 glob matching all date-partitioned directories. After two pipeline runs, every row
was doubled. Fixed with `QUALIFY ROW_NUMBER() OVER (PARTITION BY product_ref, matnr
ORDER BY 1) = 1` in `int_mko_variants.sql`.

### Shopping basket

Users can now add configured products to a basket that persists across page switches,
then export all items as a CSV. The implementation uses `st.session_state` (browser
session scope — no external storage needed) and a new `ui/basket.py` shared module
imported by both the Catalog and Configure Order pages. Prices are captured at add
time, not recalculated on display.

### Catman print options

Restructured from a flat list to an area-first hierarchy: select a print position first,
then choose techniques beneath it. Techniques are indented using `st.columns([1, 12])`.
The quantity code input is now also available in the print options panel without
needing to scroll back up to the products table.

### Current Project State (end of 28 April, session 2)

| Component | Status |
|---|---|
| AWS S3 + IAM | Done |
| Python extractor (MKO — 5 feeds) | Done |
| dbt staging + intermediate + canonical marts | Done |
| dbt seeds (carriers + carrier zones) | Done |
| SupplierExtractor ABC + MkoExtractor | Done |
| Streamlit UI (4 pages — Home, Catalog, Configure Order, Catman) | Done |
| Shopping basket (session state, CSV export) | Done |
| Dockerfile + Docker Compose | Done |
| README | Done |
| Unit tests (extractor layer, 28 tests) | Done |
| XDC as second supplier | Done |
| CI/CD with GitHub Actions | Planned |
| Airflow DAG | Planned |

---

## 29 April 2026 — XDC as a Second Supplier

**Focus:** Validating the multi-supplier architecture by adding Xindao (XDC) as a real second supplier.

This session proved that the architecture designed on 27 April works in practice. Adding XDC required exactly the five changes described in the README: one new extractor adapter, five new staging models, six new intermediate models, conditional mart unions, and one new supplier reference builder. `run_pipeline.py`, the UI pages, and the canonical mart schemas required no changes.

### What I Built

**`extractor/xdc.py`** — `XdcExtractor(SupplierExtractor)`. Unlike MKO, XDC provides data as XLSX files at authenticated full URLs rather than XML. `get_with_retry()` fetches the raw bytes; `pd.read_excel(io.BytesIO(raw))` parses them; column headers are normalised (lowercase, spaces → underscores) before upload. The five feeds mirror the MKO structure: product (contains both product and variant data in one file), product_price, print_option, print_option_price, and stock.

**Staging models** — Five `stg_xdc_*` models. XDC has no separate product table: the product XLSX has one row per colour/size variant, with product-level fields repeated across all variants. Dimensions arrive in centimetres (×10 for mm) and weight in grams (/1000 for kg).

**Intermediate models** — Six `int_xdc_*` models. `int_xdc_products.sql` *derives* a product table from the variant feed using `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY variant_id) = 1` — the lexically-first variant represents the product. `int_xdc_variants.sql` implements two-tier availability logic: a variant is available if its `productlifecycle` is not `'Outlet'`, or if its stock exceeds a per-subcategory threshold from the `xdc_availability_thresholds` seed.

**Canonical mart models** — Updated to use conditional Jinja (`{% if env_var('XDC_BASE_URL', '') != '' %} union all ... {% endif %}`) instead of static `UNION ALL`. A `dbt run` without XDC credentials builds MKO-only cleanly. All XDC models carry `{{ config(tags=["xdc"]) }}` so `dbt run --exclude tag:xdc` skips them explicitly.

**`run_pipeline.py`** — XDC is opt-in. The `XdcExtractor` and its config are only loaded when `XDC_BASE_URL` is set in the environment. The extract loop remains unchanged: `for config in SUPPLIERS: EXTRACTOR_REGISTRY[config.name](config, BUCKET).run(TODAY)`.

**`supplier_reference.py`** — `_xdc()` builder added. XDC currently uses the same reference format as MKO (`variant_id__technique#position`), so the implementation is a thin wrapper.

**New seeds** — `pcm_templates.csv` and `xdc_availability_thresholds.csv`. The thresholds table defines per-subcategory stock minimums for Outlet-lifecycle products: Water bottles 250, Plastic pens 500, Bags 50, etc.

### Key Concepts

- **Deriving a product table from variants:** XDC is structured around colour/size combinations, not discrete products. Using rank-1-per-product is a standard technique for flattening a variant-first schema into the canonical product shape without losing any data.
- **Conditional dbt Jinja:** `{% if env_var(...) %}` is resolved at compile time — the generated SQL either includes or excludes the XDC branch before execution. This is cleaner than Python-side branching; the SQL itself changes shape based on configuration.
- **dbt tags:** `{{ config(tags=["xdc"]) }}` enables `dbt run --exclude tag:xdc` for MKO-only builds — critical for developing without XDC credentials and for faster iteration.
- **Availability thresholds as a seed:** per-subcategory stock floors are editorial decisions that will change. A CSV seed is version-controlled, reviewable, and editable without touching SQL.

### Issues Encountered

1. XDC column names include spaces and mixed case in the raw XLSX. Normalised on read: `[c.strip().lower().replace(" ", "_") for c in df.columns]`.
2. XDC has no dedicated product table — `product_id` (`modelcode`) is shared across all variants of a product. The intermediate layer derives the product row from the lexically-first variant.

### Current Project State

| Component | Status |
|---|---|
| AWS S3 + IAM | Done |
| Python extractor (MKO — 5 XML feeds) | Done |
| Python extractor (XDC — 5 XLSX feeds) | Done |
| dbt staging layer (MKO: 6 models, XDC: 5 models) | Done |
| dbt intermediate layer (MKO: 6 models, XDC: 6 models) | Done |
| dbt canonical mart models (conditional Jinja unions) | Done |
| dbt seeds (carriers, carrier zones, pcm_templates, xdc_availability_thresholds) | Done |
| SupplierExtractor ABC + MkoExtractor + XdcExtractor | Done |
| Shared UI modules (db.py, supplier_reference.py, basket.py) | Done |
| Streamlit UI (4 pages — Home, Catalog, Configure Order, Catman) | Done |
| Shopping basket (session state, CSV export) | Done |
| Dockerfile + Docker Compose | Done |
| README | Done |
| Unit tests (extractor layer, 28 tests) | Done |
| XDC supplier reference builder | Done |
| Airflow DAG (replace run_pipeline.py) | Not started |
| CI/CD with GitHub Actions | Not started |
