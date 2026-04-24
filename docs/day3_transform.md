# Day 3 — Transform with dbt + DuckDB

## What I Did

I built the transformation layer: SQL models that read the raw Parquet files from S3,
clean and type-cast the data, join it together, and write a final analytics-ready table.
This is the **T** in ELT.

The tools: **dbt** to write and run the SQL models, **DuckDB** as the query engine that
actually executes them.

---

## Core Concepts

### What dbt is

dbt (data build tool) is a framework for writing SQL transformations. Instead of writing
raw SQL scripts and running them manually, dbt gives you:

- **Models** — each model is just a `SELECT` statement saved as a `.sql` file. dbt
  wraps it in a `CREATE TABLE` or `CREATE VIEW` automatically.
- **`{{ ref() }}`** — when one model references another, you use `{{ ref('model_name') }}`
  instead of the table name directly. dbt uses this to build a dependency graph and run
  models in the correct order.
- **Tests** — built-in data quality checks (`not_null`, `unique`) that run after the models.
- **Layers** — the convention of staging → marts keeps transformation concerns separate.

dbt doesn't move data. It just runs SQL against whatever database you point it at.

---

### What DuckDB is

DuckDB is an in-process analytical database. "In-process" means it runs inside your
Python process — there's no separate server to start or connect to. It's like SQLite,
but designed for analytical queries (aggregations, joins, window functions) rather than
transactional workloads.

For this project, DuckDB has one key superpower: **it can read Parquet files directly
from S3** via its `httpfs` extension, without downloading the files first. The SQL:

```sql
SELECT * FROM read_parquet('s3://supply-integration/mko/raw/product/*/products.parquet')
```

...connects to S3, reads the Parquet metadata, and pulls only the columns and rows it
needs. This is the same idea behind BigQuery reading from GCS — the storage and the
compute are separate.

---

### The two-layer model: staging and marts

**Staging** (`models/staging/stg_mko_*.sql`):
- One model per source table
- Rename columns to consistent names
- Cast types (everything arrives as VARCHAR from the Parquet, needs to become integers, decimals, dates)
- Deduplicate if the source has duplicates
- No business logic yet — just clean the raw data
- Materialised as **views** (no data is written, just a saved query)

**Marts** (`models/marts/mko_catalog.sql`):
- Join the staging models together
- Apply business logic (aggregate stock, pick the lowest price)
- Produce the table the UI will query
- Materialised as a **table** (data is written to DuckDB so the UI reads it fast)

This separation means: if the source column names change, you only update the staging
model. Everything downstream that uses `{{ ref('stg_mko_products') }}` is unaffected.

---

## The Configuration Files

### `dbt_project.yml`

```yaml
models:
  supply_integration:
    staging:
      +materialized: view
    marts:
      +materialized: table
```

This sets the materialisation for all models in each directory. Staging models become
views (no cost to rebuild, always fresh). Mart models become tables (written to DuckDB,
fast to query from Streamlit).

### `profiles.yml`

```yaml
supply_integration:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('DUCKDB_PATH', 'data/supply_integration.duckdb') }}"
      extensions:
        - httpfs
      settings:
        s3_region: "eu-south-2"
        s3_endpoint: "s3.eu-south-2.amazonaws.com"
        s3_access_key_id: "{{ env_var('AWS_ACCESS_KEY_ID') }}"
        s3_secret_access_key: "{{ env_var('AWS_SECRET_ACCESS_KEY') }}"
```

**`path`** — where DuckDB writes the database file. When running locally this is
`data/supply_integration.duckdb`. Inside Docker it would be `/app/data/...`.
The `env_var()` function reads from your `.env` file.

**`extensions: [httpfs]`** — tells DuckDB to load the httpfs extension, which enables
reading from S3/HTTP URLs. Without this, `read_parquet('s3://...')` fails.

**`s3_endpoint`** — DuckDB defaults to `s3.amazonaws.com` (the global endpoint). AWS
newer regions like `eu-south-2` don't work with the global endpoint — requests return
HTTP 400. Setting the regional endpoint explicitly fixes this.

---

## The SQL Models

### `stg_mko_products.sql`

