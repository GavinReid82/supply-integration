# dbt Model Data Flow

> **This doc assumes you know dbt basics** (models, `ref()`, materialisations). See `learn_dbt_fundamentals.md` first if needed.

## Overview

This document maps how data moves through the `catalog_data_platform` pipeline — from
raw S3 Parquet files through dbt's three layers (staging → intermediate → marts) to
the tables the Streamlit UI queries. The pipeline has **22 models** across **5 parallel
data streams**, each tracing one type of data from source to output.

## Everyday analogy

Think of it as a car assembly line with 5 parallel tracks — one for the engine, one for
the body, one for the electrics, and so on. Each track goes through the same three
stations:

1. **Staging station** — clean, label, and standardise the raw parts (rename columns,
   cast types, remove defects with `QUALIFY`).
2. **Intermediate station** — stamp every part with the supplier's brand and normalise
   it to the factory specification (add `supplier` column, harmonise column names).
3. **Final assembly (mart)** — bolt all the tracks together into the finished vehicle
   (JOIN streams, UNION ALL suppliers, materialise as a table for the showroom).

When a second supplier (XDC) joins the factory, each stream gets a parallel XDC track.
The final assembly station needs almost no changes — it just unions one more set of parts.

---

## In the project

### The full map

```
S3 Parquet
  │
  ├─ raw/product/*/products.parquet ──► stg_mko_products ──► int_mko_products ──► catalog (mart)
  │                                                                                     ▲
  ├─ raw/product/*/variants.parquet ──► stg_mko_variants ──► int_mko_variants ──► variants (mart)
  │                                              ▲                  │
  ├─ raw/stock/*/stock.parquet ────────► stg_mko_stock ──► int_mko_stock ──────► (feeds catalog)
  │
  ├─ raw/price/*/price.parquet ────────► stg_mko_prices ──► int_mko_prices ──────► prices (mart)
  │
  └─ raw/print/*/print.parquet ────────► stg_mko_print_options ──► int_mko_print_options ──► print_options
                                      └─ stg_mko_print_prices  ──► int_mko_print_prices  ──► print_prices
```

Each mart also has a supplier-filtered version (e.g. `mko_catalog`, `mko_variants`):
```sql
select * from {{ ref('catalog') }} where supplier = 'mko'
```

### What each layer does

| Layer | Job | Stored? | Key operations |
|---|---|---|---|
| **Staging** | Read S3, cast types, rename columns, unpivot | View (no) | `read_parquet()`, `try_cast()`, `UNION ALL` unpivot, `QUALIFY` dedup |
| **Intermediate** | Add `supplier` column, normalise names, derive values, cross-stream joins | View (no) | `{{ ref() }}`, `JOIN`, `CASE`, window functions |
| **Marts** | Assemble final tables for the UI; aggregate across streams | Table (yes) | `LEFT JOIN`, `GROUP BY`, `bool_or()`, `UNION ALL` |

---

### Products stream

**Purpose:** Core product info — name, brand, dimensions, categories.

#### `stg_mko_products.sql`

```sql
with source as (
    select * from read_parquet('s3://.../mko/raw/product/*/products.parquet')
)
select
    ref                                        as product_ref,
    name                                       as product_name,
    try_cast(item_long   as decimal(10, 2))    as item_length_mm,
    try_cast(item_weight as decimal(10, 4))    as item_weight_kg,
    try_cast(order_min_product as integer)     as min_order_qty,
    category_name_1, category_name_2, category_name_3,
    imagemain, link360, linkvideo
from source
qualify row_number() over (partition by ref order by ref) = 1
```

- Renames `ref` → `product_ref`, `name` → `product_name`
- Casts dimension columns from strings to decimals
- `QUALIFY row_number() = 1` removes duplicate rows — MKO occasionally sends the same
  product twice

#### `int_mko_products.sql`

```sql
select
    'mko'             as supplier,
    product_ref,
    product_name,
    category_name_1   as category,
    category_name_2   as subcategory,
    imagemain         as image_url,
    -- ... all other columns
from {{ ref('stg_mko_products') }}
```

- Prepends `supplier = 'mko'` — every intermediate model does this
- Renames `category_name_1` → `category` to match canonical mart column names

**What a row looks like after this model:**

| supplier | product_ref | product_name | category | subcategory | min_order_qty |
|---|---|---|---|---|---|
| mko | MK9200 | Makito Mug 350ml | Drinkware | Mugs | 50 |

