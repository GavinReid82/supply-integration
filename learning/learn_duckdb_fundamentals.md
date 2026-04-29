# DuckDB Fundamentals

## Overview

Most databases you've heard of — PostgreSQL, MySQL, SQLite — are built for **transactional**
workloads: lots of small, fast reads and writes, like a shop's till system recording each
sale one at a time.

DuckDB is built for a completely different job: **analytical** queries over large datasets —
aggregations, joins, window functions, reading millions of rows fast.

| Feature | What it means |
|---|---|
| **Embedded** | No server to install or run. DuckDB lives inside your Python process. |
| **File-based** | The entire database is a single `.duckdb` file on disk. |
| **Columnar storage** | Stores data column-by-column (great for aggregations, bad for row-by-row writes). |
| **Parquet-native** | Can read `.parquet` files directly — no import step needed. |
| **S3-aware** | With the `httpfs` extension, reads Parquet files straight from S3 URLs. |
| **SQL-compatible** | Speaks near-standard SQL plus PostgreSQL extensions. |
| **Zero dependencies** | `pip install duckdb` — that's it. |

In `catalog_data_platform`, DuckDB serves as the **local analytical database** that dbt
writes its transformation results into, and that the Streamlit UI queries to display the
product catalog.

## Everyday analogy

Think of the difference between a cash register (transactional) and an accountant's
spreadsheet pulling together everything at the end of the month (analytical).

If PostgreSQL is a busy restaurant kitchen that handles dozens of orders per minute,
DuckDB is a sous chef who takes all the day's receipts and produces a comprehensive
daily report — fast, thorough, no waiting for tables.

---

## In the project

### Embedded vs client-server databases

Most databases run as a **separate server process** that your code connects to over a network:

```
Your Python code  ─── TCP connection ───▶  PostgreSQL server process
                                             └── files on disk
```

DuckDB is **embedded** — it runs *inside* your Python process:

```
Your Python process
  ├── your code
  └── DuckDB engine  ─── reads/writes ───▶  supply_integration.duckdb
```

No installation, no port conflicts, no user credentials, no background service to manage.
Just a file.

### Columnar storage

A row-oriented database stores each row together on disk:

```
Row store:  [id=1, name="Mug", price=9.99] [id=2, name="Pen", price=1.50] ...
```

DuckDB stores each column together:

```
Column store:  [1, 2, 3, ...]    ← all IDs
               ["Mug", "Pen"...] ← all names
               [9.99, 1.50, ...] ← all prices
```

When you run `SELECT AVG(price) FROM products`, DuckDB only reads the `price` column —
it skips the rest. For analytical queries across millions of rows, this is dramatically
faster.

### Parquet files

**Parquet** is a file format designed for analytical data. It uses the same columnar
layout as DuckDB's internal storage — so DuckDB can read Parquet files with almost no
overhead.

Think of Parquet like a perfectly organised filing cabinet: documents sorted by type,
compressed, with an index at the front. DuckDB can flip straight to the section it needs.

In this project, the extraction layer writes Parquet files to S3. DuckDB reads them
directly — no copying, no import, no intermediate format.

### The `httpfs` extension

With `httpfs` configured, a SQL query can point directly at S3:

```sql
SELECT * FROM read_parquet('s3://my-bucket/mko/raw/product/*/products.parquet')
```

DuckDB handles the S3 auth, downloads only the columns it needs, and streams the result.
No boto3, no local temp files.

### How DuckDB fits into the pipeline

```
Supplier APIs
     │
     │  (extractor/*.py — Python + requests)
     ▼
S3 Parquet files
s3://bucket/mko/raw/product/*/products.parquet
     │
     │  (dbt staging models — read_parquet() via httpfs)
     ▼
DuckDB views (staging + intermediate)
     │
     │  (dbt mart models — SQL transforms)
     ▼
DuckDB tables (marts)  ←── written to data/supply_integration.duckdb
     │
     │  (ui/db.py — read-only Python connection)
     ▼
Streamlit UI
```

**Key insight:** DuckDB is not the raw data store — S3 is. DuckDB is the transformation
engine and query layer. If you deleted the `.duckdb` file, you could recreate it by
running `dbt run` again, because all the source data lives in S3.

