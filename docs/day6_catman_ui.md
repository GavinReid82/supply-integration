# Day 6 — Category Management UI

## What I Did

I built a Category Management (catman) UI to replace a Google Sheets workflow. The
catman team selects products by PCM template, assigns slugs and quantity codes,
configures print options, and exports a CSV that feeds the website product catalogue.

I also added a landing page to separate the two workflows — Bespoke and Category
Management — and moved the product catalogue to its own page.

---

## Context: What the Google Sheets Workflow Did

The catman team works in a Google Sheet (`supply_prod__mko_pcm.xlsx`) with three
key tabs:

- **product tab** — one row per product, with columns for `is_selected`, `slug`,
  `quantity_code`, and `pcm_template`. Catman ticks boxes and fills in values.
- **print_option tab** — one row per product × print technique × area, with an
  `is_selected` flag. Catman ticks which print options to offer.
- **pcm_template_print_technique_quantity tab** — defines which print techniques are
  valid per template, plus their min/max quantities.

The workflow was slow because: slugs were typed manually (a formula already automates
them), quantity codes were typed from memory (they follow per-template rules codified
nowhere), and print dimensions were entered by hand (the API already provides max
dimensions). The UI automates all three.

---

## Core Concepts

### Streamlit multipage apps and `st.switch_page`

Streamlit multipage apps use a `pages/` directory relative to the main script. Each
`.py` file in `pages/` becomes a separate page. `app.py` at the root is the entry
point — the landing page.

Navigation between pages uses `st.switch_page()`:

```python
if st.button("Open Catman"):
    st.switch_page("pages/3_Catman.py")
```

State that must persist across page switches — like which product the Bespoke team
selected — is stored in `st.session_state`, a dictionary that survives navigation.

---

### `st.data_editor` for editable tables

`st.dataframe` is read-only. `st.data_editor` renders an interactive table where users
can tick checkboxes, type into text cells, and select from dropdowns. The modified
DataFrame is returned on each rerun.

```python
edited = st.data_editor(
    editor_df,
    column_config={
        "Selected": st.column_config.CheckboxColumn("✓", width="small"),
        "Slug":     st.column_config.TextColumn("Slug"),
        "Qty Code": st.column_config.TextColumn("Qty Code"),
    },
    key="catman_editor",
)
```

The `key` parameter links the widget to Streamlit's internal widget state, so edits
persist between reruns without explicit session state management — as long as the
underlying data passed to the widget does not change. When the data changes (e.g., a
filter is applied), the widget resets unless its state has been persisted elsewhere.

---

### Per-product session state keys for persistence across filters

When the user applies a category filter, the product table re-renders with a new set
of rows. Any edits to products that are now filtered out would be lost if the widget
were the only place they lived.

The solution is to store each product's editable fields in individual session state
entries, keyed by product reference:

```python
st.session_state["catman_sel_4049"]    = True
st.session_state["catman_slug_4049"]   = "herabag"
st.session_state["catman_qty_4049"]    = "1-1:1,5-50:5,..."
st.session_state["catman_prints_4049"] = [("SCR", "area1")]
```

On each render the table is built from these keys, so previous edits appear. After
`data_editor` returns, the edited values are written back to the keys. Products that
are filtered out are not synced in that render, but their keys survive in session state
until the browser session ends.

The `data_editor` key is made dynamic — tied to the current filter state — so switching
filters creates a new widget instance (and therefore re-initialises from session state),
rather than re-using stale widget state from a different filter combination.

---

### Quantity codes from a YAML config

Quantity codes encode which quantities catman offers to customers, in a compact format:
`min-max:step,min-max:step,...`

For example, `1-1:1,5-50:5,60-100:10,125-500:25` expands to: 1, 5, 10, 15, ..., 50,
60, 70, ..., 100, 125, 150, ..., 500.

Catman was applying these from memory, following per-template rules that existed nowhere
in writing. By extracting the most common quantity code per template from the live PCM
Excel data (inspected with `openpyxl`), I could codify them:

```yaml
# business_logic/quantity_codes.yaml
mko:
  "Bag - DrawstringV3":  "1-1:1,5-50:5,60-100:10,100-500:50,500-1000:100,..."
  "Drinkware - BottleV2": "1-1:1,5-50:5,50-100:10,100-250:25,250-500:25,..."
  # 33 templates total
```

