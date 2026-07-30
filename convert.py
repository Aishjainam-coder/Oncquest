"""
convert.py - CLI batch runner.
Imports all logic from converter.py so per-page dynamic widths apply automatically.
"""
import shutil
from pathlib import Path
from converter import process_pdf, render_html_to_pdf_and_preview

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

# --- Process index.html (from result.pdf) ---
if Path("result.pdf").exists():
    print("Processing result.pdf -> index.html ...")
    process_pdf("result.pdf", output_dir / "index.html", is_target=False)
    shutil.copy(output_dir / "index.html", "index.html")

# --- Process cleaned_target.html (from vendor pdf.pdf or result.pdf) ---
vendor_pdf = Path("vendor pdf.pdf")
if not vendor_pdf.exists():
    vendor_pdf = Path("result.pdf")

if vendor_pdf.exists():
    print(f"Processing {vendor_pdf.name} -> cleaned_target.html ...")
    process_pdf(str(vendor_pdf), output_dir / "cleaned_target.html", is_target=True)
    shutil.copy(output_dir / "cleaned_target.html", "cleaned_target.html")

# --- Render HTML -> PDF via Playwright ---
if (output_dir / "cleaned_target.html").exists():
    print("Rendering cleaned_target.html -> result.pdf via Playwright...")
    render_html_to_pdf_and_preview(
        output_dir / "cleaned_target.html",
        output_dir / "result.pdf",
        output_dir / "cleaned_target_preview.png"
    )
    shutil.copy(output_dir / "result.pdf", "result.pdf")

print("All batch conversions completed successfully!")
