import os
import io
import shutil
import subprocess
import base64
import hashlib
import re
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF
from playwright.sync_api import sync_playwright

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

LETTERHEAD_MD5 = "6a40c85d667d86a0887ff994a8329210"

def get_page_section_overlays(page, is_target):
    spans = []
    blocks = page.get_text('dict')['blocks']
    for b in blocks:
        if 'lines' in b:
            for l in b['lines']:
                for s in l['spans']:
                    if s['text'].strip():
                        spans.append(s)
    spans.sort(key=lambda s: (round(s['bbox'][1], 1), round(s['bbox'][0], 1)))
    
    overlays = []
    default_left = '35.5pt' if is_target else '28.3pt'
    default_width = '524.0pt' if is_target else '538.0pt'
    
    for i, s in enumerate(spans):
        text = s['text'].strip()
        if text in ['Clinical Indication:', 'Sample Description:']:
            h_bbox = s['bbox']
            content_spans = []
            for j in range(i+1, len(spans)):
                next_text = spans[j]['text'].strip()
                if next_text in ['Clinical Indication:', 'Sample Description:', 'Key Findings:'] or 'Variants of Uncertain' in next_text or spans[j]['bbox'][1] - h_bbox[1] > 70:
                    break
                content_spans.append(spans[j])
            
            if content_spans:
                c_min_y = h_bbox[3] + 1.0
                c_max_y = max(cs['bbox'][3] for cs in content_spans) + 3.0
                h = max(12.0, c_max_y - c_min_y)
                top_pt = c_min_y
                overlays.append(f"<div class='section-content-box' style='left:{default_left};top:{top_pt:.1f}pt;width:{default_width};height:{h:.1f}pt;'></div>")
    return overlays