```sql
with source as (
    select * from read_parquet('s3://supply-integration/mko/raw/product/*/products.parquet')
)
select
    ref                                         as product_ref,
    try_cast(item_weight as decimal(10, 4))     as item_weight_kg,
    try_cast(order_min_product as integer)      as min_order_qty,
    ...
from source
qualify row_number() over (partition by ref order by ref) = 1
```

**`read_parquet('s3://.../*/')`** — the `*` wildcard matches any date partition. If
the pipeline has run on multiple days, DuckDB reads all of them and unions the results.
This is fine here because we overwrite the same file each day.

**`try_cast(... as decimal)`** — All values from Parquet arrive as VARCHAR (text).
`try_cast` attempts the conversion and returns `NULL` if it fails — it won't crash the
whole query on one bad value. `cast` (without `try_`) would raise an error instead.

**`qualify row_number() over (partition by ref order by ref) = 1`**

This is a deduplication pattern. Breaking it down:
- `row_number()` — assigns a sequential number to each row
- `over (partition by ref)` — the numbering restarts for each unique `ref` value
- `order by ref` — the order within each partition (arbitrary here, we just need one row)
- `qualify ... = 1` — keep only the first row from each group

The Makito source data had 3 product refs that appeared more than once. This filter
keeps exactly one row per ref. `QUALIFY` is DuckDB/BigQuery syntax — it filters on
window function results, which you can't do in a regular `WHERE` clause.

---

### `stg_mko_prices.sql`

```sql
unpivoted as (
    select ref as product_ref, 1 as tier,
           try_cast(section1 as integer) as min_qty,
           try_cast(price1 as decimal(10, 4)) as unit_price
    from source where section1 is not null

    union all
    select ref, name, 2, try_cast(section2 as integer), try_cast(price2 as decimal(10, 4))
    from source where section2 is not null
    ...
)
```

The source data is **wide**: one row per product, four price columns (`price1`–`price4`).
This pattern transforms it to **tall**: one row per product per tier.

Why tall? Because it's easier to query: "give me the lowest price for product X" becomes
`SELECT MIN(unit_price) WHERE product_ref = 'X'`, rather than
`SELECT LEAST(price1, price2, price3, price4) WHERE ref = 'X'`.

This pattern is called an **unpivot**. Most databases have a built-in `UNPIVOT` operator.
We use `UNION ALL` here because it's explicit and easy to follow.

---

### `stg_mko_stock.sql`

```sql
case
    when lower(available) = 'immediately' then current_date
    else try_cast(available as date)
end as available_date,
available = 'immediately' as in_stock_now
```

The stock API returns `available` as either the string `"immediately"` or a date like
`"13-05-2026"`. We can't `cast` a non-date string to a date, so we use a `CASE` to
handle `"immediately"` separately, converting it to today's date.

`in_stock_now` is a boolean derived column — it's `true` when `available = 'immediately'`,
`false` otherwise. Derived columns like this belong in staging, not the mart.

---

### `mko_catalog.sql` — the mart

```sql
with products as (select * from {{ ref('stg_mko_products') }}),

min_prices as (
    select product_ref,
           min(unit_price) as min_unit_price,
           max(unit_price) as max_unit_price
    from {{ ref('stg_mko_prices') }}
    group by product_ref
),

stock_summary as (
    select product_ref,
           sum(stock_qty)      as total_stock_qty,
           bool_or(in_stock_now) as in_stock_now,
           min(available_date) as earliest_available_date
    from {{ ref('stg_mko_stock') }}
    group by product_ref
)

select p.*, pr.min_unit_price, s.total_stock_qty, s.in_stock_now
from products p
left join min_prices pr on p.product_ref = pr.product_ref
left join stock_summary s  on p.product_ref = s.product_ref
```

**`{{ ref('stg_mko_products') }}`** — dbt resolves this to the actual table/view name
at runtime. More importantly, dbt sees this reference and knows that `mko_catalog`
depends on `stg_mko_products`, so it runs staging models first.

**`bool_or(in_stock_now)`** — DuckDB aggregate function: returns `true` if any row in
the group is `true`. So if any warehouse has the product in stock, the product shows as
in stock. Equivalent to `MAX(CASE WHEN in_stock_now THEN 1 ELSE 0 END) = 1` in standard SQL.