---

### Variants stream

**Purpose:** Colour/size variants of each product. One row per variant.

#### `stg_mko_variants.sql`

Pure rename — MKO's raw column names (`refct`, `colourname`, `image500px`) are obscure;
staging maps them to readable names.

#### `int_mko_variants.sql` — cross-stream join

This is the most complex intermediate model. It **joins two staging streams** to add
availability data:

```sql
with variants as (
    select * from {{ ref('stg_mko_variants') }}
),
availability as (
    select product_ref, bool_or(in_stock_now) as is_available
    from {{ ref('stg_mko_stock') }}       -- ← different staging stream
    group by product_ref
)
select
    'mko'                          as supplier,
    v.product_ref,
    v.matnr                        as variant_id,
    v.sku_code,
    v.colour_code, v.colour_name, v.size,
    coalesce(a.is_available, false) as is_available,
    null                           as attribute_json
from variants v
left join availability a on v.product_ref = a.product_ref
qualify row_number() over (partition by v.product_ref, v.matnr order by 1) = 1
```

- Joins `stg_mko_variants` with `stg_mko_stock` — two separate S3 feeds combined here
- `bool_or(in_stock_now)` collapses all warehouse rows into a single "is this product
  available?" flag per product
- `attribute_json` is `null` — placeholder column for future use

---

### Prices stream — the unpivot pattern

**Purpose:** Price tiers — how unit price changes with order quantity.

#### The problem: wide format in the source

MKO's raw price data arrives **one row per product** with up to 4 tiers as separate columns:

| ref | section1 | price1 | section2 | price2 | section3 | price3 |
|---|---|---|---|---|---|---|
| MK9200 | 50 | 4.20 | 100 | 3.80 | 250 | 3.40 |

This "wide" format is hard to query. To find the cheapest tier you'd need
`LEAST(price1, price2, price3)` — and adding a fifth tier would break your query.

#### The solution: tall format via UNION ALL

`stg_mko_prices.sql` unpivots this into **one row per tier**:

```sql
unpivoted as (
    select ref as product_ref, 1 as tier,
           try_cast(section1 as integer) as min_qty,
           try_cast(price1   as decimal(10,4)) as unit_price
    from source where section1 is not null

    union all
    select ref, 2,
           try_cast(section2 as integer),
           try_cast(price2   as decimal(10,4))
    from source where section2 is not null

    -- ... repeated for tiers 3 and 4
)
```

After unpivot, the same product produces **multiple rows**:

| product_ref | tier | min_qty | unit_price |
|---|---|---|---|
| MK9200 | 1 | 50 | 4.20 |
| MK9200 | 2 | 100 | 3.80 |
| MK9200 | 3 | 250 | 3.40 |

Now `MIN(unit_price)` and `MAX(unit_price)` give you price range trivially. Adding a
fifth tier means adding one more `UNION ALL` branch — nothing else changes.

---

### Stock stream

**Purpose:** Per-warehouse inventory levels and availability dates.

```sql
-- stg_mko_stock.sql
select
    ref           as product_ref,
    warehouse,
    try_cast(stock as integer)   as stock_qty,
    case
        when lower(available) = 'immediately' then current_date
        else try_cast(available as date)
    end           as available_date,
    available = 'immediately'    as in_stock_now
from source
```

The raw `available` column contains either `"immediately"` or a date string. The `CASE`
normalises this; `available = 'immediately'` is evaluated as a boolean by DuckDB.

Note: one product can have **multiple rows** — one per warehouse. This gets aggregated
in the catalog mart.

---

### Print options stream — derived columns

**Purpose:** What print techniques and areas are available per product.

#### `int_mko_print_options.sql` — business logic

```sql
select
    'mko'  as supplier,
    product_ref,
    teccode,
    TRIM(REGEXP_REPLACE(technique_name, '\s*\(FULLCOLOR\)', '', 'g')) as technique_name,
    CASE
        WHEN technique_name ILIKE '%FULLCOLOR%' THEN -1::BIGINT
        ELSE CAST(max_colours AS BIGINT)
    END    as print_color,
    -- ...
from {{ ref('stg_mko_print_options') }}
```

`technique_name` — cleaned: MKO appends `(FULLCOLOR)` to full-colour techniques.
`REGEXP_REPLACE` removes this suffix because `print_color = -1` already encodes the
information.

`print_color` — derived: `-1` = full colour (unlimited); any other integer = maximum
spot colours for this technique.

