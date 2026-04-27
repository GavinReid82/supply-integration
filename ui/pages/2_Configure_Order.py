import pandas as pd
import streamlit as st

from db import query
from supplier_reference import build as build_supplier_ref

st.set_page_config(page_title="Configure Order", page_icon="🖨️", layout="wide")

COUNTRIES = [
    ("NL", "Netherlands"), ("DE", "Germany"), ("FR", "France"), ("BE", "Belgium"),
    ("GB", "United Kingdom"), ("ES", "Spain"), ("IT", "Italy"), ("AT", "Austria"),
    ("CH", "Switzerland"), ("LU", "Luxembourg"), ("IE", "Ireland"), ("PT", "Portugal"),
    ("DK", "Denmark"), ("FI", "Finland"), ("SE", "Sweden"), ("NO", "Norway"),
    ("IS", "Iceland"), ("PL", "Poland"), ("CZ", "Czech Republic"), ("HU", "Hungary"),
    ("RO", "Romania"), ("BG", "Bulgaria"), ("SK", "Slovakia"), ("SI", "Slovenia"),
]


@st.cache_data
def load_variants(product_ref: str) -> pd.DataFrame:
    return query(
        "SELECT matnr, colour_name, colour_code, size FROM variants WHERE product_ref = ? ORDER BY matnr",
        [product_ref],
    )


@st.cache_data
def load_print_options(product_ref: str) -> pd.DataFrame:
    return query(
        """SELECT teccode, technique_name, areacode, area_name,
                  area_width_cm, area_height_cm, area_image_url, included_colours
           FROM print_options
           WHERE product_ref = ?
           ORDER BY teccode, areacode""",
        [product_ref],
    )


@st.cache_data
def load_print_price_tier(teccode: str, quantity: int) -> pd.DataFrame:
    df = query(
        """SELECT price_per_unit, cliche_cost, min_job_cost
           FROM print_prices
           WHERE teccode = ? AND amount_under > ?
           ORDER BY tier ASC LIMIT 1""",
        [teccode, quantity],
    )
    if df.empty:
        df = query(
            """SELECT price_per_unit, cliche_cost, min_job_cost
               FROM print_prices
               WHERE teccode = ?
               ORDER BY tier DESC LIMIT 1""",
            [teccode],
        )
    return df


@st.cache_data
def load_product_price_tier(product_ref: str, quantity: int) -> float | None:
    tiers = query(
        "SELECT min_qty, unit_price FROM mko_prices WHERE product_ref = ? ORDER BY min_qty",
        [product_ref],
    )
    if tiers.empty:
        return None
    applicable = tiers[tiers["min_qty"].abs() >= quantity]
    if applicable.empty:
        applicable = tiers.tail(1)
    return float(applicable.iloc[0]["unit_price"])


@st.cache_data
def load_carriers(country_code: str) -> pd.DataFrame:
    return query(
        """SELECT z.id_carrier, c.carrier_name, z.price_eur
           FROM mko_carrier_zones z
           JOIN carriers c ON z.id_carrier = c.id_carrier
           WHERE z.country_code = ?
           ORDER BY z.price_eur""",
        [country_code],
    )


# ── Guard: product must be pre-selected from catalog ─────────────────────────
if "order_product" not in st.session_state:
    st.warning("No product selected. Please choose a product from the catalog first.")
    if st.button("← Back to Catalog"):
        st.switch_page("pages/1_Catalog.py")
    st.stop()

product = st.session_state["order_product"]
product_ref  = product["product_ref"]
product_name = product["product_name"]

# ── Product summary header ────────────────────────────────────────────────────
st.title("🖨️ Configure Order")

col_img, col_info = st.columns([1, 4])
with col_img:
    if product.get("imagemain"):
        st.image(product["imagemain"], width=120)
with col_info:
    st.markdown(f"### {product_name}")
    st.markdown(
        f"**Ref:** {product_ref}"
        f"&nbsp;&nbsp;|&nbsp;&nbsp;**Type:** {product.get('product_type') or '—'}"
        f"&nbsp;&nbsp;|&nbsp;&nbsp;**Category:** {product.get('category_name_1') or '—'}"
        f" › {product.get('category_name_2') or '—'}"
    )
    if st.button("← Back to Catalog"):
        st.switch_page("pages/1_Catalog.py")

st.divider()

# ── Configuration columns ─────────────────────────────────────────────────────
left, right = st.columns([1, 1])

