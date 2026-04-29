import pandas as pd
import streamlit as st

from basket import show_basket
from db import query


@st.cache_data
def load_catalog() -> pd.DataFrame:
    return query("SELECT * FROM catalog ORDER BY product_name")


@st.cache_data
def load_prices(product_ref: str) -> pd.DataFrame:
    return query(
        "SELECT tier, min_qty, unit_price FROM prices WHERE product_ref = ? ORDER BY tier",
        [product_ref],
    )


@st.cache_data
def load_variants(product_ref: str) -> pd.DataFrame:
    return query(
        "SELECT variant_id, colour_name, colour_code, size FROM variants WHERE product_ref = ? ORDER BY variant_id",
        [product_ref],
    )


df = load_catalog()

# ── Sidebar filters ──────────────────────────────────────────────────────────
st.sidebar.title("Filters")

suppliers = ["All"] + sorted(df["supplier"].dropna().unique().tolist())
selected_supplier = st.sidebar.selectbox("Supplier", suppliers)

product_id_search = st.sidebar.text_input("Product ID", placeholder="e.g. 4591")

categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
selected_cat = st.sidebar.selectbox("Category", categories)

sub_options = ["All"]
if selected_cat != "All":
    subs = df[df["category"] == selected_cat]["subcategory"].dropna().unique().tolist()
    sub_options += sorted(subs)
selected_sub = st.sidebar.selectbox("Sub-category", sub_options)

in_stock_only = st.sidebar.checkbox("In stock now only", value=False)

# ── Apply filters ────────────────────────────────────────────────────────────
filtered = df.copy()
if selected_supplier != "All":
    filtered = filtered[filtered["supplier"] == selected_supplier]
if product_id_search:
    filtered = filtered[filtered["product_ref"].str.contains(product_id_search, case=False, na=False)]
if selected_cat != "All":
    filtered = filtered[filtered["category"] == selected_cat]
if selected_sub != "All":
    filtered = filtered[filtered["subcategory"] == selected_sub]
if in_stock_only:
    filtered = filtered[filtered["total_stock_qty"].fillna(0) > 0]

# ── Header ───────────────────────────────────────────────────────────────────
st.title("📦 Product Catalog")

# ── Metrics ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
col1.metric("Products shown", f"{len(filtered):,}")
col2.metric("In stock now", f"{(filtered['total_stock_qty'].fillna(0) > 0).sum():,}")

st.divider()

# ── Products table ────────────────────────────────────────────────────────────
st.subheader("Products")

display = filtered[[
    "product_ref", "product_name", "product_type",
    "category", "subcategory",
    "min_unit_price", "total_stock_qty", "min_order_qty",
]].copy()

display["total_stock_qty"] = display["total_stock_qty"].fillna(0).astype(int)
display["in_stock"] = display["total_stock_qty"] > 0

display = display.rename(columns={
    "product_ref":     "Ref",
    "product_name":    "Name",
    "product_type":    "Type",
    "category": "Category",
    "subcategory": "Sub-category",
    "min_unit_price":  "Price (€)",
    "total_stock_qty": "Stock",
    "min_order_qty":   "MOQ",
    "in_stock":        "In stock",
})

selected_rows = st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "In stock": st.column_config.CheckboxColumn("In stock", disabled=True),
    },
)

# ── Product detail (stacked below table) ─────────────────────────────────────
st.divider()

selected_indices = selected_rows.selection.get("rows", [])

if selected_indices:
    row = filtered.iloc[selected_indices[0]]

    col_img, col_info = st.columns([1, 3])

    with col_img:
        if row.get("image_url"):
            st.image(row["image_url"], width=280)

    with col_info:
        st.markdown(f"### {row['product_name']}")
        st.markdown(f"**Ref:** {row['product_ref']}  |  **Type:** {row['product_type'] or '—'}")
        st.markdown(f"**Category:** {row['category'] or '—'} › {row['subcategory'] or '—'}")

        st.divider()

        prices_df = load_prices(row["product_ref"])
        if not prices_df.empty:
            if prices_df["unit_price"].nunique() == 1:
                st.markdown(f"**Price:** €{float(prices_df.iloc[0]['unit_price']):.2f}")
            else:
                st.markdown("**Volume pricing:**")
                price_display = prices_df.copy()
                price_display["Quantity"] = price_display["min_qty"].abs().apply(
                    lambda x: f"Up to {int(x):,} units"
                )
                price_display["Unit price"] = price_display["unit_price"].apply(
                    lambda x: f"€{float(x):.2f}"
                )
                st.dataframe(
                    price_display[["Quantity", "Unit price"]],
                    use_container_width=True,
                    hide_index=True,
                )

        stock_qty = int(row["total_stock_qty"]) if pd.notna(row["total_stock_qty"]) and row["total_stock_qty"] else 0
        c1, c2 = st.columns(2)
        c1.metric("Stock qty", f"{stock_qty:,}")
        c2.metric("MOQ", str(row["min_order_qty"] or "—"))

        if row.get("composition"):
            st.markdown(f"**Material:** {row['composition']}")

        dims = [
            f"L {row['item_length_mm']:.0f}mm" if pd.notna(row["item_length_mm"]) else None,
            f"W {row['item_width_mm']:.0f}mm"  if pd.notna(row["item_width_mm"])  else None,
            f"H {row['item_height_mm']:.0f}mm" if pd.notna(row["item_height_mm"]) else None,
        ]
        dims = [d for d in dims if d]
        if dims:
            st.markdown(f"**Dimensions:** {' × '.join(dims)}")

        st.divider()
        st.markdown("**Variants**")
        variants_df = load_variants(row["product_ref"])
        if not variants_df.empty:
            st.dataframe(variants_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No variants found.")

        st.divider()
        if st.button("🖨️ Configure Order →", use_container_width=True, type="primary"):
            st.session_state["order_product"] = row.to_dict()
            st.switch_page("pages/2_Configure_Order.py")

else:
    st.info("Click a row to see product details, image, and variants.")

# ── Basket ────────────────────────────────────────────────────────────────────
show_basket()