**`LEFT JOIN`** — We use left (not inner) joins because some products may have no price
data or no stock data in the API. An inner join would silently drop those products from
the catalog. A left join keeps them with `NULL` values, which is more honest.

---

### dbt tests

```yaml
columns:
  - name: product_ref
    tests:
      - not_null
      - unique
```

After running models, dbt runs tests. Each test compiles to a SQL query:

- **`not_null`** → `SELECT COUNT(*) FROM model WHERE product_ref IS NULL` — fails if > 0
- **`unique`** → `SELECT product_ref FROM model GROUP BY product_ref HAVING COUNT(*) > 1` — fails if any rows returned

Tests failing doesn't mean the data is wrong — it means the data doesn't meet your
expectations, and you need to understand why. In our case, 3 duplicate product refs
in the source data was a Makito data quality issue, which we fixed by deduplicating
in the staging model.

---

## Issues We Hit

### Issue 1: DuckDB path was a Docker path

**What happened:** The profiles.yml had `path: /app/data/supply_integration.duckdb`.
This path only exists inside a Docker container (where `/app` is the working directory).
Running locally, DuckDB couldn't find or create the file at that path.

**Fix:** Changed to `path: "{{ env_var('DUCKDB_PATH', 'data/supply_integration.duckdb') }}"`.
This defaults to a local `data/` directory when the env var isn't set, and lets Docker
override it by setting `DUCKDB_PATH=/app/data/supply_integration.duckdb` in the
container environment.

**Lesson:** When building for both local and Docker environments, avoid hardcoded paths.
Use environment variables with sensible defaults.

### Issue 2: DuckDB couldn't reach the S3 bucket (HTTP 400)

**What happened:** DuckDB's httpfs extension defaults to the global S3 endpoint
(`s3.amazonaws.com`). For newer AWS regions like `eu-south-2`, this endpoint returns
HTTP 400 — it doesn't know how to route requests to newer regions without a regional
endpoint specified.

**Fix:** Added `s3_endpoint: "s3.eu-south-2.amazonaws.com"` to profiles.yml.

**Lesson:** This is a common gotcha with newer AWS regions. The same issue would affect
any tool that makes direct S3 HTTP calls and doesn't automatically resolve regional
endpoints (as `boto3` does by following HTTP 301 redirects).

### Issue 3: Wrong column names in `stg_mko_products`

**What happened:** The staging model referenced `categories__category_ref_1`
(double underscore — DLT's naming convention for nested fields). But our Python extractor
produces flat columns named `category_ref_1`. The column didn't exist.

**Why this happened:** The staging model was originally written based on the DLT Parquet
output from the Helloprint system (which you shared). When we replaced DLT with our own
XML parser, the column names changed. The staging model wasn't updated to match.

**Fix:** Updated the model to reference `category_ref_1` directly.

**Lesson:** When you replace one layer of the pipeline, check every downstream component
that depends on its output. This is exactly why dbt tests exist — they catch schema
mismatches early.

### Issue 4: 3 duplicate product refs in source data

**What happened:** The uniqueness test failed — 3 product refs appeared more than once
in the Makito product catalog.

**Fix:** Added `qualify row_number() over (partition by ref order by ref) = 1` to the
staging model to keep exactly one row per ref.

**Why here?** Deduplication belongs in staging, not in the mart. If we deduplicated in
`mko_catalog`, we'd be doing it in a model that's supposed to be about joining and
aggregating, not cleaning. Staging is the right layer for cleaning source data.

---

## What You Should Be Able to Explain After Day 3

- The difference between staging and mart layers, and why we separate them
- What dbt's `{{ ref() }}` does and why it matters (dependency graph)
- What `read_parquet('s3://...')` does and why DuckDB can run it
- Why `try_cast` is safer than `cast`
- What `QUALIFY` and `ROW_NUMBER OVER PARTITION BY` do
- What an unpivot is and why wide-to-tall is often better for analytics
- Why `LEFT JOIN` is usually safer than `INNER JOIN` in marts
- What `not_null` and `unique` dbt tests actually check
- Why hardcoded paths break when you move between environments
