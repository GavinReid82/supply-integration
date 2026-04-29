# dbt Fundamentals

## Overview

dbt (data build tool) is a framework for writing the **T** in ELT — the Transform step.
You write SQL `SELECT` statements; dbt handles the `CREATE TABLE` / `CREATE VIEW`
scaffolding, runs them in the right order, and tests the results.

dbt does **not** move data. It does not extract from APIs or load from files. It runs
SQL against a database you already have.

## Everyday analogy

Think of a recipe book where every recipe references ingredients from other recipes:
"For the sauce, use the base from Recipe 3." dbt works the same way — each model
references other models, and dbt figures out which order to cook everything in.

---

## In the project

### Models

A dbt model is a `.sql` file containing a single `SELECT` statement. That is the entire
file — no `CREATE`, no `INSERT`, no `DROP`. dbt wraps it automatically.

```sql
-- models/staging/stg_mko_products.sql
SELECT
    ref         AS product_ref,
    name        AS product_name,
    try_cast(item_weight AS DECIMAL(10, 4)) AS item_weight_kg
FROM read_parquet('s3://supply-integration/mko/raw/product/*/products.parquet')
```

Run `dbt run` and dbt creates either a view or a table from this query, depending on the
configured materialisation.

### `{{ ref() }}` — the dependency graph

When one model uses data from another, you reference it with `{{ ref('model_name') }}`
instead of the table name directly:

```sql
-- models/marts/catalog.sql
SELECT p.*, pr.min_unit_price, s.total_stock_qty
FROM {{ ref('int_mko_products') }}   p
LEFT JOIN {{ ref('int_mko_prices') }} pr ON p.product_ref = pr.product_ref
LEFT JOIN {{ ref('int_mko_stock') }}  s  ON p.product_ref = s.product_ref
```

**Why not just write the table name?**

Two reasons:

1. **dbt builds a dependency graph.** When it sees `{{ ref('int_mko_products') }}` inside
   `catalog.sql`, it knows `catalog` depends on `int_mko_products`, and will run
   `int_mko_products` first. You never manually specify run order.

2. **Portability.** `{{ ref() }}` resolves to the correct schema and table name for
   whatever environment (dev/prod) you are running in. The underlying table name might
   be `dev_gavin.int_mko_products` in development and `prod.int_mko_products` in
   production — `{{ ref() }}` handles this automatically.

**Jinja templating:** The `{{ }}` syntax is Jinja — a templating language. dbt uses Jinja to let you add
logic and variables to SQL files. `{{ ref('x') }}` is a function call that dbt evaluates
before running the SQL. Other common uses:
- `{{ env_var('AWS_ACCESS_KEY_ID') }}` — reads an environment variable
- `{{ config(materialized='table') }}` — sets model configuration inline

**Important:** dbt processes Jinja everywhere in the file, including inside SQL comments.
A reference like `-- union with {{ ref('int_xdc_variants') }}` would cause a compile
error if `int_xdc_variants` does not exist. Use plain English in comments.

### Materialisation

Materialisation controls what dbt creates when it runs a model.

| Materialisation | What dbt creates | Data written to disk? | Use for |
|---|---|---|---|
| `view` | A SQL view (saved query) | No | Staging models — always fresh, no storage cost |
| `table` | A physical table | Yes | Mart models — fast to query, no live S3 reads |
| `incremental` | Appends/updates a table | Yes (partially) | High-volume fact tables |
| `ephemeral` | A CTE injected inline | No | Intermediate steps you never query directly |

Set materialisation globally in `dbt_project.yml`:

```yaml
models:
  supply_integration:
    staging:
      +materialized: view    # all staging/ models are views
    marts:
      +materialized: table   # all marts/ models are tables
```

Or override per-model at the top of the file:

```sql
{{ config(materialized='table') }}
SELECT ...
```