---

### Print prices stream — window functions for tier bounds

**Purpose:** Per-technique pricing tiers (cost per unit depending on print quantity).

#### `stg_mko_print_prices.sql` — 7-tier unpivot

Same unpivot pattern as prices, but with up to 7 tiers. The raw column is `amount_under`
— the **upper bound** of a tier, not the lower bound.

After unpivot:

| teccode | code | tier | amount_under | price_per_unit |
|---|---|---|---|---|
| DP | F | 1 | 25 | 0.85 |
| DP | F | 2 | 100 | 0.60 |

`amount_under = 25` means "this price applies for quantities **under 25**". The lower
bound requires looking at the *previous* tier's `amount_under`.

#### `int_mko_print_prices.sql` — `LAG()` to compute lower bounds

```sql
with_bounds as (
    select
        *,
        coalesce(
            lag(amount_under) over (partition by teccode, code order by tier),
            1
        ) as quantity_min
    from source
)
select
    'mko'           as supplier,
    teccode         as technique_code,
    quantity_min,                        -- computed by LAG
    amount_under - 1 as quantity_max,    -- upper bound is exclusive, so subtract 1
    price_per_unit,
    cliche_cost      as setup_cost,
    -- ...
from with_bounds
```

How `LAG` works here:

| tier | amount_under | LAG(amount_under) | quantity_min | quantity_max |
|---|---|---|---|---|
| 1 | 25 | NULL → coalesce → 1 | **1** | 24 |
| 2 | 100 | 25 | **25** | 99 |

`LAG()` looks at the previous row in the same `teccode/code` partition. Tier 1 has no
previous row, so `coalesce(..., 1)` defaults to 1.

---

### The catalog mart — assembly point

`catalog.sql` is where everything comes together. It's the only mart model that joins
across multiple intermediate models.

```sql
with products as (
    select * from {{ ref('int_mko_products') }}
),
min_prices as (
    select supplier, product_ref,
           min(unit_price) as min_unit_price,
           max(unit_price) as max_unit_price
    from {{ ref('int_mko_prices') }}
    group by supplier, product_ref
),
stock_summary as (
    select supplier, product_ref,
           sum(stock_qty)       as total_stock_qty,
           min(available_date)  as earliest_available_date
    from {{ ref('int_mko_stock') }}
    group by supplier, product_ref
),
availability as (
    select supplier, product_ref, bool_or(is_available) as in_stock_now
    from {{ ref('variants') }}           -- reads the mart, not an intermediate
    group by supplier, product_ref
)
select p.*, pr.min_unit_price, pr.max_unit_price,
       s.total_stock_qty, a.in_stock_now, s.earliest_available_date
from products p
left join min_prices    pr on p.supplier = pr.supplier and p.product_ref = pr.product_ref
left join stock_summary s  on p.supplier = s.supplier  and p.product_ref = s.product_ref
left join availability  a  on p.supplier = a.supplier  and p.product_ref = a.product_ref
```

Four things happening:
1. **Products CTE** — one row per product (already deduplicated upstream)
2. **min_prices CTE** — collapses multiple price tiers to a single `min_unit_price / max_unit_price`
3. **stock_summary CTE** — collapses multiple warehouse rows to `total_stock_qty` and
   `earliest_available_date`
4. **availability CTE** — reads from `{{ ref('variants') }}` (a mart, not an intermediate)

---

### The supplier-filtered marts

Five models (`mko_catalog`, `mko_variants`, `mko_prices`, `mko_print_options`,
`mko_print_prices`) are each a single line:

```sql
-- mko_catalog.sql
select * from {{ ref('catalog') }} where supplier = 'mko'
```

**Why they exist:** The UI pages sometimes want to show only one supplier's data without
the caller having to filter. Also useful for testing one supplier in isolation:
`dbt run --select mko_catalog`.

**Why they reference canonical marts, not intermediates:** If the UI queried
`int_mko_products` directly, it would bypass the aggregations that `catalog.sql`
computes (price range, stock totals).

---

### Dependency graph

If you ran `dbt run --select +catalog`, it would execute in this order:

```
1. stg_mko_products       (reads S3)
2. stg_mko_prices         (reads S3)
3. stg_mko_stock          (reads S3)
4. stg_mko_variants       (reads S3)
5. int_mko_products       (depends on 1)
6. int_mko_prices         (depends on 2)
7. int_mko_stock          (depends on 3)
8. int_mko_variants       (depends on 1, 3 — cross-stream join)
9. variants               (depends on 8)
10. catalog               (depends on 5, 6, 7, 9)
11. mko_catalog           (depends on 10)
```

