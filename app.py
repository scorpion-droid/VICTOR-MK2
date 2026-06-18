import streamlit as st
import io 
from PIL import Image
import pillow_heif
from App.sanitiser import clean_image
from App.checker import detect_first_error

st.set_page_config(page_title="V.I.C.T.O.R", layout="centered")

st.title("V.I.C.T.O.R")
st.subheader("Upload your math steps for verification")

uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "png", "jpeg", "heic", "heif"])

if uploaded_file is not None:
    if st.button("Check Math"):
        with st.spinner('Analyzing handwriting and verifying steps...'):
            
            
            try:
                file_extension = uploaded_file.name.split(".")[-1].lower()
                if file_extension in ["heic", "heif"]:
                    heif_file = pillow_heif.read_heif(uploaded_file.getvalue())
                    image = Image.frombytes(
                        heif_file.mode, 
                        heif_file.size, 
                        heif_file.data, 
                        "raw", 
                        heif_file.mode, 
                        heif_file.stride
                    )
                    image.save("temp_image.png", format="PNG")
                else:
                    with open("temp_image.png", "wb") as f:
                        f.write(uploaded_file.getvalue())

                sanatized = clean_image("temp_image.png")
                steps = [s.strip() for s in sanatized.splitlines() if s.strip()]
                
                st.text_area("Extracted Steps:", "\n".join(steps))
    
                result = detect_first_error(steps)
                if result.passed:
                    st.success(f"Passed: {result.message}")
                else:
                    st.error(f"Error found: {result.message}")
                    
            except Exception as e:
                st.error("The AI service is experiencing heavy traffic or is temporarily down. Please wait a moment and try clicking 'Check Math' again.")
                st.caption(f"Technical info: {e}")