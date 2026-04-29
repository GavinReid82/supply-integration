# Day 9 — XDC as a Second Supplier

## What I Did

I added Xindao (XDC) as the second supplier, validating the multi-supplier architecture
built on Day 5. The goal was to prove that the `SupplierExtractor` pattern, dbt
intermediate layer, and canonical mart structure could absorb a supplier with a
fundamentally different data format — XLSX instead of XML, variant-first instead of
product-first — without changing the pipeline orchestrator, the UI, or the canonical
mart schemas.

---

## Core Concepts

### XLSX extraction vs XML parsing

MKO returns XML responses that I parse with `ElementTree`. XDC provides XLSX files
at authenticated full URLs. The key difference is how I read the raw bytes:

```python
# MKO — XML bytes → ElementTree
root = ET.fromstring(raw)
for product in root.findall(".//product"):
    ...

# XDC — XLSX bytes → pandas DataFrame via openpyxl
df = pd.read_excel(io.BytesIO(raw))
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
```

`pd.read_excel` uses `openpyxl` internally to parse the XLSX. The column normalisation
step (`strip().lower().replace(" ", "_")`) handles the inconsistent header casing in
XDC's spreadsheets. After normalisation, the DataFrame is uploaded to S3 as Parquet —
the same as every MKO feed.

The `SupplierExtractor` contract means `XdcExtractor.run(date)` only needs to produce
Parquet files in the right S3 locations. What happens inside `run()` is private to
the adapter.

---

### Deriving a product table from variants

XDC has no separate product table. The product XLSX is structured around
colour/size variants: one row per variant, with product-level fields (`modelcode`,
`itemname`, `brand`, `maincategory`) repeated on every row.

The canonical mart expects one row per product in the `catalog` table. The intermediate
model `int_xdc_products.sql` derives this by taking the lexically-first variant as the
product representative:

```sql
with source as (
    select * from {{ ref('stg_xdc_variants') }}
),

ranked as (
    select *,
           row_number() over (partition by product_id order by variant_id) as rn
    from source
)

select 'xdc' as supplier, product_id as product_ref, product_name, ...
from ranked
where rn = 1
```

The variant fields (colour, size, image) are not in this model — they live in
`int_xdc_variants`. Only the product-level fields (name, category, dimensions,
composition) are promoted. This is a deliberate normalisation: the mart's `catalog`
table is about products, not variants.

**Why rank 1 by `variant_id`?** It gives a deterministic, reproducible result. Any
other choice (e.g. "first by colour name") would produce different rows on different
runs if data changes. Lexical ordering of `variant_id` is stable.

---

### Conditional Jinja unions in canonical marts

The Day 5 plan described canonical marts as static `UNION ALL` tables. In practice, a
static UNION requires XDC credentials to be present for every `dbt run`, even during
MKO-only development. The solution is conditional compilation:

```sql
-- catalog.sql
with products as (
    select ... from {{ ref('int_mko_products') }}
    {% if env_var('XDC_BASE_URL', '') != '' %}
    union all
    select ... from {{ ref('int_xdc_products') }}
    {% endif %}
),
```

`env_var('XDC_BASE_URL', '')` is the dbt function for reading an environment variable
with a default. The `{% if %}` block is Jinja — resolved at compile time, before any
SQL runs. If `XDC_BASE_URL` is empty, the compiled SQL has no XDC branch at all.

This means:
- `dbt run` with `XDC_BASE_URL` set → full multi-supplier build
- `dbt run` without `XDC_BASE_URL` → MKO-only, no XDC models compiled or referenced

**The compile-time vs runtime distinction matters.** A Python `if` is runtime — the
SQL still has to be valid for both branches. A Jinja `{% if %}` removes the branch
entirely from the compiled SQL, which also means dbt does not try to resolve the
`ref('int_xdc_products')` call when XDC is inactive. This is what allows
`dbt run --exclude tag:xdc` to work cleanly.

---

### dbt tags

Adding `{{ config(tags=["xdc"]) }}` to every XDC model enables targeted selection:

```bash
dbt run --exclude tag:xdc     # MKO-only, no XDC models built
dbt test --select tag:xdc     # run only XDC model tests
dbt run --select tag:xdc      # build only XDC models (for debugging)
```

Tags are the right mechanism for grouping models by supplier. The alternative —
checking model name prefixes — works but is fragile if naming conventions change.

---

### XDC availability logic

MKO uses `available_date` from the stock feed to determine in-stock status:
`available = 'immediately'` maps to today's date.

XDC uses a different model:

1. **Lifecycle flag:** if `productlifecycle = 'Outlet'`, the variant is being
   discontinued and should not be shown as available by default.
