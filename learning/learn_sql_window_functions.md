# SQL Window Functions

## Overview

A regular aggregate function collapses a group of rows into one:

```sql
SELECT supplier, COUNT(*) AS product_count
FROM catalog
GROUP BY supplier
```

You lose the individual rows — you only see the summary.

A **window function** does the calculation *without* collapsing. Every original row
stays in the result; the function just adds a new column derived from looking at a
*window* (a defined set of rows nearby).

## Everyday analogy

Imagine a league table of football results. You want each team's rank *alongside* their
actual score. A `GROUP BY` would give you just the ranks. A window function gives you
the score AND the rank, one row per team.

---

## The core syntax

```sql
function_name() OVER (
    PARTITION BY column1
    ORDER BY column2
    ROWS/RANGE BETWEEN ...
)
```

- **`OVER (...)`** — this is what makes it a window function. Without `OVER`, the same
  function name is often an aggregate.
- **`PARTITION BY`** — splits the rows into groups ("windows"). The function restarts
  for each partition. Like `GROUP BY`, but the rows are not collapsed.
- **`ORDER BY`** — within each partition, defines the row order. Required for
  ranking/cumulative functions; optional for others.

### `ROW_NUMBER()`

Assigns a sequential integer to each row within a partition, starting at 1.

```sql
ROW_NUMBER() OVER (PARTITION BY product_ref ORDER BY created_at)
```

If three rows share `product_ref = '2050'`, they get numbers 1, 2, 3. If you then
filter `WHERE row_num = 1`, you keep exactly one row per product.

**No ties.** `ROW_NUMBER` always produces unique numbers within a partition, even if
the `ORDER BY` values are identical — it breaks ties arbitrarily.

### `RANK()` and `DENSE_RANK()`

Like `ROW_NUMBER`, but ties get the same number:

| Score | ROW_NUMBER | RANK | DENSE_RANK |
|---|---|---|---|
| 100 | 1 | 1 | 1 |
| 90  | 2 | 2 | 2 |
| 90  | 3 | 2 | 2 |
| 80  | 4 | 4 | 3 |

`RANK` skips numbers after a tie (two rows tied at 2nd → next is 4th).
`DENSE_RANK` does not skip (tied at 2nd → next is 3rd).

For deduplication, use `ROW_NUMBER` — you just need one row, and ties don't matter.

### `SUM()`, `AVG()`, `COUNT()` as window functions

```sql
SUM(unit_price) OVER (PARTITION BY supplier)
```

This adds the total price for the supplier to every row — without collapsing. Useful
for "what fraction of the total is this row?" calculations.

---

## `QUALIFY` — DuckDB/BigQuery syntax

`WHERE` runs before window functions are computed. So you cannot do this:

```sql
-- This FAILS
SELECT *, ROW_NUMBER() OVER (PARTITION BY ref ORDER BY ref) AS rn
FROM source
WHERE rn = 1    -- rn doesn't exist yet when WHERE runs
```

The standard solution uses a subquery or CTE:

```sql
-- Standard SQL approach
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ref ORDER BY ref) AS rn
    FROM source
) t
WHERE rn = 1
```

**`QUALIFY`** is DuckDB/BigQuery shorthand that avoids the subquery:

```sql
SELECT *
FROM source
QUALIFY ROW_NUMBER() OVER (PARTITION BY ref ORDER BY ref) = 1
```

It runs *after* window functions — exactly like `HAVING` runs after `GROUP BY`.

---

## In the project

### Deduplicating products in staging

**File:** `dbt_project/models/staging/stg_mko_products.sql`

The Makito product API occasionally returns the same product ref more than once (3
duplicates were found in real data). A `unique` dbt test on `product_ref` would fail
unless we deduplicate.

```sql
SELECT
    ref AS product_ref,
    name AS product_name,
    ...
FROM source
QUALIFY ROW_NUMBER() OVER (PARTITION BY ref ORDER BY ref) = 1
```