def process_pdf(pdf_path, output_html_path, is_target=False):
    output_html_path = Path(output_html_path)
    doc = fitz.open(pdf_path)
    print(f"Processing '{pdf_path}' ({len(doc)} pages) -> '{output_html_path.name}'...")

    default_left = "35.5pt" if is_target else "28.3pt"
    default_width = "524.0pt" if is_target else "538.0pt"

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        f"<title>Report - {Path(pdf_path).name}</title>",
        "<style>",
        "@page { size: 595.6pt 842.0pt; margin: 0; }",
        "* { box-sizing: border-box; }",
        "body { margin: 0; padding: 0; background-color: #525659; font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }",
        ".pdf-container { display: flex; flex-direction: column; align-items: center; padding: 20px 0; }",
        ".pdf-page { background: #ffffff; width: 595.6pt; height: 842.0pt; margin-bottom: 20px; position: relative; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.3); page-break-after: always; page-break-inside: avoid; }",
        "div[id^='page'] { position: relative !important; width: 595.6pt !important; height: 842.0pt !important; overflow: hidden !important; }",
        "div[id^='page'] p { position: absolute !important; margin: 0 !important; padding: 0 !important; white-space: nowrap !important; z-index: 10 !important; }",
        f"div[id^='page'] p span[style*='color:#ffffff']:not(.black-banner-span) {{ background-color: #1f497d !important; color: #ffffff !important; padding: 2px 6px !important; display: inline-block !important; width: {default_width} !important; border-radius: 2px !important; }}",
        f".black-banner-span {{ background-color: #404040 !important; color: #ffffff !important; display: inline-block !important; width: {default_width} !important; text-align: center !important; padding: 4px 0 !important; font-weight: bold !important; font-size: 13.0pt !important; font-family: Cambria, serif !important; border-radius: 0px !important; }}",
        ".table-header-cell { position: absolute; background-color: #1f497d !important; color: #ffffff !important; font-family: Cambria, 'Times New Roman', serif !important; font-size: 9.5pt !important; font-weight: bold !important; display: flex !important; align-items: center !important; justify-content: center !important; text-align: center !important; padding: 2px 4px !important; white-space: normal !important; word-break: break-word !important; overflow-wrap: break-word !important; line-height: 1.15 !important; border: 1px solid #1f497d !important; box-sizing: border-box !important; z-index: 15 !important; }",
        "div[id^='page'] img { position: absolute !important; transform-origin: 0 0 !important; z-index: 5 !important; opacity: 1 !important; visibility: visible !important; display: inline-block !important; }",
        ".table-grid-cell { position: absolute; border: 1px solid #1f497d !important; background: transparent; pointer-events: none; z-index: 4; }",
        ".section-content-box { position: absolute; border: 1px solid #1f497d !important; background: transparent; pointer-events: none; z-index: 4; }",
        "@media print { body { background-color: #ffffff; } .pdf-container { padding: 0; } .pdf-page { margin: 0; box-shadow: none; } }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='pdf-container'>"
    ]

    for page_num in range(len(doc)):
        page = doc[page_num]
        html_parts.append("<div class='pdf-page'>")
        page_html = page.get_text("html")

        # 1. Detect tables and format header row cells
        tabs = page.find_tables()
        table_header_html_divs = []
        table_grid_html_divs = []
        header_y_ranges = []

        for tab in tabs.tables:
            if hasattr(tab, 'bbox') and tab.bbox[1] > 700:
                continue
            valid_cells = [c for c in tab.cells if c]
            if valid_cells:
                min_y0 = min(c[1] for c in valid_cells)
                header_cells = [c for c in valid_cells if abs(c[1] - min_y0) < 3.0]
                header_cells.sort(key=lambda c: c[0])
                if len(header_cells) >= 4:
                    hy0 = min(c[1] for c in header_cells)
                    hy1 = max(c[3] for c in header_cells)
                    header_y_ranges.append((hy0 - 1.0, hy1 + 1.0))

                    for c in header_cells:
                        x0, y0, x1, y1 = c
                        w = x1 - x0
                        h = max(32.0, y1 - y0)
                        rect = fitz.Rect(x0, y0, x1, y1)
                        raw_text = page.get_text('text', clip=rect).strip()
                        formatted_text = raw_text.replace('\n', ' ').strip()
                        if "/" in formatted_text and " " not in formatted_text:
                            formatted_text = formatted_text.replace("/", "/ ")
                        table_header_html_divs.append(
                            f"<div class='table-header-cell' style='left:{x0:.1f}pt;top:{y0:.1f}pt;width:{w:.1f}pt;height:{h:.1f}pt;'>{formatted_text}</div>"
                        )

            for cell in tab.cells:
                if cell:
                    cx0, cy0, cx1, cy1 = cell
                    cw = cx1 - cx0
                    ch = cy1 - cy0
                    if cy0 > 700:
                        continue
                    if any(hy0_r <= cy0 <= hy1_r for hy0_r, hy1_r in header_y_ranges):
                        continue
                    table_grid_html_divs.append(
                        f"<div class='table-grid-cell' style='left:{cx0:.1f}pt;top:{cy0:.1f}pt;width:{cw:.1f}pt;height:{ch:.1f}pt;'></div>"
                    )

        # 2. Keep all page HTML intact
        cleaned = page_html

        HEADER_Y_CUTOFF = 200.0   # Remove top header text/patient info above 200pt (cleaned target format)
        FOOTER_Y_CUTOFF = 680.0  # Remove bottom footer text/page numbers below 680pt

        # 3. Filter text <p> elements (remove top header & bottom footer <p> tags on every page)
        def filter_p(match):
            p_tag = match.group(0)
            top_match = re.search(r'top:([\d\.]+)pt', p_tag)
            if top_match:
                try:
                    top_val = float(top_match.group(1))
                    if top_val < HEADER_Y_CUTOFF or top_val > FOOTER_Y_CUTOFF:
                        return ""
                    for hy0_r, hy1_r in header_y_ranges:
                        if hy0_r <= top_val <= hy1_r:
                            return ""
                except Exception:
                    pass
            return p_tag

        cleaned = re.sub(r'<p\s+[^>]*>.*?</p>', filter_p, cleaned, flags=re.DOTALL)

        # 4. Preserve and properly fit all legitimate report images within page margins
        def fit_page_imgs(page_html_str, default_left_val, default_width_val):
            right_b = float(default_left_val.replace('pt','')) + float(default_width_val.replace('pt',''))
            def_l = float(default_left_val.replace('pt',''))

            img_matches = list(re.finditer(r'<img\s+([^>]*style=["\']([^"\']+)["\'][^>]*)>', page_html_str))
            if not img_matches:
                return page_html_str

            img_infos = []
            for m in img_matches:
                full_tag = m.group(0)
                style_str = m.group(2)
                src_m = re.search(r'src=["\']data:image/png;base64,([^"\']+)["\']', full_tag)
                b64_data = src_m.group(1) if src_m else None

                pw, ph = 0, 0
                if b64_data:
                    try:
                        im = Image.open(io.BytesIO(base64.b64decode(b64_data)))
                        pw, ph = im.size
                    except Exception:
                        pass

                matrix_m = re.search(r'matrix\(([^)]+)\)', style_str)
                if matrix_m:
                    parts = [float(x.strip()) for x in matrix_m.group(1).split(',')]
                    sx, sy, tx, ty = parts[0], parts[3], parts[4], parts[5]
                else:
                    sx, sy, tx, ty = 1.0, 1.0, def_l, 0.0

                img_infos.append({
                    'tag': full_tag, 'style': style_str,
                    'pw': pw, 'ph': ph,
                    'sx': sx, 'sy': sy, 'tx': tx, 'ty': ty
                })

            valid_imgs = [info for info in img_infos if (-100 <= info['tx'] <= 595.6) and (info['ty'] >= HEADER_Y_CUTOFF) and (info['ty'] <= FOOTER_Y_CUTOFF)]
            for info in img_infos:
                if info not in valid_imgs:
                    page_html_str = page_html_str.replace(info['tag'], '')

            if len(valid_imgs) == 2 and abs(valid_imgs[0]['ty'] - valid_imgs[1]['ty']) < 30:
                valid_imgs.sort(key=lambda x: x['tx'])
                gap = 12.0
                target_w = (float(default_width_val.replace('pt','')) - gap) / 2.0
                common_ty = min(valid_imgs[0]['ty'], valid_imgs[1]['ty'])

                for idx, info in enumerate(valid_imgs):
                    pw = info['pw'] if info['pw'] > 0 else 500
                    new_sx = target_w / pw
                    new_sy = new_sx
                    new_tx = def_l if idx == 0 else (def_l + target_w + gap)
                    new_matrix = f"matrix({new_sx:.6f},0,0,{new_sy:.6f},{new_tx:.2f},{common_ty:.2f})"
                    new_style = re.sub(r'matrix\([^)]+\)', new_matrix, info['style'])
                    new_tag = info['tag'].replace(info['style'], new_style)
                    page_html_str = page_html_str.replace(info['tag'], new_tag)
            else:
                for info in valid_imgs:
                    new_tx = max(def_l, info['tx']) if info['tx'] < def_l else info['tx']
                    pw = info['pw'] if info['pw'] > 0 else 500
                    rw = pw * info['sx']
                    new_sx = info['sx']
                    new_sy = info['sy']

                    if new_tx + rw > right_b:
                        avail_w = right_b - new_tx
                        new_sx = avail_w / pw
                        new_sy = new_sx

                    if new_tx != info['tx'] or new_sx != info['sx']:
                        new_matrix = f"matrix({new_sx:.6f},0,0,{new_sy:.6f},{new_tx:.2f},{info['ty']:.2f})"
                        new_style = re.sub(r'matrix\([^)]+\)', new_matrix, info['style'])
                        new_tag = info['tag'].replace(info['style'], new_style)
                        page_html_str = page_html_str.replace(info['tag'], new_tag)

            return page_html_str

        cleaned = fit_page_imgs(cleaned, default_left, default_width)

        # 5. Format black banner headings ("Variants of Uncertain Significance...")
        def format_heading_p(match):
            p_tag = match.group(0)
            if "color:#ffffff" in p_tag and ("font-size:14.0pt" in p_tag or "font-size:14pt" in p_tag or "Variants of Uncertain" in p_tag or "Pathogenic" in p_tag):
                top_m = re.search(r'top:([\d\.]+)pt', p_tag)
                top_val = top_m.group(1) if top_m else "271.5"
                text_val = re.sub(r'<[^>]+>', '', p_tag).strip()
                return f'<p style="top:{top_val}pt;left:{default_left};width:{default_width};margin:0;padding:0;z-index:12;"><span class="black-banner-span">{text_val}</span></p>'
            return p_tag

        cleaned = re.sub(r'<p\s+[^>]*>.*?</p>', format_heading_p, cleaned, flags=re.DOTALL)

        # 6. Inject section content box borders (Clinical Indication / Sample Description)
        section_overlays = get_page_section_overlays(page, is_target)

        html_parts.append(cleaned)
        html_parts.extend(section_overlays)
        html_parts.extend(table_header_html_divs)
        html_parts.extend(table_grid_html_divs)
        html_parts.append("</div>")

    html_parts.append("</div></body></html>")
    
    full_html = "\n".join(html_parts)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Saved HTML to: {output_html_path}")
    return full_html

