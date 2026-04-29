import pandas as pd
import streamlit as st


def add_to_basket(item: dict) -> None:
    if "bespoke_basket" not in st.session_state:
        st.session_state["bespoke_basket"] = []
    st.session_state["bespoke_basket"].append(item)


def show_basket() -> None:
    basket = st.session_state.get("bespoke_basket", [])
    if not basket:
        return

    st.divider()
    st.subheader(f"🛒 Basket — {len(basket)} item{'s' if len(basket) != 1 else ''}")

    rows = [
        {
            "Product":      item["product_name"],
            "Variant":      item["variant_label"],
            "Qty":          item["quantity"],
            "Prints":       item["prints_label"],
            "Carrier":      item["carrier_name"],
            "Supplier Ref": item["supplier_ref"],
            "Total (€)":    f"€{item['grand_total']:.2f}",
        }
        for item in basket
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    col_csv, col_detail, col_clear = st.columns([1, 2, 1])

    with col_csv:
        export_rows = [
            {
                "supplier":      item.get("supplier", ""),
                "product_ref":   item["product_ref"],
                "product_name":  item["product_name"],
                "variant_matnr": item["variant_matnr"],
                "variant":       item["variant_label"],
                "quantity":      item["quantity"],
                "prints":        item["prints_label"],
                "carrier":       item["carrier_name"],
                "supplier_ref":  item["supplier_ref"],
                "unit_price":    item["unit_price"],
                "product_total": item["product_total"],
                "print_total":   item["print_total"],
                "carrier_cost":  item["carrier_cost"],
                "grand_total":   item["grand_total"],
            }
            for item in basket
        ]
        csv = pd.DataFrame(export_rows).to_csv(index=False).encode()
        st.download_button(
            "⬇️ Export CSV",
            data=csv,
            file_name="basket.csv",
            mime="text/csv",
            type="primary",
        )

    with col_detail:
        with st.expander("Price breakdown"):
            detail = [
                {
                    "Product":       item["product_name"],
                    "Variant":       item["variant_label"],
                    "Qty":           item["quantity"],
                    "Unit price":    f"€{item['unit_price']:.4f}",
                    "Products":      f"€{item['product_total']:.2f}",
                    "Print":         f"€{item['print_total']:.2f}",
                    "Carrier":       f"€{item['carrier_cost']:.2f}",
                    "Total":         f"€{item['grand_total']:.2f}",
                }
                for item in basket
            ]
            st.dataframe(pd.DataFrame(detail), use_container_width=True, hide_index=True)

    with col_clear:
        if st.button("🗑 Clear basket", type="secondary"):
            st.session_state["bespoke_basket"] = []
            st.rerun()