**Why views for staging?** A view is a saved `SELECT` query. Every time you query it,
DuckDB re-runs the SQL and reads the latest data from S3. No extra storage used, always
fresh.

**Why tables for marts?** The UI queries mart tables on every page load. If the mart
were a view, every UI query would re-read the Parquet files from S3 — slow and expensive.
Writing the mart to a DuckDB table means the UI reads local DuckDB, which is orders of
magnitude faster.

### The three-layer architecture

This project uses the standard dbt layering pattern: staging → intermediate → marts.

```
S3 Parquet files
    ↓
staging (views)        raw data, renamed columns, type casts, dedup
    ↓
intermediate (views)   normalise to canonical shape, add supplier column
    ↓
marts (tables)         supplier-agnostic union tables, queried by the UI
```

**Staging layer** — one model per source table. Job: rename, cast, clean. No joins. No
business logic. If the source column name changes, you update one staging model.
Everything downstream is insulated.

**Intermediate layer** — adds the `supplier` column and normalises column names to match
the canonical mart schema. This is where supplier-specific quirks are ironed out.

```sql
-- int_mko_variants.sql
SELECT
    'mko'        AS supplier,
    product_ref,
    matnr,
    colour_name,
    colour_code,
    size
FROM {{ ref('stg_mko_variants') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY product_ref, matnr ORDER BY 1) = 1
```

When XDC is added, `int_xdc_variants.sql` will produce the same columns. The canonical
`variants` mart can then `UNION ALL` both intermediate models without knowing anything
about either supplier's source format.

**Marts layer** — supplier-agnostic tables. The UI queries mart tables only — it never
touches staging or intermediate.

### dbt Seeds

Seeds are CSV files in `dbt_project/seeds/`. Running `dbt seed` loads them as tables.
They are for small, static reference data that does not come from an API.

In this project:

```
seeds/
├── carriers.csv        — 3 MKO carrier names and IDs
└── mko_carrier_zones.csv  — 72 rows: 24 countries × 3 carriers with prices
```

Seeds are referenced with `{{ ref('carriers') }}` just like models.

**When to use seeds vs models:**
- Seeds: static lookup tables (country codes, carrier lists, product categories)
- Models: anything derived from the pipeline data

### dbt Tests

Tests are data quality checks that run after `dbt run`. They live in `schema.yml` files.

```yaml
# models/marts/schema.yml
models:
  - name: catalog
    columns:
      - name: product_ref
        tests:
          - not_null
          - unique
```

Each test compiles to a query. If the query returns any rows, the test fails:

```sql
-- not_null compiles to:
SELECT COUNT(*) FROM catalog WHERE product_ref IS NULL
-- fails if result > 0

-- unique compiles to:
SELECT product_ref FROM catalog GROUP BY product_ref HAVING COUNT(*) > 1
-- fails if any rows returned
```

**Tests failing is information, not failure.** When the `unique` test on `product_ref`
first failed, it revealed that Makito's source data had 3 duplicate product refs. That
led to adding `QUALIFY ROW_NUMBER()` deduplication in staging. Without the test, those
duplicates would have silently entered the catalog.

### Project file structure

```
dbt_project/
├── dbt_project.yml        — project name, version, model configurations
├── profiles.yml           — database connection (DuckDB path, S3 credentials)
├── seeds/
│   ├── carriers.csv
│   └── mko_carrier_zones.csv
└── models/
    ├── staging/
    │   ├── schema.yml          — source definitions and tests
    │   ├── stg_mko_products.sql
    │   ├── stg_mko_variants.sql
    │   ├── stg_mko_prices.sql
    │   ├── stg_mko_stock.sql
    │   ├── stg_mko_print_options.sql
    │   └── stg_mko_print_prices.sql
    ├── intermediate/
    │   ├── int_mko_products.sql
    │   ├── int_mko_variants.sql   ← QUALIFY dedup here
    │   ├── int_mko_prices.sql
    │   ├── int_mko_stock.sql
    │   ├── int_mko_print_options.sql  ← print_color derived here
    │   └── int_mko_print_prices.sql
    └── marts/
        ├── schema.yml          — mart tests
        ├── catalog.sql         — UNION of all int_*_products
        ├── variants.sql        — UNION of all int_*_variants
        ├── prices.sql
        ├── print_options.sql
        ├── print_prices.sql
        ├── mko_catalog.sql     — WHERE supplier = 'mko'
        └── mko_variants.sql
```

