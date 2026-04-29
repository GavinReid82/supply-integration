import streamlit as st

st.set_page_config(page_title="Supply Integration", page_icon="🏭", layout="wide")

pg = st.navigation(
    [
        st.Page("pages/0_Home.py", title="Home", icon="🏠", default=True),
        st.Page("pages/1_Catalog.py", title="Bespoke", icon="🖨️"),
        st.Page("pages/3_Catman.py", title="Catman", icon="📊"),
        st.Page("pages/2_Configure_Order.py", title="Configure Order"),
    ],
    position="hidden",
)

st.sidebar.page_link("pages/0_Home.py", label="Home", icon="🏠")
st.sidebar.page_link("pages/1_Catalog.py", label="Bespoke", icon="🖨️")
st.sidebar.page_link("pages/3_Catman.py", label="Catman", icon="📊")

pg.run()