with left:
    # Step 1 — Variant
    st.subheader("1. Select Variant")
    variants_df = load_variants(product_ref)
    if variants_df.empty:
        st.warning("No variants found for this product.")
        st.stop()

    variant_labels = variants_df.apply(
        lambda r: f"{r['matnr']} — {r['colour_name'] or ''} {r['size'] or ''}".strip(),
        axis=1,
    ).tolist()
    variant_idx = st.selectbox("Variant", range(len(variant_labels)), format_func=lambda i: variant_labels[i])
    selected_variant = variants_df.iloc[variant_idx]
    variant_id = selected_variant["matnr"]

    # Step 2 — Quantity
    st.subheader("2. Quantity")
    quantity = st.number_input("Units", min_value=1, value=100, step=1)

    # Step 3 — Print options
    st.subheader("3. Print Options")
    print_options_df = load_print_options(product_ref)

    selected_prints = []
    if print_options_df.empty:
        st.caption("No print options available for this product.")
    else:
        option_labels = print_options_df.apply(
            lambda r: f"{r['technique_name']} — {r['area_name']}", axis=1
        ).tolist()
        selected_idxs = st.multiselect(
            "Select print option(s)",
            range(len(option_labels)),
            format_func=lambda i: option_labels[i],
        )
        selected_prints = [print_options_df.iloc[i] for i in selected_idxs]

        if selected_prints:
            img_cols = st.columns(min(len(selected_prints), 3))
            for col, p in zip(img_cols, selected_prints):
                if p.get("area_image_url"):
                    col.image(
                        p["area_image_url"],
                        width=100,
                        caption=f"{p['area_name']} ({p['area_width_cm']}×{p['area_height_cm']} cm)",
                    )

with right:
    # Step 4 — Destination
    st.subheader("4. Destination")
    country_labels = [f"{name} ({code})" for code, name in COUNTRIES]
    country_idx = st.selectbox(
        "Destination country",
        range(len(COUNTRIES)),
        format_func=lambda i: country_labels[i],
    )
    selected_country_code = COUNTRIES[country_idx][0]

    # Step 5 — Carrier
    st.subheader("5. Carrier")
    carrier_options = load_carriers(selected_country_code)
    selected_carrier = None

    if carrier_options.empty:
        st.warning("No carriers available for this destination.")
    else:
        carrier_labels = carrier_options.apply(
            lambda r: f"{r['carrier_name']} — €{float(r['price_eur']):.2f}", axis=1
        ).tolist()
        carrier_idx = st.selectbox(
            "Carrier", range(len(carrier_labels)), format_func=lambda i: carrier_labels[i]
        )
        selected_carrier = carrier_options.iloc[carrier_idx]

    st.divider()

    # ── Price breakdown ───────────────────────────────────────────────────────
    st.subheader("Price Breakdown")

    unit_price   = load_product_price_tier(product_ref, quantity)
    product_total = (unit_price * quantity) if unit_price else 0.0

    print_total     = 0.0
    print_breakdown = []
    for p in selected_prints:
        pp = load_print_price_tier(p["teccode"], quantity)
        if not pp.empty:
            per_unit  = float(pp.iloc[0]["price_per_unit"])
            cliche    = float(pp.iloc[0]["cliche_cost"])
            min_job   = float(pp.iloc[0]["min_job_cost"])
            job_cost  = max(min_job, per_unit * quantity)
            total     = job_cost + cliche
            print_total += total
            print_breakdown.append({
                "Print":    f"{p['technique_name']} — {p['area_name']}",
                "Per unit": f"€{per_unit:.4f}",
                "Job cost": f"€{job_cost:.2f}",
                "Cliché":   f"€{cliche:.2f}",
                "Total":    f"€{total:.2f}",
            })

    carrier_cost = float(selected_carrier["price_eur"]) if selected_carrier is not None else 0.0
    grand_total  = product_total + print_total + carrier_cost

    rows = []
    if unit_price:
        rows.append({"Item": f"Product ({quantity:,} units × €{unit_price:.4f})", "Cost": f"€{product_total:.2f}"})
    for pb in print_breakdown:
        rows.append({"Item": pb["Print"], "Cost": pb["Total"]})
    if selected_carrier is not None:
        rows.append({"Item": f"Carrier — {selected_carrier['carrier_name']}", "Cost": f"€{carrier_cost:.2f}"})
    rows.append({"Item": "**TOTAL**", "Cost": f"**€{grand_total:.2f}**"})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if print_breakdown:
        with st.expander("Print cost detail"):
            st.dataframe(pd.DataFrame(print_breakdown), use_container_width=True, hide_index=True)

    st.divider()

    # ── Supplier reference ────────────────────────────────────────────────────
    st.subheader("Supplier Reference")

    supplier_ref = build_supplier_ref(
        supplier="mko",
        product_type=product.get("product_type", ""),
        variant_id=variant_id,
        prints=[{"teccode": p["teccode"], "areacode": p["areacode"]} for p in selected_prints],
    )

    st.code(supplier_ref, language=None)
    st.caption("Copy this reference when placing the order with Makito.")

    if selected_carrier is not None:
        st.markdown(
            f"**Carrier ID:** `{int(selected_carrier['id_carrier'])}` "
            f"— {selected_carrier['carrier_name']}"
        )
