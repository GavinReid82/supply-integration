import re

import pandas as pd
import streamlit as st

from db import query


@st.cache_data
def load_templates() -> pd.DataFrame:
    return query(
        "SELECT template_name, template_category, quantity_code, catalog_category FROM pcm_templates ORDER BY template_category, template_name"
    )


@st.cache_data
def load_catalog() -> pd.DataFrame:
    return query(
        """SELECT product_ref, product_name, category, subcategory, supplier, image_url
           FROM catalog ORDER BY product_name"""
    )


@st.cache_data
def load_print_options(product_ref: str, supplier: str) -> pd.DataFrame:
    if supplier == "All":
        return query(
            """SELECT DISTINCT teccode, technique_name, print_color, areacode, area_name, area_width_cm, area_height_cm
               FROM print_options WHERE product_ref = ? ORDER BY area_name, technique_name""",
            [product_ref],
        )
    return query(
        """SELECT teccode, technique_name, print_color, areacode, area_name, area_width_cm, area_height_cm
           FROM print_options WHERE product_ref = ? AND supplier = ? ORDER BY area_name, technique_name""",
        [product_ref, supplier],
    )


def auto_slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]", "", name).lower()


def sk(field: str, ref: str) -> str:
    return f"catman_{field}_{ref}"


# ── Header ────────────────────────────────────────────────────────────────────
st.title("📊 Category Management")
if st.button("← Home"):
    st.switch_page("pages/0_Home.py")

st.divider()

# ── Config + filters (sidebar) ────────────────────────────────────────────────
templates_df = load_templates()
catalog_df = load_catalog()

st.sidebar.title("Session Setup")

supplier = st.sidebar.selectbox("Supplier", ["All", "mko", "xdc"])

# Filter catalog to the selected supplier (or keep all)
supplier_catalog = catalog_df if supplier == "All" else catalog_df[catalog_df["supplier"] == supplier]

st.sidebar.divider()
st.sidebar.subheader("Product Filter")

cats = ["All"] + sorted(supplier_catalog["category"].dropna().unique().tolist())
sel_cat = st.sidebar.selectbox("Category", cats)
filtered = supplier_catalog.copy()
if sel_cat != "All":
    filtered = filtered[filtered["category"] == sel_cat]

subcats = ["All"] + sorted(filtered["subcategory"].dropna().unique().tolist())
sel_sub = st.sidebar.selectbox("Sub-category", subcats)
if sel_sub != "All":
    filtered = filtered[filtered["subcategory"] == sel_sub]

search = st.sidebar.text_input("Search name")
if search:
    filtered = filtered[filtered["product_name"].str.contains(search, case=False, na=False)]

st.sidebar.divider()
st.sidebar.subheader("PCM Template")

# Narrow the template list to those whose catalog_category matches the selected
# product category. Falls back to all templates when no match exists.
if sel_cat != "All":
    cat_matched = templates_df[templates_df["catalog_category"] == sel_cat]
    tmpl_pool = cat_matched if not cat_matched.empty else templates_df
else:
    tmpl_pool = templates_df

tmpl_cat_opts = ["All"] + sorted(tmpl_pool["template_category"].unique().tolist())
tmpl_cat = st.sidebar.selectbox("Template Category", tmpl_cat_opts, key="tmpl_cat")
filtered_tmpls = tmpl_pool if tmpl_cat == "All" else tmpl_pool[tmpl_pool["template_category"] == tmpl_cat]

