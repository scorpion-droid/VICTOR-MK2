import streamlit as st
from App.ocr import extract_steps_from_image
from App.sanitiser import clean_noisy_ocr
from App.checker import detect_first_error

st.set_page_config(page_title="V.I.C.T.O.R", layout="centered")

st.title("V.I.C.T.O.R")
st.subheader("Upload your math steps for verification")

uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    if st.button("Check Math"):
        with st.spinner('Processing layout and checking math...'):
            # Save bytes out locally so the backend reader can pull it
            with open("temp_image.png", "wb") as f:
                f.write(uploaded_file.getvalue())
            
            try:
                # 1. OCR Extraction
                raw_steps = extract_steps_from_image("temp_image.png")
                
                # 2. AI Sanitization
                sanitized = clean_noisy_ocr(raw_steps)
                steps = [s.strip() for s in sanitized.splitlines() if s.strip()]
                
                # Display what was read & cleaned
                st.text_area("Sanitized Steps:", "\n".join(steps))
                
                # 3. Math Validation Engine
                result = detect_first_error(steps)
                if result.passed:
                    st.success(f"Passed: {result.message}")
                else:
                    st.error(f"Error found: {result.message}")
                    
            except Exception as e:
                # Catch any unexpected server anomalies cleanly in the user interface
                st.error("The AI service is experiencing heavy traffic or is temporarily down. Please wait a moment and try clicking 'Check Math' again.")
                st.caption(f"Technical info: {e}")