2. **Stock threshold by subcategory:** even an Outlet variant counts as available if
   stock exceeds a per-subcategory minimum (e.g. 250 for water bottles, 30 for
   headphones).

The thresholds are stored in `dbt_project/seeds/xdc_availability_thresholds.csv`
and joined in `int_xdc_variants.sql`:

```sql
(
    coalesce(v.productlifecycle, '') != 'Outlet'
    or coalesce(s.stock_qty, 0) > coalesce(t.threshold, 300)
) as is_available
```

The `coalesce(t.threshold, 300)` default handles subcategories not in the thresholds
seed — 300 is a conservative fallback.

**Why a seed for thresholds?** The values are business decisions, not logic. A data
analyst should be able to change a threshold by editing a CSV and running
`dbt seed && dbt run --select tag:xdc` — no SQL knowledge required.

---

### XDC data quirks

**XLSX headers with spaces:** `"Main Category"`, `"Item Length Cm"`. Normalised on
read in the extractor, not in staging. The extractor is the right place for this:
staging assumes clean column names, and normalisation happens before upload.

**Dimensions in cm, weight in grams:** the staging model converts to mm and kg to
match the canonical mart schema (set by MKO, which uses mm/kg):

```sql
try_cast(itemlengthcm as decimal(8, 2)) * 10   as length_mm,
try_cast(itemweightnetgr as decimal(10, 3)) / 1000  as weight_kg,
```

**No `product_ref` column:** XDC calls it `modelcode`; the intermediate model aliases
it to `product_ref` to match the canonical shape.

---

## The Changes Made

| File | Change |
|---|---|
| `extractor/xdc.py` | New — `XdcExtractor(SupplierExtractor)`; reads XLSX via `pd.read_excel`, normalises headers, uploads as Parquet |
| `run_pipeline.py` | Updated — XDC config + extractor loaded conditionally on `XDC_BASE_URL` env var |
| `dbt_project/models/staging/stg_xdc_variants.sql` | New — one row per variant; cm→mm, g→kg unit conversions |
| `dbt_project/models/staging/stg_xdc_prices.sql` | New |
| `dbt_project/models/staging/stg_xdc_print_options.sql` | New |
| `dbt_project/models/staging/stg_xdc_print_prices.sql` | New |
| `dbt_project/models/staging/stg_xdc_stock.sql` | New |
| `dbt_project/models/intermediate/int_xdc_products.sql` | New — derives product from variants; rank-1 per `product_id` |
| `dbt_project/models/intermediate/int_xdc_variants.sql` | New — two-tier availability logic (lifecycle + threshold) |
| `dbt_project/models/intermediate/int_xdc_prices.sql` | New — joins prices to representative variant per product |
| `dbt_project/models/intermediate/int_xdc_print_options.sql` | New |
| `dbt_project/models/intermediate/int_xdc_print_prices.sql` | New |
| `dbt_project/models/intermediate/int_xdc_stock.sql` | New |
| `dbt_project/models/marts/catalog.sql` | Updated — conditional Jinja `{% if env_var('XDC_BASE_URL') %}` union |
| `dbt_project/models/marts/variants.sql` | Updated — conditional XDC union |
| `dbt_project/models/marts/prices.sql` | Updated — conditional XDC union |
| `dbt_project/models/marts/print_options.sql` | Updated — conditional XDC union |
| `dbt_project/models/marts/print_prices.sql` | Updated — conditional XDC union |
| `dbt_project/seeds/xdc_availability_thresholds.csv` | New — per-subcategory stock thresholds for Outlet variants |
| `dbt_project/seeds/pcm_templates.csv` | New — PCM template reference data |
| `ui/supplier_reference.py` | Updated — `_xdc()` builder added to `build()` dispatcher |
| `requirements.txt` | Added `openpyxl==3.1.5` |

**Result:** 33 dbt models (11 staging views, 12 intermediate views, 10 mart tables)
across MKO and XDC. 4 seeds. MKO-only build confirmed with `dbt run --exclude tag:xdc`.

---

## What I Should Be Able to Explain After Day 9

- How `XdcExtractor` differs from `MkoExtractor` and why the contract (`run(date)`)
  is the same regardless
- Why XDC has no product table and how `int_xdc_products.sql` solves this
- What dbt conditional Jinja (`{% if env_var(...) %}`) does at compile time vs runtime
  and why it enables MKO-only builds
- How dbt tags work and how `--exclude tag:xdc` uses them
- What XDC's two-tier availability logic does and why the thresholds are in a seed
- Why dimension/weight unit conversion happens in staging rather than intermediate
- Why XLSX header normalisation happens in the extractor rather than staging
