# Oncquest PDF Theme Converter

A Streamlit web application and Python engine that converts diagnostic/lab report PDFs into Oncquest-themed HTML+CSS documents (`target.html` / `index.html`) and high-fidelity print-ready PDFs.

## Features

- 🧪 **Streamlit Web Interface (`app.py`)**: Drag-and-drop PDF report upload with live HTML preview and screenshot viewer.
- 🎨 **Oncquest Deep Blue Styling**: Injects `#1f497d` section content boxes and table grid styling.
- 🏷️ **Header Banner Formatting**: Formats black banner section headers (`#404040` background, Cambria font).
- 📐 **Auto-Formatted Table Header Rows**: Proportional header cell width, uniform row height, equal padding, and clean 2-line text wrapping across all header cells (*Gene & Transcript*, *Location*, *Variant*, *Zygosity/Inheritance*, *Phenotype*, *Clinical Significance*).
- 🖼️ **Image & Logo Preservation**: Preserves all report logos, diagrams, signatures, and figures.
- 🖨️ **PDF Generation**: Uses Playwright Chromium to output print-ready result PDFs.

## Project Structure

```
├── app.py              # Streamlit Web Frontend
├── converter.py        # Core PDF-to-Oncquest Conversion Engine Module
├── convert.py          # Standalone Script to process local PDFs
├── vendor pdf.pdf      # Source Vendor PDF
├── result.pdf          # Source Result PDF
├── target.html         # Generated Oncquest Target HTML Report
├── index.html          # Generated Oncquest Index HTML Report
└── output/             # Extracted report images and rendered PDF results
```

## How to Run Locally

### 1. Install Dependencies

```bash
pip install streamlit fitz playwright
playwright install chromium
```

### 2. Run Streamlit Frontend

```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501`.

### 3. Run Standalone Script

```bash
python convert.py
```