template = st.sidebar.selectbox("PCM Template", ["(select a template)"] + filtered_tmpls["template_name"].tolist())
qty_row = templates_df[templates_df["template_name"] == template]
default_qty_code = qty_row.iloc[0]["quantity_code"] if not qty_row.empty else ""

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
n_selected = sum(
    1 for ref in supplier_catalog["product_ref"]
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
        "Image":     filtered["image_url"].values,
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
            "Image":     st.column_config.ImageColumn("Image", width="small"),
            "Qty Code":  st.column_config.TextColumn("Qty Code"),
        },
        key=f"catman_editor_{sel_cat}_{sel_sub}_{search}_{template}",
    )

    for i, ref in enumerate(filtered["product_ref"].values):
        st.session_state[sk("sel",  ref)] = bool(edited.iloc[i]["Selected"])
        st.session_state[sk("slug", ref)] = str(edited.iloc[i]["Slug"] or "")
        st.session_state[sk("qty",  ref)] = str(edited.iloc[i]["Qty Code"] or "")

# ── Print options (stacked below products) ────────────────────────────────────
st.divider()
st.subheader("Print Options")

all_selected_refs = [
    ref for ref in supplier_catalog["product_ref"]
    if st.session_state.get(sk("sel", ref), False)
]

if not all_selected_refs:
    st.info("Select products above, then configure their print options here.")
else:
    ref_to_name = dict(zip(supplier_catalog["product_ref"], supplier_catalog["product_name"]))
    configure_ref = st.selectbox(
        "Configure print for:",
        all_selected_refs,
        format_func=lambda r: ref_to_name.get(r, r),
    )

    if configure_ref:
        opts_df = load_print_options(configure_ref, supplier)
        current = st.session_state[sk("prints", configure_ref)]

        new_qty = st.text_input(
            "Qty Code",
            value=st.session_state.get(sk("qty", configure_ref), ""),
            key=f"qty_input_{configure_ref}",
        )
        st.session_state[sk("qty", configure_ref)] = new_qty

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
            st.caption("Select print positions, then choose which techniques to offer for each.")

            # Group by area: position first, techniques second
            for areacode in opts_df["areacode"].unique():
                area_rows = opts_df[opts_df["areacode"] == areacode]
                area_name = area_rows.iloc[0]["area_name"]
                w = area_rows.iloc[0]["area_width_cm"]
                h = area_rows.iloc[0]["area_height_cm"]
                dims = f"{w:.0f}×{h:.0f} cm" if (pd.notna(w) and pd.notna(h)) else "—"

                area_has_selection = any(ac == areacode for (_, ac) in current)

                area_selected = st.checkbox(
                    f"**{area_name}** ({dims})",
                    value=area_has_selection,
                    key=f"area_{configure_ref}_{areacode}",
                )

                if area_selected:
                    for row_idx, (_, opt) in enumerate(area_rows.iterrows()):
                        key_pair = (opt["teccode"], areacode)
                        pc = int(opt["print_color"])
                        color_label = "Full Color" if pc == -1 else f"{pc} colour{'s' if pc != 1 else ''}"
                        _, tech_col = st.columns([1, 12])
                        with tech_col:
                            if st.checkbox(
                                f"↳ {opt['technique_name']} ({color_label})",
                                value=key_pair in current,
                                key=f"opt_{configure_ref}_{opt['teccode']}_{areacode}_{row_idx}",
                            ):
                                new_prints.append(key_pair)

        st.session_state[sk("prints", configure_ref)] = new_prints

# ── Validation + export ────────────────────────────────────────────────────────
st.divider()

all_selected_refs = [
    ref for ref in supplier_catalog["product_ref"]
    if st.session_state.get(sk("sel", ref), False)
]

if not all_selected_refs:
    st.caption("No products selected yet.")
else:
    ref_to_name = dict(zip(supplier_catalog["product_ref"], supplier_catalog["product_name"]))

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
        export_rows = []
        for ref in all_selected_refs:
            slug      = st.session_state[sk("slug", ref)]
            qty_code  = st.session_state[sk("qty",  ref)]
            prints    = st.session_state[sk("prints", ref)]

            if not prints:
                continue

            opts_df = load_print_options(ref, supplier)
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
        filename  = f"catman_{supplier.lower()}_{tmpl_slug}.csv"

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
