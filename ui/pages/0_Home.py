import streamlit as st

st.title("🏭 Supply Integration")
st.markdown("Choose your workflow:")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🖨️ Bespoke")
    st.markdown(
        "Look up a product, configure print options and a carrier, "
        "and generate a supplier reference for a one-off order."
    )
    if st.button("Open Bespoke →", use_container_width=True, type="primary", key="bespoke"):
        st.switch_page("pages/1_Catalog.py")

with col2:
    st.markdown("### 📊 Category Management")
    st.markdown(
        "Select products by template, assign slugs and quantity codes, "
        "choose print options, and export a PCM configuration file."
    )
    if st.button("Open Catman →", use_container_width=True, type="primary", key="catman"):
        st.switch_page("pages/3_Catman.py")
