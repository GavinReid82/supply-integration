import pandas as pd
import streamlit as st

from basket import add_to_basket, show_basket
from db import query
from supplier_reference import build as build_supplier_ref

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
        "SELECT variant_id, colour_name, colour_code, size FROM variants WHERE product_ref = ? ORDER BY variant_id",
        [product_ref],
    )


@st.cache_data
def load_print_options(product_ref: str) -> pd.DataFrame:
    return query(
        """SELECT teccode, technique_name, print_color, areacode, area_name,
                  area_width_cm, area_height_cm, area_image_url, included_colours
           FROM print_options
           WHERE product_ref = ?
           ORDER BY teccode, areacode""",
        [product_ref],
    )


@st.cache_data
def load_print_price_tier(technique_code: str, quantity: int) -> pd.DataFrame:
    df = query(
        """SELECT price_per_unit, setup_cost, min_job_cost
           FROM print_prices
           WHERE technique_code = ? AND quantity_min <= ?
           ORDER BY quantity_min DESC LIMIT 1""",
        [technique_code, quantity],
    )
    if df.empty:
        df = query(
            """SELECT price_per_unit, setup_cost, min_job_cost
               FROM print_prices
               WHERE technique_code = ?
               ORDER BY quantity_min DESC LIMIT 1""",
            [technique_code],
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
    if product.get("image_url"):
        st.image(product["image_url"], width=120)
with col_info:
    st.markdown(f"### {product_name}")
    st.markdown(
        f"**Ref:** {product_ref}"
        f"&nbsp;&nbsp;|&nbsp;&nbsp;**Type:** {product.get('product_type') or '—'}"
        f"&nbsp;&nbsp;|&nbsp;&nbsp;**Category:** {product.get('category') or '—'}"
        f" › {product.get('subcategory') or '—'}"
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
        lambda r: f"{r['variant_id']} — {r['colour_name'] or ''} {r['size'] or ''}".strip(),
        axis=1,
    ).tolist()
    variant_idx = st.selectbox("Variant", range(len(variant_labels)), format_func=lambda i: variant_labels[i])
    selected_variant = variants_df.iloc[variant_idx]
    variant_id = selected_variant["variant_id"]

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
        def _color_label(pc: int) -> str:
            return "Full Color" if pc == -1 else f"{pc} colour{'s' if pc != 1 else ''}"

        option_labels = print_options_df.apply(
            lambda r: f"{r['technique_name']} ({_color_label(int(r['print_color']))}) — {r['area_name']}", axis=1
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

    unit_price    = load_product_price_tier(product_ref, quantity)
    product_total = (unit_price * quantity) if unit_price else 0.0

    print_total     = 0.0
    print_breakdown = []
    for p in selected_prints:
        pp = load_print_price_tier(p["teccode"], quantity)
        if not pp.empty:
            per_unit  = float(pp.iloc[0]["price_per_unit"])
            cliche    = float(pp.iloc[0]["setup_cost"])
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
    st.caption("Copy this reference when placing the order with mko.")

    if selected_carrier is not None:
        st.markdown(
            f"**Carrier ID:** `{int(selected_carrier['id_carrier'])}` "
            f"— {selected_carrier['carrier_name']}"
        )

    st.divider()

    # ── Add to basket ─────────────────────────────────────────────────────────
    can_add = selected_carrier is not None and unit_price is not None
    if st.button(
        "🛒 Add to Basket",
        use_container_width=True,
        type="primary",
        disabled=not can_add,
    ):
        prints_label = (
            " | ".join(f"{p['technique_name']} ({p['area_name']})" for p in selected_prints)
            if selected_prints else "No print"
        )
        add_to_basket({
            "supplier":      "mko",
            "product_ref":   product_ref,
            "product_name":  product_name,
            "variant_matnr": str(variant_id),
            "variant_label": variant_labels[variant_idx],
            "quantity":      int(quantity),
            "prints_label":  prints_label,
            "carrier_name":  selected_carrier["carrier_name"],
            "supplier_ref":  supplier_ref,
            "unit_price":    unit_price or 0.0,
            "product_total": product_total,
            "print_total":   print_total,
            "carrier_cost":  carrier_cost,
            "grand_total":   grand_total,
        })
        st.success(f"✓ {product_name} added to basket.")

# ── Basket ────────────────────────────────────────────────────────────────────
show_basket()
