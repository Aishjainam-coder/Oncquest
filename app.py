import os
import tempfile
import base64
from pathlib import Path
import streamlit as st
import fitz  # PyMuPDF
import streamlit.components.v1 as components
from converter import process_pdf, render_html_to_pdf_and_preview

# Configure Streamlit page
st.set_page_config(
    page_title="Oncquest PDF Theme Converter",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling for premium look
st.markdown("""
<style>
    /* Global font & background enhancements */
    .main {
        background-color: #f8fafc;
    }
    
    /* Header card */
    .header-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1f497d 100%);
        color: #ffffff;
        padding: 2.2rem 2.5rem;
        border-radius: 16px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.25);
        margin-bottom: 2rem;
    }
    .header-title {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.02em;
        color: #ffffff;
    }
    .header-subtitle {
        font-size: 1.05rem;
        color: #94a3b8;
        margin-top: 0.5rem;
        margin-bottom: 0;
    }

    /* Card container */
    .content-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 1.5rem;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 0.25em 0.65em;
        font-size: 0.75em;
        font-weight: 700;
        line-height: 1;
        color: #fff;
        text-align: center;
        white-space: nowrap;
        vertical-align: baseline;
        border-radius: 0.375rem;
        background-color: #1f497d;
    }

    /* Custom Streamlit button overrides */
    div.stButton > button:first-child {
        background: linear-gradient(135deg, #1f497d 0%, #112c4e 100%);
        color: white;
        font-weight: 600;
        font-size: 1.05rem;
        padding: 0.65rem 1.8rem;
        border-radius: 10px;
        border: none;
        box-shadow: 0 4px 12px rgba(31, 73, 125, 0.3);
        transition: all 0.2s ease-in-out;
        width: 100%;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(31, 73, 125, 0.4);
        background: linear-gradient(135deg, #275997 0%, #173863 100%);
    }

    /* Download buttons */
    div.stDownloadButton > button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar setup
st.sidebar.image("https://img.icons8.com/color/96/000000/microscope.png", width=64)
st.sidebar.title("Configuration")
st.sidebar.markdown("---")

theme_mode = st.sidebar.radio(
    "Select Target Design Mode",
    options=["🎯 Target Theme (target.html)", "📄 Standard Full Theme (index.html)"],
    index=0,
    help="Target Theme generates the target.html layout matching vendor pdf format."
)
is_target = (theme_mode == "🎯 Target Theme (target.html)")

preview_height = st.sidebar.slider(
    "Live HTML Preview Height (px)",
    min_value=500,
    max_value=1200,
    value=850,
    step=50
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Features")
st.sidebar.markdown("""
- 📄 **Source PDF → target.html**
- 🎨 **Oncquest Deep Blue Theme** (`#1f497d`)
- 🏷️ **Banner Header Formatting**
- 📐 **Table Grid & Section Boxes**
- 🖨️ **HTML+CSS → target.pdf Output**
""")

# Header Banner
st.markdown("""
<div class="header-card">
    <div class="header-title">🧪 Oncquest Target PDF & HTML/CSS Converter</div>
    <div class="header-subtitle">Upload any vendor/source PDF report to generate <code>target.html</code> (HTML+CSS design) and produce the converted Oncquest target PDF result.</div>
</div>
""", unsafe_allow_html=True)

# App State initialization
if "converted" not in st.session_state:
    st.session_state.converted = False
if "html_content" not in st.session_state:
    st.session_state.html_content = ""
if "html_bytes" not in st.session_state:
    st.session_state.html_bytes = None
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
if "preview_png" not in st.session_state:
    st.session_state.preview_png = None
if "file_name" not in st.session_state:
    st.session_state.file_name = ""

# Main area - File Upload
st.subheader("📤 1. Upload Source PDF Report (e.g., Vendor PDF)")
uploaded_file = st.file_uploader("Choose Source PDF File", type=["pdf"], help="Upload vendor pdf or any source lab report PDF.")

if uploaded_file is not None:
    # Read file info
    file_bytes = uploaded_file.getvalue()
    file_size_kb = len(file_bytes) / 1024.0
    
    # Parse page count
    try:
        temp_doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(temp_doc)
        temp_doc.close()
    except Exception:
        page_count = "Unknown"

    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.info(f"**Filename:** {uploaded_file.name}")
    with col_info2:
        st.info(f"**File Size:** {file_size_kb:.1f} KB")
    with col_info3:
        st.info(f"**Total Pages:** {page_count}")

    st.markdown("---")
    st.subheader("⚡ 2. Generate target.html & Target PDF")

    if st.button("🚀 Convert Source PDF to target.html & Target PDF"):
        with st.spinner("Processing vendor PDF, creating target.html (HTML+CSS), and rendering target PDF..."):
            try:
                # Create temporary working directory for processing
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_dir_path = Path(tmp_dir)
                    out_html_path = tmp_dir_path / "target.html"
                    out_pdf_path = tmp_dir_path / "target_output.pdf"
                    preview_png_path = tmp_dir_path / "target_preview.png"

                    # 1. Process PDF to target.html
                    html_str = process_pdf(file_bytes, out_html_path, is_target=is_target)

                    # 2. Render target PDF & Screenshot via Playwright
                    render_html_to_pdf_and_preview(out_html_path, out_pdf_path, preview_png_path)

                    # Read generated outputs into memory for session state
                    with open(out_html_path, "rb") as fh:
                        html_data = fh.read()
                    with open(out_pdf_path, "rb") as fp:
                        pdf_data = fp.read()
                    
                    if preview_png_path.exists():
                        with open(preview_png_path, "rb") as img_f:
                            preview_img_data = img_f.read()
                    else:
                        preview_img_data = None

                    # Save to state
                    st.session_state.converted = True
                    st.session_state.html_content = html_str
                    st.session_state.html_bytes = html_data
                    st.session_state.pdf_bytes = pdf_data
                    st.session_state.preview_png = preview_img_data
                    st.session_state.file_name = Path(uploaded_file.name).stem

                st.success("🎉 Conversion to target.html and Target PDF completed successfully!")
            except Exception as e:
                st.error(f"❌ Error during conversion: {str(e)}")

# Display Results Section if converted
if st.session_state.converted and st.session_state.html_bytes:
    st.markdown("---")
    st.subheader("🎉 3. Results: target.html & Target PDF")

    # Action Buttons Row
    base_name = st.session_state.file_name or "target"
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            label="📥 Download target.html (HTML + CSS)",
            data=st.session_state.html_bytes,
            file_name=f"{base_name}_target.html",
            mime="text/html",
            use_container_width=True
        )
    with col_dl2:
        st.download_button(
            label="📥 Download Target PDF (Result PDF)",
            data=st.session_state.pdf_bytes,
            file_name=f"{base_name}_target_output.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Tabs for Viewers
    tab1, tab2, tab3 = st.tabs(["🌐 Live target.html Preview", "🖼️ Target PDF Screenshot Preview", "💻 Raw target.html Code"])

    with tab1:
        st.markdown("**Live Interactive `target.html` (HTML + CSS):**")
        components.html(st.session_state.html_content, height=preview_height, scrolling=True)

    with tab2:
        st.markdown("**Target PDF Rendered Preview (Page 1):**")
        if st.session_state.preview_png:
            st.image(st.session_state.preview_png, caption="Rendered Target PDF Preview", use_container_width=True)
        else:
            st.warning("Preview screenshot not available.")

    with tab3:
        st.markdown("**Generated Source Code (`target.html`):**")
        st.code(st.session_state.html_content, language="html")