# --- PROCESS index.html (from result.pdf) ---
if Path("result.pdf").exists():
    process_pdf("result.pdf", output_dir / "index.html", is_target=False)
    shutil.copy(output_dir / "index.html", "index.html")

# --- PROCESS target.html (from vendor pdf.pdf) ---
vendor_pdf = Path("vendor pdf.pdf")
if not vendor_pdf.exists():
    vendor_pdf = Path("result.pdf")

if vendor_pdf.exists():
    process_pdf(str(vendor_pdf), output_dir / "cleaned_target.html", is_target=True)
    shutil.copy(output_dir / "cleaned_target.html", "cleaned_target.html")

# --- RENDER PDFS VIA PLAYWRIGHT ---
print("\nConverting HTML + CSS to PDF using Playwright (Chromium)...")

with sync_playwright() as p:
    browser = p.chromium.launch()

    # Render cleaned_target.html -> result.pdf
    if (output_dir / "cleaned_target.html").exists():
        page_tgt = browser.new_page(viewport={"width": 1000, "height": 1200})
        page_tgt.goto((output_dir / "cleaned_target.html").absolute().as_uri(), wait_until="networkidle")
        page_tgt.screenshot(path=str(output_dir / "cleaned_target_preview.png"), full_page=False)
        page_tgt.pdf(path=str(output_dir / "result.pdf"), print_background=True, prefer_css_page_size=True, margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"})
        shutil.copy(output_dir / "result.pdf", "result.pdf")
        page_tgt.close()

    browser.close()

print("\nAll HTML and PDF files updated successfully!")
print("Done!")
