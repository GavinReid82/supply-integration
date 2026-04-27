import re
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from db import query

st.set_page_config(page_title="Category Management", page_icon="📊", layout="wide")

QUANTITY_CODES_PATH = Path(__file__).parent.parent.parent / "business_logic" / "quantity_codes.yaml"


@st.cache_data
def load_qty_config() -> dict:
    with open(QUANTITY_CODES_PATH) as f:
        return yaml.safe_load(f)


@st.cache_data
def load_catalog() -> pd.DataFrame:
    return query(
        """SELECT product_ref, product_name, category_name_1, category_name_2, supplier
           FROM catalog ORDER BY product_name"""
    )


@st.cache_data
def load_print_options(product_ref: str) -> pd.DataFrame:
    return query(
        """SELECT teccode, technique_name, areacode, area_name, area_width_cm, area_height_cm
           FROM print_options WHERE product_ref = ? ORDER BY technique_name, area_name""",
        [product_ref],
    )


def auto_slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]", "", name).lower()


def sk(field: str, ref: str) -> str:
    return f"catman_{field}_{ref}"


# ── Header ────────────────────────────────────────────────────────────────────
st.title("📊 Category Management")
if st.button("← Home"):
    st.switch_page("app.py")

st.divider()

# ── Config + filters (sidebar) ────────────────────────────────────────────────
qty_config = load_qty_config()
catalog_df = load_catalog()

st.sidebar.title("Session Setup")

supplier = st.sidebar.selectbox("Supplier", ["mko"])
templates = list(qty_config.get(supplier, {}).keys())
template = st.sidebar.selectbox("PCM Template", ["(select a template)"] + templates)
default_qty_code = qty_config.get(supplier, {}).get(template, "")

st.sidebar.divider()
st.sidebar.title("Product Filter")

cats = ["All"] + sorted(catalog_df["category_name_1"].dropna().unique().tolist())
sel_cat = st.sidebar.selectbox("Category", cats)
filtered = catalog_df.copy()
if sel_cat != "All":
    filtered = filtered[filtered["category_name_1"] == sel_cat]

subcats = ["All"] + sorted(filtered["category_name_2"].dropna().unique().tolist())
sel_sub = st.sidebar.selectbox("Sub-category", subcats)
if sel_sub != "All":
    filtered = filtered[filtered["category_name_2"] == sel_sub]

search = st.sidebar.text_input("Search name")
if search:
    filtered = filtered[filtered["product_name"].str.contains(search, case=False, na=False)]

# ── Initialise session state for newly-visible products ───────────────────────
for _, row in filtered.iterrows():
    ref = row["product_ref"]
    if sk("sel", ref) not in st.session_state:
        st.session_state[sk("sel", ref)] = False
    if sk("slug", ref) not in st.session_state:
        st.session_state[sk("slug", ref)] = auto_slug(row["product_name"])
    if sk("qty", ref) not in st.session_state:
        st.session_state[sk("qty", ref)] = default_qty_code
    if sk("prints", ref) not in st.session_state:
        st.session_state[sk("prints", ref)] = []

# ── Product table ─────────────────────────────────────────────────────────────
left, right = st.columns([3, 2])

with left:
    n_selected = sum(
        1 for ref in catalog_df["product_ref"]
        if st.session_state.get(sk("sel", ref), False)
    )
    st.subheader(f"Products — {len(filtered):,} shown · {n_selected:,} selected")

    if filtered.empty:
        st.info("No products match the current filters.")
    elif len(filtered) > 300:
        st.warning(f"{len(filtered):,} products — narrow the filter to browse.")
    else:
        editor_df = pd.DataFrame({
            "Selected":  [st.session_state[sk("sel",  r)] for r in filtered["product_ref"]],
            "Product":   filtered["product_name"].values,
            "Ref":       filtered["product_ref"].values,
            "Slug":      [st.session_state[sk("slug", r)] for r in filtered["product_ref"]],
            "Qty Code":  [st.session_state.get(sk("qty", r)) or default_qty_code for r in filtered["product_ref"]],
        })

        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Selected":  st.column_config.CheckboxColumn("✓", width="small"),
                "Product":   st.column_config.TextColumn("Product", disabled=True),
                "Ref":       st.column_config.TextColumn("Ref", disabled=True, width="small"),
                "Slug":      st.column_config.TextColumn("Slug"),
                "Qty Code":  st.column_config.TextColumn("Qty Code"),
            },
            key=f"catman_editor_{sel_cat}_{sel_sub}_{search}_{template}",
        )

        # Sync edits back to individual session_state keys
        for i, ref in enumerate(filtered["product_ref"].values):
            st.session_state[sk("sel",  ref)] = bool(edited.iloc[i]["Selected"])
            st.session_state[sk("slug", ref)] = str(edited.iloc[i]["Slug"] or "")
            st.session_state[sk("qty",  ref)] = str(edited.iloc[i]["Qty Code"] or "")