### Configuration — `profiles.yml`

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
        s3_region: "{{ env_var('AWS_DEFAULT_REGION', 'eu-south-2') }}"
        s3_endpoint: "s3.eu-south-2.amazonaws.com"
        s3_access_key_id: "{{ env_var('AWS_ACCESS_KEY_ID') }}"
        s3_secret_access_key: "{{ env_var('AWS_SECRET_ACCESS_KEY') }}"
```

- `type: duckdb` — use the dbt-duckdb adapter
- `path:` — the `.duckdb` file on disk; defaults to `data/supply_integration.duckdb`
- `extensions: [httpfs]` — load the S3 extension automatically when dbt opens DuckDB
- `settings:` — pass S3 credentials directly into the DuckDB session

### Materialisation in DuckDB

| Layer | Materialisation | What DuckDB stores |
|---|---|---|
| Staging | `view` | A named SQL query — no data stored, executed on demand |
| Intermediate | `view` | Same — just a view over staging views |
| Marts | `table` | Actual rows written to the `.duckdb` file |

**Why views for staging/intermediate?** These layers just clean and rename data from S3.
No need to store intermediate results — DuckDB reads Parquet directly and executes the
full chain on the fly when a mart is built.

**Why tables for marts?** The Streamlit UI queries marts repeatedly. Materialising them
means the UI hits pre-computed tables, not a chain of views that would re-read S3 on
every page load.

### DuckDB Python API — `ui/db.py`

```python
import os
import duckdb
import pandas as pd

DB_PATH = os.getenv("DUCKDB_PATH", "data/supply_integration.duckdb")

def query(sql: str, params: list = None) -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()
```

- `duckdb.connect(DB_PATH, read_only=True)` — opens the `.duckdb` file. `read_only=True`
  allows multiple processes (pipeline and UI) to open the file simultaneously without
  locking conflicts.
- `con.execute(sql, params or [])` — parameterised queries prevent SQL injection:
  `WHERE supplier = ?` with `params=["mko"]`.
- `.df()` — converts the result to a pandas DataFrame with zero-copy integration.
- `finally: con.close()` — closes the connection even if the query throws an error.

### DuckDB-specific SQL features

**`read_parquet()` with S3 glob patterns:**

```sql
select * from read_parquet(
    's3://{{ env_var("S3_BUCKET") }}/mko/raw/product/*/products.parquet'
)
```

`read_parquet()` is a table-valued function. The `*` glob matches any directory
(e.g. one folder per extraction run). DuckDB reads all matching files and unions them
automatically.

**`try_cast()` — safe type casting:**

```sql
try_cast(item_long as decimal(10, 2))  as item_length_mm,
try_cast(order_min_product as integer) as min_order_qty,
```

Raw supplier data comes in as strings. `try_cast()` attempts the conversion and returns
`NULL` on failure instead of crashing the pipeline. Standard `CAST()` would throw an
error if the value is `"N/A"` or blank.

**`QUALIFY` — post-window-function filtering:**

```sql
select * from source
qualify row_number() over (partition by ref order by ref) = 1
```

DuckDB's `QUALIFY` clause filters on window function results inline, avoiding a subquery.

**`bool_or()` — boolean aggregation:**

```sql
bool_or(in_stock_now) as in_stock_now
```

Returns `TRUE` if **any** row in the group is `TRUE`. Used in `catalog.sql` to answer:
"Does this product have *at least one* variant in stock?"

**`LAG()` window function for tier bounds** (used in `int_mko_print_prices.sql`):

```sql
coalesce(
    lag(amount_under) over (partition by teccode, code order by tier),
    1
) as quantity_min
```

`LAG()` looks at the *previous* row in a window. Here it computes the lower bound of
each pricing tier by looking at the `amount_under` from the tier above it.

**`REGEXP_REPLACE()` and `ILIKE`:**

```sql
TRIM(REGEXP_REPLACE(technique_name, '\s*\(FULLCOLOR\)', '', 'g')) as technique_name,
CASE WHEN technique_name ILIKE '%FULLCOLOR%' THEN -1::BIGINT ...
```

`REGEXP_REPLACE` removes the `(FULLCOLOR)` suffix from technique names.
`ILIKE` is case-insensitive pattern matching.

**`::` type cast shorthand:**

```sql
-1::BIGINT   -- equivalent to CAST(-1 AS BIGINT)
```

PostgreSQL-style shorthand supported by DuckDB.

---

## Glossary

| Term | Meaning |
|---|---|
| **DuckDB** | An embedded, columnar, analytical SQL database. |
| **Embedded database** | A database that runs inside your application process — no separate server. |
| **Columnar storage** | Stores data by column rather than by row; fast for aggregations. |
| **Parquet** | A columnar file format for analytical data; highly compressed, column-oriented. |
| **`httpfs` extension** | DuckDB extension enabling reads from S3 and HTTPS URLs. |
| **`read_parquet()`** | DuckDB table function that queries Parquet files directly in SQL. |
| **Glob pattern** | Wildcard path like `*/products.parquet` that matches multiple files. |
| **`try_cast()`** | Safe type conversion — returns NULL on failure instead of an error. |
| **`QUALIFY`** | DuckDB clause for filtering rows based on window function results inline. |
| **`bool_or()`** | Aggregate function returning TRUE if any row in the group is TRUE. |
| **`LAG()`** | Window function returning the value from the previous row in the partition. |
| **`ILIKE`** | Case-insensitive version of SQL `LIKE`. |
| **`::` cast** | PostgreSQL-style type cast shorthand: `value::TYPE`. |
| **dbt-duckdb adapter** | The dbt plugin that lets dbt write to and read from DuckDB. |
| **View** | A saved SQL query; executes on demand, stores no data. |
| **Table** | Materialised rows stored on disk in the `.duckdb` file. |
| **`read_only=True`** | DuckDB connection mode allowing concurrent reads without write locks. |
| **`.df()`** | DuckDB result method that returns a pandas DataFrame. |

---

## Cheat sheet

```
DUCKDB PYTHON API
  import duckdb
  con = duckdb.connect("file.duckdb")                      # open (writable)
  con = duckdb.connect("file.duckdb", read_only=True)      # open (read-only)
  con.execute("SELECT ...", [param1, param2])               # parameterised query
  con.execute(...).df()                                     # → pandas DataFrame
  con.execute(...).fetchall()                               # → list of tuples
  con.close()

  # In-memory (no file)
  con = duckdb.connect()
  con.execute("CREATE TABLE t AS SELECT 1 AS x")

