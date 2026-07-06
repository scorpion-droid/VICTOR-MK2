import streamlit as st

selected_code = st.session_state.get("selected_class_code")

if not selected_code:
    st.warning("No class selected.")
    if st.button("Back to Dashboard"):
        st.switch_page("app.py")
    st.stop()

st.title(f"Class Detail: {selected_code}")

if st.button("Back to Dashboard"):
    st.switch_page("app.py")