# Day 8 — UI Navigation, Print Colour Data Model, and Shopping Basket

## What I Did

This session was entirely UI and data model refinement — no new API endpoints, no new
pipeline stages. The focus was on making the two existing workflows (Bespoke and
Category Management) production-ready: correct navigation, better data modelling of
print colour information, and a persistent shopping basket so a user can configure
multiple products before exporting.

---

## Streamlit Navigation with `st.navigation(position="hidden")`

The default Streamlit multipage setup auto-generates a sidebar nav from the filenames
in `pages/`. That is convenient for development but not suitable for a real product:
it exposes internal page names, cannot hide intermediate pages (like Configure Order),
and cannot control labels or icons.

From Streamlit 1.36+, `st.navigation()` takes full control. Setting
`position="hidden"` disables the auto-generated sidebar entirely. Pages are still
registered (which Streamlit requires for `st.switch_page()` to resolve them), but the
sidebar shows only what I explicitly add with `st.sidebar.page_link()`.

```python
# app.py
pg = st.navigation(
    [
        st.Page("pages/0_Home.py",            title="Home",           icon="🏠", default=True),
        st.Page("pages/1_Catalog.py",         title="Bespoke",        icon="🖨️"),
        st.Page("pages/3_Catman.py",          title="Catman",         icon="📊"),
        st.Page("pages/2_Configure_Order.py", title="Configure Order"),
    ],
    position="hidden",
)
st.sidebar.page_link("pages/0_Home.py",    label="Home",    icon="🏠")
st.sidebar.page_link("pages/1_Catalog.py", label="Bespoke", icon="🖨️")
st.sidebar.page_link("pages/3_Catman.py",  label="Catman",  icon="📊")
pg.run()
```

Configure Order is registered (so `st.switch_page("pages/2_Configure_Order.py")`
works from the Catalog page) but has no `page_link`, so it does not appear in the
sidebar. `st.set_page_config()` must only be called once — in `app.py` — never in
individual pages.

I also extracted the old landing page content into a new `pages/0_Home.py`, keeping
`app.py` focused on routing.

---

## Print Colour: Separating Data from Labels

The original `print_options` table had a `technique_name` field that embedded colour
information in the string — for example `"Digital Transfer (FULLCOLOR)"` or
`"Tampo Print 2 Colors"`. This made the UI label logic awkward and the field unusable
for filtering or sorting by colour type.

### What the source data actually contains

- `technique_name`: a free-text label sometimes including `(FULLCOLOR)` as a suffix
- `max_colours`: an integer count of spot colours
- `colour_layers`: always 1 — useless for this purpose

The correct encoding is:

| Situation | `print_color` |
|---|---|
| Full colour / digital print | `-1` |
| Spot colour (e.g. 2 colours) | `2` |

### dbt changes in `int_mko_print_options.sql`

```sql
TRIM(REGEXP_REPLACE(technique_name, '\s*\(FULLCOLOR\)', '', 'g')) AS technique_name,

CASE
    WHEN technique_name ILIKE '%FULLCOLOR%' THEN -1::BIGINT
    ELSE CAST(max_colours AS BIGINT)
END AS print_color,
```

Two points worth noting:

1. **SQL aliases are not visible within the same SELECT list.** The CASE WHEN must test
   `technique_name` (the original column), not the cleaned alias produced by
   `REGEXP_REPLACE`. In DuckDB, as in standard SQL, a SELECT alias is only visible in
   `ORDER BY`, not in other expressions within the same SELECT.

2. **`REGEXP_REPLACE` with the `'g'` flag** replaces all occurrences, not just the
   first. The `\s*` before `\(FULLCOLOR\)` handles any trailing space before the
   parenthesis.

The UI helper function converts the integer to a display label:

```python
def _color_label(pc: int) -> str:
    return "Full Color" if pc == -1 else f"{pc} colour{'s' if pc != 1 else ''}"
```

---

## Variant Deduplication

Variants were appearing twice in the Bespoke UI. The root cause was in how dbt reads
from S3: the staging model uses a wildcard glob
`s3://supply-integration/mko/raw/product/*/variants.parquet`. With two pipeline runs
producing two date-partitioned directories, every variant row was present twice.

The fix is a `QUALIFY` deduplication at the intermediate layer:

```sql
-- int_mko_variants.sql
from {{ ref('stg_mko_variants') }}
qualify row_number() over (partition by product_ref, matnr order by 1) = 1
```

I applied this at the intermediate layer rather than staging to keep staging as a pure
representation of the raw data. The canonical `variants` mart inherits the deduplication
without any changes.

The same `QUALIFY` pattern already existed in `stg_mko_products.sql` for product-level
deduplication. The variants model was the only intermediate model missing it.

---

## Bespoke Catalogue Improvements

### Supplier and Product ID filters

Two new sidebar filters before the Category filter:

```python
suppliers = ["All"] + sorted(df["supplier"].dropna().unique().tolist())
selected_supplier = st.sidebar.selectbox("Supplier", suppliers)

product_id_search = st.sidebar.text_input("Product ID", placeholder="e.g. 4591")
```

The `product_id_search` uses `str.contains(case=False)` so partial IDs work.

### Stock display