DUCKDB SQL EXTENSIONS
  -- Read Parquet from S3 (glob OK)
  SELECT * FROM read_parquet('s3://bucket/path/*/file.parquet')

  -- Safe type casting (NULL on failure)
  try_cast(column AS INTEGER)

  -- Deduplicate inline (no subquery needed)
  SELECT ... QUALIFY row_number() OVER (PARTITION BY id ORDER BY id) = 1

  -- Boolean aggregation
  bool_or(in_stock_now)    -- TRUE if any row is TRUE
  bool_and(is_valid)       -- TRUE if all rows are TRUE

  -- Case-insensitive match
  WHERE name ILIKE '%fullcolor%'

  -- Regex replace
  REGEXP_REPLACE(col, 'pattern', 'replacement', 'g')

  -- Type cast shorthand
  -1::BIGINT    -- equivalent to CAST(-1 AS BIGINT)

PROFILES.YML (dbt-duckdb)
  type: duckdb
  path: data/my.duckdb
  extensions: [httpfs]
  settings:
    s3_region: eu-west-1
    s3_access_key_id: "{{ env_var('AWS_ACCESS_KEY_ID') }}"
    s3_secret_access_key: "{{ env_var('AWS_SECRET_ACCESS_KEY') }}"

MATERIALIZATIONS
  +materialized: view    # SQL query saved, no data stored
  +materialized: table   # rows written to .duckdb file
```

---

## Practice

**Questions:**

1. What is the difference between an embedded database (DuckDB) and a client-server
   database (PostgreSQL)? Give one advantage of each.

2. In `catalog_data_platform`, staging and intermediate models are views, but mart models
   are tables. Why does this make sense given how DuckDB and the UI interact?

3. `ui/db.py` opens the connection with `read_only=True`. Why is this important when
   both the pipeline service and the UI service run simultaneously?

4. What is the difference between `CAST()` and `try_cast()` in DuckDB? When would you
   choose one over the other?

**Short tasks:**

5. Open a Python REPL, connect to the DuckDB file with `read_only=True`, and run
   `SHOW TABLES`. What tables exist?

6. Run `try_cast('not_a_number' AS INTEGER)` in a DuckDB query and observe the NULL
   result. Then try `CAST('not_a_number' AS INTEGER)` and observe the error.

7. Look at `stg_mko_stock.sql`. Rewrite the `QUALIFY` clause as a standard subquery
   without `QUALIFY`. Which is more readable?