The UI reads this YAML at startup (`@st.cache_data`) and pre-populates the Qty Code
column when a template is selected. Catman can still edit individual rows — the config
is a sensible default, not a hard constraint.

The path to the YAML is resolved relative to the page file:

```python
QUANTITY_CODES_PATH = Path(__file__).parent.parent.parent / "business_logic" / "quantity_codes.yaml"
```

This works regardless of the working directory when Streamlit is launched.

---

### Hard validation before export

The PCM data has two hard rules drawn from the Google Sheet's validation formulas:

1. Every selected product must have a quantity code.
2. Every selected product must have at least one print option selected. "No print" (for
   sample requests) counts as valid — it is represented as `print_technique=no` in the
   output, matching the existing PCM convention.

The UI blocks the export button and shows per-product error messages if either rule is
violated. This replaces the Sheet's formula-based "OK"/"NOT" validation column.

---

## The Changes Made

| File | Change |
|---|---|
| `ui/app.py` | Converted from catalogue to landing page (two workflow buttons) |
| `ui/pages/1_Catalog.py` | New — catalogue code moved from `app.py` |
| `ui/pages/2_Configure_Order.py` | Updated back-links to point to `pages/1_Catalog.py` |
| `ui/pages/3_Catman.py` | New — full Category Management UI |
| `business_logic/quantity_codes.yaml` | New — 33 MKO template quantity code defaults |

### Catman page features

- **Sidebar:** supplier selector (MKO for now), PCM template selector (drives quantity
  code defaults), category / sub-category / name filters
- **Product table:** `st.data_editor` with editable Selected checkbox, Slug
  (auto-generated from product name with `re.sub(r'[^0-9a-zA-Z]', '', name).lower()`),
  and Qty Code (pre-filled from template config); state persisted per-product so edits
  survive filter changes
- **Print options panel:** for any selected product, shows all available print techniques
  and areas (max dimensions pre-filled from the `print_options` table) as checkboxes;
  "No print (samples only)" always available
- **Validation:** per-product error messages that block export until every selected
  product has a quantity code and at least one print option ticked
- **Export:** `st.download_button` producing a CSV with one row per product × print
  option — columns: `product_ref`, `product_name`, `slug`, `quantity_code`,
  `pcm_template`, `print_technique`, `print_position`, `width_cm`, `height_cm`

---

## Issues I Hit

### `data_editor` state vs filter interaction

**What happened:** When changing category filters, the `data_editor` re-renders with
a new set of rows. With a fixed widget key, the editor preserved stale widget-internal
state from the previous filter. With a fully dynamic key, the editor reset and lost
the user's edits.

**Fix:** Used a dynamic key tied to the filter combination
(`key=f"catman_editor_{sel_cat}_{sel_sub}_{search}"`) so each unique filter
combination has its own widget instance. Edits are synced to individual session state
keys after every render, so values survive when a product is temporarily filtered out.

**Lesson:** In Streamlit, widget state (managed by `key`) and application state
(managed by `st.session_state`) are separate concerns. For data that must survive
widget resets or filter changes, write it explicitly to `st.session_state` — do not
rely on the widget to hold it.

### PCM-derived quantity code variants

**What happened:** After extracting quantity codes from the live PCM Excel data, some
templates had variation across products (e.g. "Bag - DrawstringV3" had two different
codes in use). The YAML config needed to pick one default without losing precision.

**Fix:** Used the most common code per template (by product count). The config is a
pre-fill, not a fixed value — catman can override per row for the exceptions.

---

## What I Should Be Able to Explain After Day 6

- What Streamlit multipage apps are and how `st.switch_page` and `st.session_state` work
- What `st.data_editor` is and how it differs from `st.dataframe`
- Why per-product session state keys are needed when filters change
- What the `key` parameter on a Streamlit widget controls
- What quantity codes encode and how the YAML config automates pre-fill
- What the PCM template workflow is and which steps the UI now replaces
- Why "no print" is a valid print option in the PCM convention (sample requests)
- How the export validation rules map to the original Google Sheet validation formulas