# ── Print options panel ────────────────────────────────────────────────────────
with right:
    st.subheader("Print Options")

    # All currently selected products (across all filters)
    all_selected_refs = [
        ref for ref in catalog_df["product_ref"]
        if st.session_state.get(sk("sel", ref), False)
    ]

    if not all_selected_refs:
        st.info("Select products on the left, then configure their print options here.")
    else:
        ref_to_name = dict(zip(catalog_df["product_ref"], catalog_df["product_name"]))
        configure_ref = st.selectbox(
            "Configure print for:",
            all_selected_refs,
            format_func=lambda r: ref_to_name.get(r, r),
        )

        if configure_ref:
            opts_df = load_print_options(configure_ref)
            current = st.session_state[sk("prints", configure_ref)]

            st.caption("Tick the print options to offer for this product (dimensions pre-filled to maximum).")

            new_prints = []

            # "No print" row — always available, for sample requests
            no_key = ("no", "no")
            if st.checkbox(
                "No print (samples only)",
                value=no_key in current,
                key=f"noprint_{configure_ref}",
            ):
                new_prints.append(no_key)

            if opts_df.empty:
                st.caption("No print options found for this product.")
            else:
                for _, opt in opts_df.iterrows():
                    key = (opt["teccode"], opt["areacode"])
                    w = opt["area_width_cm"]
                    h = opt["area_height_cm"]
                    dims = f"{w:.0f}×{h:.0f} cm" if (w or h) else "—"
                    label = f"{opt['technique_name']} — {opt['area_name']} ({dims})"
                    if st.checkbox(
                        label,
                        value=key in current,
                        key=f"opt_{configure_ref}_{opt['teccode']}_{opt['areacode']}",
                    ):
                        new_prints.append(key)

            st.session_state[sk("prints", configure_ref)] = new_prints

# ── Validation + export ────────────────────────────────────────────────────────
st.divider()

all_selected_refs = [
    ref for ref in catalog_df["product_ref"]
    if st.session_state.get(sk("sel", ref), False)
]

if not all_selected_refs:
    st.caption("No products selected yet.")
else:
    ref_to_name = dict(zip(catalog_df["product_ref"], catalog_df["product_name"]))

    errors = []
    for ref in all_selected_refs:
        name = ref_to_name.get(ref, ref)
        if not st.session_state.get(sk("qty", ref), "").strip():
            errors.append(f"**{name}** — missing quantity code")
        if not st.session_state.get(sk("prints", ref)):
            errors.append(f"**{name}** — no print option selected (add at least one, or tick 'No print')")

    if errors:
        st.subheader("Validation errors")
        for e in errors:
            st.error(e, icon="⚠️")
    else:
        # Build export rows
        export_rows = []
        for ref in all_selected_refs:
            slug      = st.session_state[sk("slug", ref)]
            qty_code  = st.session_state[sk("qty",  ref)]
            prints    = st.session_state[sk("prints", ref)]

            if not prints:
                continue

            opts_df = load_print_options(ref)
            opts_map = {
                (r["teccode"], r["areacode"]): r
                for _, r in opts_df.iterrows()
            }

            for (teccode, areacode) in prints:
                if teccode == "no":
                    export_rows.append({
                        "product_ref":     ref,
                        "product_name":    ref_to_name.get(ref, ref),
                        "slug":            slug,
                        "quantity_code":   qty_code,
                        "pcm_template":    template if template != "(select a template)" else "",
                        "print_technique": "no",
                        "print_position":  "no",
                        "width_cm":        "",
                        "height_cm":       "",
                    })
                elif (teccode, areacode) in opts_map:
                    opt = opts_map[(teccode, areacode)]
                    export_rows.append({
                        "product_ref":     ref,
                        "product_name":    ref_to_name.get(ref, ref),
                        "slug":            slug,
                        "quantity_code":   qty_code,
                        "pcm_template":    template if template != "(select a template)" else "",
                        "print_technique": opt["technique_name"],
                        "print_position":  opt["area_name"],
                        "width_cm":        opt["area_width_cm"],
                        "height_cm":       opt["area_height_cm"],
                    })

        export_df = pd.DataFrame(export_rows)
        csv_bytes = export_df.to_csv(index=False).encode()

        tmpl_slug = template.replace(" ", "_").replace("(", "").replace(")", "") if template != "(select a template)" else "export"
        filename  = f"catman_{supplier}_{tmpl_slug}.csv"

        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            st.download_button(
                "⬇️ Export CSV",
                data=csv_bytes,
                file_name=filename,
                mime="text/csv",
                type="primary",
            )
        with col_info:
            st.caption(
                f"{len(all_selected_refs)} products · "
                f"{len(export_rows)} print configurations · "
                f"downloading as `{filename}`"
            )

        with st.expander("Preview export"):
            st.dataframe(export_df, use_container_width=True, hide_index=True)
