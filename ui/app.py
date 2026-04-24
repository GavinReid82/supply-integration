import os

import duckdb
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="MKO Product Catalog",
    page_icon="📦",
    layout="wide",
)

DB_PATH = os.getenv("DUCKDB_PATH", "data/supply_integration.duckdb")


def query(sql: str, params: list = None) -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


@st.cache_data
def load_catalog() -> pd.DataFrame:
    return query("SELECT * FROM mko_catalog ORDER BY product_name")


@st.cache_data
def load_prices(product_ref: str) -> pd.DataFrame:
    return query(
        "SELECT tier, min_qty, unit_price FROM mko_prices WHERE product_ref = ? ORDER BY tier",
        [product_ref],
    )


@st.cache_data
def load_variants(product_ref: str) -> pd.DataFrame:
    return query(
        "SELECT sku_code, colour_name, colour_code, size FROM mko_variants WHERE product_ref = ? ORDER BY sku_code",
        [product_ref],
    )


df = load_catalog()

# ── Sidebar filters ──────────────────────────────────────────────────────────
st.sidebar.title("Filters")

categories = ["All"] + sorted(df["category_name_1"].dropna().unique().tolist())
selected_cat = st.sidebar.selectbox("Category", categories)

sub_options = ["All"]
if selected_cat != "All":
    subs = df[df["category_name_1"] == selected_cat]["category_name_2"].dropna().unique().tolist()
    sub_options += sorted(subs)
selected_sub = st.sidebar.selectbox("Sub-category", sub_options)

in_stock_only = st.sidebar.checkbox("In stock now only", value=False)

price_min = float(df["min_unit_price"].min())
price_max = float(df["min_unit_price"].max())
price_range = st.sidebar.slider(
    "Price range (€)",
    min_value=price_min,
    max_value=price_max,
    value=(price_min, price_max),
    step=0.10,
)

# ── Apply filters ────────────────────────────────────────────────────────────
filtered = df.copy()
if selected_cat != "All":
    filtered = filtered[filtered["category_name_1"] == selected_cat]
if selected_sub != "All":
    filtered = filtered[filtered["category_name_2"] == selected_sub]
if in_stock_only:
    filtered = filtered[filtered["in_stock_now"] == True]
filtered = filtered[
    (filtered["min_unit_price"] >= price_range[0]) &
    (filtered["min_unit_price"] <= price_range[1])
]

# ── Header ───────────────────────────────────────────────────────────────────
st.title("📦 Makito Product Catalog")
st.caption(f"Live data from Makito API via AWS S3 → dbt → DuckDB")

# ── Metrics ──────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Products shown", f"{len(filtered):,}")
col2.metric("In stock now", f"{filtered['in_stock_now'].sum():,}")
col3.metric("Min price", f"€{filtered['min_unit_price'].min():.2f}" if not filtered.empty else "—")
col4.metric("Max price", f"€{filtered['min_unit_price'].max():.2f}" if not filtered.empty else "—")

st.divider()

# ── Main layout: table + detail panel ────────────────────────────────────────
left, right = st.columns([2, 1])

with left:
    st.subheader("Products")

    display = filtered[[
        "product_ref", "product_name", "product_type",
        "category_name_1", "category_name_2",
        "min_unit_price", "total_stock_qty", "in_stock_now",
        "min_order_qty",
    ]].rename(columns={
        "product_ref":      "Ref",
        "product_name":     "Name",
        "product_type":     "Type",
        "category_name_1":  "Category",
        "category_name_2":  "Sub-category",
        "min_unit_price":   "Price (€)",
        "total_stock_qty":  "Stock",
        "in_stock_now":     "In stock",
        "min_order_qty":    "MOQ",
    })

    selected_rows = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

with right:
    st.subheader("Product detail")

    selected_indices = selected_rows.selection.get("rows", [])

    if selected_indices:
        row = filtered.iloc[selected_indices[0]]

        if row.get("imagemain"):
            st.image(row["imagemain"], width=280)

        st.markdown(f"### {row['product_name']}")
        st.markdown(f"**Ref:** {row['product_ref']}  |  **Type:** {row['product_type'] or '—'}")
        st.markdown(f"**Category:** {row['category_name_1'] or '—'} › {row['category_name_2'] or '—'}")

        st.divider()

        # Pricing
        prices_df = load_prices(row["product_ref"])
        if not prices_df.empty:
            if prices_df["unit_price"].nunique() == 1:
                st.markdown(f"**Price:** €{float(prices_df.iloc[0]['unit_price']):.2f}")
            else:
                st.markdown("**Volume pricing:**")
                price_display = prices_df.copy()
                price_display["Quantity"] = price_display["min_qty"].abs().apply(lambda x: f"Up to {int(x):,} units")
                price_display["Unit price"] = price_display["unit_price"].apply(lambda x: f"€{float(x):.2f}")
                st.dataframe(price_display[["Quantity", "Unit price"]], use_container_width=True, hide_index=True)

        c1, c2 = st.columns(2)
        c1.metric("Stock qty", f"{int(row['total_stock_qty']):,}" if row['total_stock_qty'] else "—")
        c2.metric("MOQ", str(row['min_order_qty'] or '—'))

        if row.get("composition"):
            st.markdown(f"**Material:** {row['composition']}")

        dims = [
            f"L {row['item_length_mm']:.0f}mm" if pd.notna(row['item_length_mm']) else None,
            f"W {row['item_width_mm']:.0f}mm"  if pd.notna(row['item_width_mm'])  else None,
            f"H {row['item_height_mm']:.0f}mm" if pd.notna(row['item_height_mm']) else None,
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

    else:
        st.info("Click a row to see product details, image, and variants.")