---

## Glossary

| Term | Meaning |
|---|---|
| Model | A `.sql` file containing a single `SELECT`; dbt creates a table or view from it |
| `{{ ref() }}` | Jinja function that references another model and builds the dependency graph |
| Materialisation | Whether dbt creates a view, table, or other object from a model |
| Staging | First transformation layer — rename, cast, clean; one model per source table |
| Intermediate | Second layer — normalise to canonical shape; add supplier column |
| Mart | Final layer — joined, business-ready tables that the UI queries |
| Seed | A CSV file loaded as a table via `dbt seed`; for static reference data |
| Test | A data quality check (`not_null`, `unique`) that runs after models |
| Jinja | Templating language used inside dbt SQL files for `{{ ref() }}`, `{{ env_var() }}` etc. |
| Dependency graph | The directed graph of which models depend on which; dbt resolves run order from this |
| `dbt run --select` | Run only specific models (supports model names, layer names, `+` for dependencies) |

---

## Cheat sheet

```sql
-- Reference another model (builds dependency graph)
FROM {{ ref('model_name') }}

-- Read env var (used in profiles.yml)
{{ env_var('MY_VAR', 'default_value') }}

-- Override materialisation per model
{{ config(materialized='table') }}

-- Dedup pattern (used in staging + intermediate)
QUALIFY ROW_NUMBER() OVER (PARTITION BY id_col ORDER BY any_col) = 1

-- Typical staging model structure
SELECT
    source_col   AS canonical_col,
    try_cast(num_col AS INTEGER) AS num_col
FROM read_parquet('s3://bucket/prefix/*/file.parquet')
QUALIFY ROW_NUMBER() OVER (PARTITION BY id_col ORDER BY 1) = 1

-- Typical intermediate model structure
SELECT
    'supplier_code'  AS supplier,
    col1, col2, ...
FROM {{ ref('stg_supplier_table') }}

-- Typical mart model (union all suppliers)
SELECT * FROM {{ ref('int_mko_table') }}
-- UNION ALL SELECT * FROM {{ ref('int_xdc_table') }}
```

```bash
# Run all models
dbt run

# Run only staging models
dbt run --select staging

# Run a specific model and everything it depends on
dbt run --select +int_mko_variants

# Run tests
dbt test

# Load seeds
dbt seed

# Run seed + models + tests in sequence
dbt seed && dbt run && dbt test
```

---

## Practice

**Questions:**

1. What does `dbt run` actually do? What SQL does it execute for a staging model
   materialised as a view versus a mart model materialised as a table?

2. Why must `{{ ref() }}` be used instead of writing table names directly in dbt SQL?
   Give two reasons.

3. The staging models in this project are materialised as views and mart models as
   tables. Explain the reasoning behind this choice.

4. A dbt model fails with `Catalog Error: Table "int_mko_products" does not exist`.
   You check and `int_mko_products.sql` is in the `intermediate/` folder. What are
   two possible causes, and how would you diagnose each?

**Short tasks:**

5. Run `dbt run --select staging` and check which models were created. Then run
   `dbt test` and read the test output — which tests pass and which fail?

6. Open `int_mko_variants.sql`. Identify where the `QUALIFY` dedup happens and explain
   what would happen if you removed that line after two pipeline runs.

7. You are adding XDC as a second supplier. List the files you would create or modify
   (with file paths). Which files do you NOT need to touch until the final step?
