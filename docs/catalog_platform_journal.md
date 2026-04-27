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