`total_stock_qty` could be `None` / `NaN` in the DataFrame when a product has no stock
record. Displaying `None` in the table looks inconsistent — and deriving the `In stock`
boolean from a `None` value produces incorrect results.

Fix: normalise before building the display frame.

```python
display["total_stock_qty"] = display["total_stock_qty"].fillna(0).astype(int)
display["in_stock"] = display["total_stock_qty"] > 0
```

The checkbox column is then derived from the normalised integer, never from `None`.

---

## Shopping Basket

### Design

A basket needs to persist across page switches without a database. Streamlit's
`st.session_state` lives for the browser session — exactly the right scope. I created
`ui/basket.py` as a shared module imported by both `1_Catalog.py` and
`2_Configure_Order.py`.

```python
# basket.py
def add_to_basket(item: dict) -> None:
    if "bespoke_basket" not in st.session_state:
        st.session_state["bespoke_basket"] = []
    st.session_state["bespoke_basket"].append(item)

def show_basket() -> None:
    basket = st.session_state.get("bespoke_basket", [])
    if not basket:
        return
    ...
```

Both pages call `show_basket()` at the bottom of their script, so the basket is visible
on either page. `add_to_basket()` is called only from Configure Order when the user
clicks "Add to Basket".

### What gets stored

Each basket item is a plain dict with all the pricing components computed at add time:

```python
{
    "supplier":      "mko",
    "product_ref":   product_ref,
    "product_name":  product_name,
    "variant_matnr": str(variant_id),
    "variant_label": variant_labels[variant_idx],
    "quantity":      int(quantity),
    "prints_label":  prints_label,
    "carrier_name":  selected_carrier["carrier_name"],
    "supplier_ref":  supplier_ref,
    "unit_price":    unit_price,
    "product_total": product_total,
    "print_total":   print_total,
    "carrier_cost":  carrier_cost,
    "grand_total":   grand_total,
}
```

Prices are computed and stored at add time rather than recalculated on display — this
means the basket shows what the user saw when they clicked Add, even if quantity or
carrier changes while browsing.

### Basket display

Three columns: CSV export (primary button), price breakdown expander, Clear button.
The CSV export uses `pd.DataFrame(export_rows).to_csv(index=False).encode()` piped
to `st.download_button`.

---

## Catman Print Options Redesign

The previous Catman layout had print options alongside products in a two-column layout.
This was cramped and did not communicate the area → technique hierarchy clearly.

### Changes

**Layout:** products table is now full-width; print options are stacked below with
`st.divider()` separating them.

**Area-first selection:** instead of a flat list of all technique/area combinations,
the UI now groups by area (print position). The user selects an area first; technique
checkboxes appear indented beneath it.

```python
for areacode in opts_df["areacode"].unique():
    area_rows = opts_df[opts_df["areacode"] == areacode]
    area_name, w, h = ...
    area_selected = st.checkbox(f"**{area_name}** ({dims})", ...)
    if area_selected:
        for _, opt in area_rows.iterrows():
            _, tech_col = st.columns([1, 12])
            with tech_col:
                if st.checkbox(f"↳ {opt['technique_name']} ({color_label})", ...):
                    new_prints.append((opt["teccode"], areacode))
```

The `st.columns([1, 12])` trick creates a narrow invisible column on the left, pushing
the technique checkboxes right without using `st.markdown` padding hacks.

**Qty Code in the print panel:** a `st.text_input` for the quantity code lives in the
print configuration section, not only in the products table. This lets the user adjust
the code while reviewing print options without scrolling back up.

---

## The Changes Made

| File | Change |
|---|---|
| `ui/app.py` | Rewritten: `st.navigation(position="hidden")` + explicit `page_link` sidebar |
| `ui/pages/0_Home.py` | New — extracted landing page content from `app.py` |
| `ui/pages/1_Catalog.py` | Supplier + Product ID filters; stock normalisation; stacked product detail; `show_basket()` |
| `ui/pages/2_Configure_Order.py` | `print_color` in print options query; `_color_label()` helper; "Add to Basket" button; `show_basket()` |
| `ui/pages/3_Catman.py` | Stacked layout; area-first print selection; technique indentation; Qty Code in print panel |
| `ui/basket.py` | New — `add_to_basket()` + `show_basket()` shared module |
| `dbt_project/models/intermediate/int_mko_print_options.sql` | `print_color BIGINT` derived column; `REGEXP_REPLACE` to strip `(FULLCOLOR)` from technique names |
| `dbt_project/models/intermediate/int_mko_variants.sql` | `QUALIFY ROW_NUMBER()` deduplication |

---

## What I Should Be Able to Explain After Day 8

- How `st.navigation(position="hidden")` works and why `st.set_page_config()` must
  only appear in `app.py`
- Why `st.switch_page()` requires a page to be registered even if it has no sidebar link
- Why SQL aliases are not available within the same SELECT list, and how this affects
  CASE WHEN expressions that reference a transformed column
- The `REGEXP_REPLACE(col, pattern, '', 'g')` pattern for in-place string cleaning in dbt
- Why QUALIFY deduplication belongs at the intermediate layer rather than staging
- Why basket prices should be computed at add time rather than at display time
- The `st.columns([1, N])` visual indentation pattern for nested UI elements
