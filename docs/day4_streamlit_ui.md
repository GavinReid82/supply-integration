# Day 4 — Streamlit UI

## What I Did

I built a Streamlit web application that reads from the local DuckDB file and displays
the Makito product catalog with filters, metrics, product images, tiered pricing, and
a variants table. I also fixed several bugs discovered during development.

---

## Core Concepts

### What Streamlit is

Streamlit is a Python library that turns a Python script into an interactive web app.
You write Python — Streamlit handles the HTML, CSS, and JavaScript. It reruns the
entire script from top to bottom every time a user interacts with the page (clicks a
filter, selects a row, etc.).

It's not the right tool for a public production app with thousands of users, but it's
perfect for internal data tools and portfolio projects — you can go from nothing to a
working UI in a day.

---

### `@st.cache_data`

```python
@st.cache_data
def load_catalog() -> pd.DataFrame:
    return query("SELECT * FROM mko_catalog ORDER BY product_name")
```

Because Streamlit reruns the whole script on every interaction, without caching this
would re-query DuckDB every time a user moves a slider. `@st.cache_data` stores the
result in memory after the first call and returns the cached version on subsequent
calls, as long as the function arguments haven't changed.

`load_prices(product_ref)` and `load_variants(product_ref)` take arguments — the cache
is keyed by those arguments, so each product gets its own cached result.

---

### Layout: columns and sidebar

```python
left, right = st.columns([2, 1])
```

`st.columns([2, 1])` creates two columns — the left takes up 2/3 of the width,
the right takes 1/3. Everything placed inside `with left:` renders in the left
column, and vice versa. This gives the table-and-detail-panel layout.

`st.sidebar` renders content in a collapsible panel on the left edge of the page,
separate from the main content area. Filters go in the sidebar because they're
secondary to the main content.

---

### Interactive table selection

```python
selected_rows = st.dataframe(
    display,
    on_select="rerun",
    selection_mode="single-row",
)
selected_indices = selected_rows.selection.get("rows", [])
```

`on_select="rerun"` tells Streamlit to rerun the script when the user clicks a row.
`selected_rows.selection["rows"]` gives a list of the selected row indices (positions
in the filtered DataFrame). I use `filtered.iloc[selected_indices[0]]` to get the
actual row data for the detail panel.

---

### DuckDB connection management

```python
def query(sql: str, params: list = None) -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()
```

DuckDB uses file locks — only one process can write to a `.duckdb` file at a time.
If the Streamlit app holds an open connection, running `run_pipeline.py` (which
writes via dbt) fails with a lock conflict error.

The `try/finally` block guarantees the connection closes even if the query throws
an error. `finally` runs regardless of whether an exception occurred. Without this,
Python's garbage collector decides when to close the connection — which isn't fast
enough to release the lock before dbt needs it.

The practical workflow: stop Streamlit before running the pipeline, then restart it.
Or run the pipeline first, then start the UI.

---

### Staging views vs mart tables

The UI queries `mko_catalog`, `mko_prices`, and `mko_variants` — all mart tables
materialised as DuckDB tables. It does **not** query staging models directly.

This matters because staging models are **views** — they're just saved SQL that runs
live when queried. The staging views contain `read_parquet('s3://...')` which requires
S3 credentials and the httpfs extension to be configured. The Streamlit app's DuckDB
connection doesn't have those configured — it opens a plain local connection.

Mart tables are physical tables stored in the `.duckdb` file. The UI reads them with
no S3 access required.

**Rule:** The UI only ever reads from marts. Staging is for dbt's internal use.

---

### Tiered pricing display

```python
if prices_df["unit_price"].nunique() == 1:
    st.markdown(f"**Price:** €{float(prices_df.iloc[0]['unit_price']):.2f}")
else:
    price_display["Quantity"] = price_display["min_qty"].abs().apply(
        lambda x: f"Up to {int(x):,} units"
    )
```

The price API returns up to 4 quantity tiers per product. When all tiers have the
same price (most products), showing a tiered table would be confusing — it implies
prices change with quantity when they don't. I check `nunique()` (number of unique
values) to decide which display to use.

The `min_qty` values from the API use negative numbers to encode the first tier
(e.g. `-500` means "up to 500 units"). Taking `abs()` gives the displayable quantity.

---

## Issues I Hit

### Issue 1: Staging view queried S3 from the UI

**What happened:** `load_prices` originally queried `stg_mko_prices` directly. That
view contains `read_parquet('s3://...')`, which needs httpfs and S3 credentials.
The Streamlit DuckDB connection had neither, so it threw an HTTP 400 error.

**Fix:** Created `mko_prices` and `mko_variants` as mart tables (materialised by dbt).
Updated the UI to query those instead.

**Lesson:** Staging models are for dbt's internal pipeline. The UI should only ever
touch mart tables. If the UI needs data that isn't in a mart, add it to a mart —
don't reach into staging.

### Issue 2: DuckDB file lock when running pipeline with UI open

**What happened:** Streamlit was still running (holding an open DuckDB connection)
when I ran `run_pipeline.py`. dbt couldn't acquire the write lock on the `.duckdb`
file and failed with a lock conflict error. Even after stopping Streamlit with
Ctrl+C, the process (PID 91125) was still alive and holding the lock.

**Fix:** Killed the lingering process with `kill 91125`, then re-ran the pipeline.
Fixed the root cause by adding `try/finally` to close connections immediately after
each query.

**Lesson:** DuckDB is a single-writer database. If you have a UI and a pipeline that
both touch the same file, you need to ensure they don't run at the same time.
In production this would be solved architecturally — the pipeline writes to one file,
the UI reads from a copy, or a proper multi-process database (Postgres, etc.) is used.

### Issue 3: `imagemain` missing from `mko_catalog`

**What happened:** The mart model didn't include the `imagemain` column (the product
image URL). Adding it to `mko_catalog.sql` caused a dbt error because it also wasn't
in `stg_mko_products`.

**Fix:** Added `imagemain` to `stg_mko_products.sql` first, then to `mko_catalog.sql`.

**Lesson:** Changes flow downstream. When adding a column to a mart, trace it back to
where it originates in staging and add it there first.

### Issue 4: `dbt` not found in subprocess

**What happened:** `run_pipeline.py` calls dbt via `subprocess.run(["dbt", "run", ...])`.
When running `python run_pipeline.py` (system Python, not the venv), `dbt` isn't on
the system PATH — it's only installed inside `.venv/`.

**Fix:** Used `sys.executable` to find the current Python's location, then derived
the dbt path from it:

```python
from pathlib import Path
DBT = str(Path(sys.executable).parent / "dbt")
```

This always points to the dbt that lives alongside whichever Python is running the
script — whether that's the venv Python or any other.

**Lesson:** When a Python script calls other tools via subprocess, don't assume those
tools are on the system PATH. Derive the path programmatically from `sys.executable`.

---

## What I Should Be Able to Explain After Day 4

- What Streamlit is and why it reruns the script on every interaction
- What `@st.cache_data` does and why it's needed
- How `st.columns`, `st.sidebar`, and `st.metric` work
- How interactive row selection works with `on_select="rerun"`
- What a DuckDB file lock is and why it matters
- Why `try/finally` guarantees a connection closes
- Why the UI queries mart tables and not staging views
- What `nunique()` does and how I used it for the pricing display
- Why `sys.executable` is the right way to find co-installed tools