Steps 1–4 can run in parallel (no dependencies between them). Steps 5–8 can also run
in parallel once their inputs exist. dbt handles this automatically.

---

## Glossary

| Term | Meaning |
|---|---|
| **Unpivot** | Transform wide columns (price1, price2, price3) into tall rows using UNION ALL |
| **Wide format** | Multiple values stored as separate columns in the same row |
| **Tall / long format** | Multiple values stored as separate rows; easier to aggregate |
| **Cross-stream join** | An intermediate model that joins data from two different staging models |
| **`bool_or()`** | Returns TRUE if any row in the group is TRUE |
| **`LAG()`** | Window function returning the value from the previous row in the partition |
| **`QUALIFY`** | DuckDB clause for filtering rows after a window function |
| **`try_cast()`** | Safe type cast; returns NULL on failure rather than raising an error |
| **`amount_under`** | MKO's name for the upper (exclusive) bound of a print price tier |
| **`supplier` column** | Added in every intermediate model — enables UNION ALL across suppliers |
| **Canonical mart** | A multi-supplier UNION table (`catalog`, `variants`, etc.) |
| **Supplier-filtered mart** | `mko_catalog` etc. — a `WHERE supplier = 'mko'` filter over the canonical mart |

---

## Cheat sheet

```
THE 5 STREAMS:
  products     → product info, dimensions, categories
  variants     → colour/size variants, + availability from stock
  prices       → quantity-based unit price tiers (unpivoted)
  stock        → per-warehouse stock qty + availability dates
  print_opts   → print techniques per product
  print_prices → price per unit print run, per tier (unpivoted)

LAYER RESPONSIBILITIES:
  staging      → read S3, rename, try_cast, dedup (QUALIFY), unpivot (UNION ALL)
  intermediate → add supplier col, normalise names, derive values, cross-stream joins
  marts        → aggregate (GROUP BY), join streams, materialise to DuckDB table

KEY PATTERNS:
  -- Unpivot wide to tall (prices, print_prices)
  SELECT ref, 1 as tier, try_cast(price1 as decimal) as price FROM source WHERE price1 IS NOT NULL
  UNION ALL
  SELECT ref, 2,         try_cast(price2 as decimal)          FROM source WHERE price2 IS NOT NULL

  -- Dedup (products, variants)
  QUALIFY row_number() OVER (PARTITION BY id_col ORDER BY 1) = 1

  -- Collapse to product level (catalog)
  bool_or(is_available)            -- any variant in stock?
  min(unit_price), max(unit_price) -- price range across tiers
  sum(stock_qty)                   -- total across warehouses

  -- Tier bounds (print_prices)
  coalesce(lag(amount_under) OVER (PARTITION BY teccode, code ORDER BY tier), 1) AS quantity_min
  amount_under - 1 AS quantity_max

  -- Supplier-filtered mart (5 x mko_*)
  SELECT * FROM {{ ref('canonical_mart') }} WHERE supplier = 'mko'
```

---

## Practice

**Questions:**

1. There are 6 staging models but only 5 canonical mart tables. Which two staging/intermediate
   streams feed into a single mart, and why does it make sense to combine them there?

2. `catalog.sql` references `{{ ref('variants') }}` — a mart model — for availability
   data. Why does it use the mart rather than `int_mko_variants` directly?

3. MKO's raw price data arrives one row per product with price tiers as separate columns.
   Explain the unpivot pattern used in `stg_mko_prices.sql` and why tall format is better
   for downstream queries.

4. `int_mko_variants` joins with `stg_mko_stock` (not `int_mko_stock`). Why reference a
   staging model here rather than the intermediate one?

**Short tasks:**

5. Trace product `MK9200` with 3 price tiers `(50, 4.20)`, `(100, 3.80)`, `(250, 3.40)`.
   Write out the rows as they appear after `stg_mko_prices`, after `int_mko_prices`, and
   in the `catalog` mart (price-related columns only).

6. A technique `DP` at position `F` has `amountunder1=25, price1=0.85` and
   `amountunder2=100, price2=0.60`. Write out the rows after `stg_mko_print_prices` and
   `int_mko_print_prices`, including the computed `quantity_min` and `quantity_max`.