**What this does:**
- For each unique `ref` value, number the rows 1, 2, 3...
- `QUALIFY ... = 1` keeps only the first row for each ref
- The `ORDER BY ref` is arbitrary — we just need a deterministic tiebreaker

**Why in staging?** Deduplication is data cleaning — it belongs in the staging layer,
not the mart. If it were in the mart, every downstream model would still receive
duplicates from staging.

### Deduplicating variants across pipeline runs

**File:** `dbt_project/models/intermediate/int_mko_variants.sql`

The staging model reads from an S3 wildcard:
```
s3://supply-integration/mko/raw/product/*/variants.parquet
```

The `*` matches every date partition. After two pipeline runs, every variant appears
twice (once from each date directory). The dedup is applied in the intermediate model:

```sql
SELECT ...
FROM {{ ref('stg_mko_variants') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY product_ref, matnr ORDER BY 1) = 1
```

Here `PARTITION BY product_ref, matnr` — the combination of product and variant — is
the natural key. `ORDER BY 1` just means "order by the first column" — the specific
order does not matter, we just need exactly one row per combination.

**Why intermediate, not staging?** Staging is a pure reflection of the raw data. The
duplication is caused by the pipeline run history, not by bad source data. The
intermediate layer is the right place to normalise across pipeline runs.

---

## Glossary

| Term | Meaning |
|---|---|
| Window function | A function that operates across a set of related rows, without collapsing them |
| `OVER()` | The clause that turns an aggregate function into a window function |
| `PARTITION BY` | Divides rows into groups; the function restarts for each group |
| `ORDER BY` (in OVER) | Defines row order within each partition |
| `ROW_NUMBER()` | Sequential integer per row within each partition; no ties |
| `RANK()` | Like ROW_NUMBER but tied rows share the same rank; gaps follow ties |
| `DENSE_RANK()` | Like RANK but no gaps after ties |
| `QUALIFY` | DuckDB/BigQuery clause to filter on window function results (like HAVING for GROUP BY) |
| Deduplication | Removing duplicate rows — keeping exactly one row per logical entity |
| Partition | A subset of rows with the same PARTITION BY value |

---

## Cheat sheet

```sql
-- Basic pattern
SELECT *, function() OVER (PARTITION BY col1 ORDER BY col2) AS alias
FROM table;

-- Deduplication — keep first row per key
SELECT *
FROM source
QUALIFY ROW_NUMBER() OVER (PARTITION BY id_col ORDER BY any_col) = 1;

-- Running total
SELECT date, amount,
       SUM(amount) OVER (ORDER BY date) AS cumulative_total
FROM sales;

-- Rank within group
SELECT product, category, sales,
       RANK() OVER (PARTITION BY category ORDER BY sales DESC) AS rank_in_cat
FROM products;

-- Row count without collapsing
SELECT product, category,
       COUNT(*) OVER (PARTITION BY category) AS products_in_category
FROM products;
```

---

## Practice

**Questions:**

1. What is the difference between `GROUP BY supplier` and `PARTITION BY supplier` in
   terms of what the result set looks like?

2. Why can't you use `WHERE rn = 1` to filter window function results? What clause do
   you use instead in DuckDB, and why does it work there?

3. In the project, the variant deduplication uses `PARTITION BY product_ref, matnr`.
   Why is this the right partition key, rather than just `product_ref`?

4. What is the difference between `RANK()` and `DENSE_RANK()`? Give an example where
   they produce different results.

**Short tasks:**

5. Write a query that returns the cheapest product (by `min_unit_price`) in each
   `category_name_1`, using `ROW_NUMBER()`. Include all product columns plus a
   `rank_in_category` column.

6. The `prices` table has one row per product per tier. Write a query that adds a
   `pct_of_max_price` column showing each tier's price as a percentage of that
   product's highest tier price.
