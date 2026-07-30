import os
import io
import base64
import re
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF
from playwright.sync_api import sync_playwright

LETTERHEAD_MD5 = "6a40c85d667d86a0887ff994a8329210"


def _get_page_bounds(page, fallback_left, fallback_width):
    """
    Compute the actual content left-edge and width for a page
    by inspecting all table bounding boxes found via PyMuPDF.
    Returns (page_left_val: float, page_width_val: float) in points.
    Falls back to the supplied fallback values if no tables are found.
    """
    tabs = page.find_tables()
    bboxes = []
    for tab in tabs.tables:
        if hasattr(tab, 'bbox'):
            x0, y0, x1, y1 = tab.bbox
            # Only use tables that are in the content area (not footer) and wide enough
            if y1 < 750 and (x1 - x0) > 80:
                bboxes.append(tab.bbox)

    if bboxes:
        page_left = min(b[0] for b in bboxes)
        page_right = max(b[2] for b in bboxes)
        page_width = page_right - page_left
        return page_left, page_width

    return fallback_left, fallback_width


def get_page_section_overlays(page, page_left_str, page_width_str):
    """
    Extract Clinical Indication / Sample Description section bounding boxes
    and return HTML overlay divs that use the per-page computed width.
    """
    spans = []
    blocks = page.get_text('dict')['blocks']
    for b in blocks:
        if 'lines' in b:
            for ln in b['lines']:
                for s in ln['spans']:
                    if s['text'].strip():
                        spans.append(s)
    spans.sort(key=lambda s: (round(s['bbox'][1], 1), round(s['bbox'][0], 1)))

    overlays = []
    for i, s in enumerate(spans):
        text = s['text'].strip()
        if text in ['Clinical Indication:', 'Sample Description:']:
            h_bbox = s['bbox']
            content_spans = []
            for j in range(i + 1, len(spans)):
                next_text = spans[j]['text'].strip()
                if (next_text in ['Clinical Indication:', 'Sample Description:', 'Key Findings:']
                        or 'Variants of Uncertain' in next_text
                        or spans[j]['bbox'][1] - h_bbox[1] > 70):
                    break
                content_spans.append(spans[j])

            if content_spans:
                c_min_y = h_bbox[3] + 1.0
                c_max_y = max(cs['bbox'][3] for cs in content_spans) + 3.0
                h = max(12.0, c_max_y - c_min_y)
                overlays.append(
                    f"<div class='section-content-box' "
                    f"style='left:{page_left_str};top:{c_min_y:.1f}pt;"
                    f"width:{page_width_str};height:{h:.1f}pt;'></div>"
                )
    return overlays


def process_pdf(pdf_input, output_html_path, is_target=False):
    """
    Convert a PDF (file path, bytes, or file-like) to themed Oncquest HTML+CSS.
    All widths and left-offsets are derived per-page from actual table bboxes
    so headers, label bars, and grid lines never overflow into page margins.
    Returns the generated HTML string.
    """
    output_html_path = Path(output_html_path)
    output_html_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(pdf_input, (str, Path)):
        doc = fitz.open(str(pdf_input))
        doc_title = Path(pdf_input).name
    elif isinstance(pdf_input, bytes):
        doc = fitz.open(stream=pdf_input, filetype="pdf")
        doc_title = "Uploaded Report"
    else:
        pdf_bytes = pdf_input.read()
        if hasattr(pdf_input, "seek"):
            pdf_input.seek(0)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        doc_title = getattr(pdf_input, "name", "Uploaded Report")

    # Fallback dimensions — only used when a page has no detectable tables
    fallback_left = 35.5 if is_target else 28.3
    fallback_width = 524.0 if is_target else 538.0

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        f"<title>Oncquest Report - {doc_title}</title>",
        "<style>",
        "@page { size: 595.6pt 842.0pt; margin: 0; }",
        "* { box-sizing: border-box; }",
        "body { margin: 0; padding: 0; background-color: #525659; "
        "font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }",
        ".pdf-container { display: flex; flex-direction: column; align-items: center; padding: 20px 0; }",
        ".pdf-page { background: #ffffff; width: 595.6pt; height: 842.0pt; margin-bottom: 20px; "
        "position: relative; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.3); "
        "page-break-after: always; page-break-inside: avoid; }",
        "div[id^='page'] { position: relative !important; width: 595.6pt !important; "
        "height: 842.0pt !important; overflow: hidden !important; }",
        "div[id^='page'] p { position: absolute !important; margin: 0 !important; "
        "padding: 0 !important; white-space: nowrap !important; z-index: 10 !important; }",
        # .black-banner-span: width + background are set inline per element (per-page)
        ".black-banner-span { color: #ffffff !important; display: inline-block !important; "
        "text-align: center !important; padding: 4px 0 !important; font-weight: bold !important; "
        "font-size: 13.0pt !important; font-family: Cambria, serif !important; border-radius: 0px !important; }",
        # .label-bar-span: width + background are set inline per element (per-page)
        ".label-bar-span { color: #ffffff !important; display: inline-block !important; "
        "padding: 2px 6px !important; border-radius: 2px !important; }",
        ".table-header-cell { position: absolute; background-color: #1f497d !important; "
        "color: #ffffff !important; font-family: Cambria, 'Times New Roman', serif !important; "
        "font-size: 9.5pt !important; font-weight: bold !important; display: flex !important; "
        "align-items: center !important; justify-content: center !important; "
        "text-align: center !important; padding: 2px 4px !important; white-space: normal !important; "
        "word-break: break-word !important; overflow-wrap: break-word !important; "
        "line-height: 1.15 !important; border: 1px solid #1f497d !important; "
        "box-sizing: border-box !important; z-index: 15 !important; }",
        "div[id^='page'] img { position: absolute !important; transform-origin: 0 0 !important; "
        "z-index: 5 !important; opacity: 1 !important; visibility: visible !important; "
        "display: inline-block !important; }",
        ".table-grid-cell { position: absolute; border: 1px solid #1f497d !important; "
        "background: transparent; pointer-events: none; z-index: 4; }",
        ".section-content-box { position: absolute; border: 1px solid #1f497d !important; "
        "background: transparent; pointer-events: none; z-index: 4; }",
        "@media print { body { background-color: #ffffff; } "
        ".pdf-container { padding: 0; } .pdf-page { margin: 0; box-shadow: none; } }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='pdf-container'>",
    ]

    for page_num in range(len(doc)):
        page = doc[page_num]

        # ── Per-page dynamic width detection ──────────────────────────────────
        page_left_val, page_width_val = _get_page_bounds(page, fallback_left, fallback_width)
        page_left_str = f"{page_left_val:.1f}pt"
        page_width_str = f"{page_width_val:.1f}pt"
        page_right_val = page_left_val + page_width_val
        # ─────────────────────────────────────────────────────────────────────

        html_parts.append("<div class='pdf-page'>")
        page_html = page.get_text("html")

        # Find tables again (already used inside _get_page_bounds but we need cells here)
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
                            f"<div class='table-header-cell' "
                            f"style='left:{x0:.1f}pt;top:{y0:.1f}pt;"
                            f"width:{w:.1f}pt;height:{h:.1f}pt;'>"
                            f"{formatted_text}</div>"
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
                        f"<div class='table-grid-cell' "
                        f"style='left:{cx0:.1f}pt;top:{cy0:.1f}pt;"
                        f"width:{cw:.1f}pt;height:{ch:.1f}pt;'></div>"
                    )

        cleaned = page_html

        HEADER_Y_CUTOFF = 200.0
        FOOTER_Y_CUTOFF = 680.0

        # ── Step 1: Remove header/footer <p> tags ─────────────────────────────
        def filter_p(match):
            p_tag = match.group(0)
            top_m = re.search(r'top:([\d\.]+)pt', p_tag)
            if top_m:
                try:
                    top_val = float(top_m.group(1))
                    if top_val < HEADER_Y_CUTOFF or top_val > FOOTER_Y_CUTOFF:
                        return ""
                    for hy0_r, hy1_r in header_y_ranges:
                        if hy0_r <= top_val <= hy1_r:
                            return ""
                except Exception:
                    pass
            return p_tag

        cleaned = re.sub(r'<p\s+[^>]*>.*?</p>', filter_p, cleaned, flags=re.DOTALL)

        # ── Step 2: Fit images within per-page bounds ─────────────────────────
        def fit_page_imgs(page_html_str):
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
                    sx, sy, tx, ty = 1.0, 1.0, page_left_val, 0.0

                img_infos.append({
                    'tag': full_tag, 'style': style_str,
                    'pw': pw, 'ph': ph,
                    'sx': sx, 'sy': sy, 'tx': tx, 'ty': ty
                })

            valid_imgs = [
                info for info in img_infos
                if (-100 <= info['tx'] <= 595.6)
                and (info['ty'] >= HEADER_Y_CUTOFF)
                and (info['ty'] <= FOOTER_Y_CUTOFF)
            ]
            for info in img_infos:
                if info not in valid_imgs:
                    page_html_str = page_html_str.replace(info['tag'], '')

            if len(valid_imgs) == 2 and abs(valid_imgs[0]['ty'] - valid_imgs[1]['ty']) < 30:
                # Side-by-side pair: split per-page width equally
                valid_imgs.sort(key=lambda x: x['tx'])
                gap = 12.0
                target_w = (page_width_val - gap) / 2.0
                common_ty = min(valid_imgs[0]['ty'], valid_imgs[1]['ty'])
                for idx, info in enumerate(valid_imgs):
                    pw = info['pw'] if info['pw'] > 0 else 500
                    new_sx = target_w / pw
                    new_sy = new_sx
                    new_tx = page_left_val if idx == 0 else (page_left_val + target_w + gap)
                    new_matrix = f"matrix({new_sx:.6f},0,0,{new_sy:.6f},{new_tx:.2f},{common_ty:.2f})"
                    new_style = re.sub(r'matrix\([^)]+\)', new_matrix, info['style'])
                    new_tag = info['tag'].replace(info['style'], new_style)
                    page_html_str = page_html_str.replace(info['tag'], new_tag)
            else:
                for info in valid_imgs:
                    new_tx = max(page_left_val, info['tx']) if info['tx'] < page_left_val else info['tx']
                    pw = info['pw'] if info['pw'] > 0 else 500
                    rw = pw * info['sx']
                    new_sx = info['sx']
                    new_sy = info['sy']
                    if new_tx + rw > page_right_val:
                        avail_w = page_right_val - new_tx
                        new_sx = avail_w / pw
                        new_sy = new_sx
                    if new_tx != info['tx'] or new_sx != info['sx']:
                        new_matrix = f"matrix({new_sx:.6f},0,0,{new_sy:.6f},{new_tx:.2f},{info['ty']:.2f})"
                        new_style = re.sub(r'matrix\([^)]+\)', new_matrix, info['style'])
                        new_tag = info['tag'].replace(info['style'], new_style)
                        page_html_str = page_html_str.replace(info['tag'], new_tag)

            return page_html_str

        cleaned = fit_page_imgs(cleaned)

        # ── Step 3: Format dark banner headings (white text, large font) ──────
        # Inject per-page width + background as inline style on the span
        def format_heading_p(match):
            p_tag = match.group(0)
            if "color:#ffffff" in p_tag and (
                "font-size:14.0pt" in p_tag or "font-size:14pt" in p_tag
                or "Variants of Uncertain" in p_tag or "Pathogenic" in p_tag
            ):
                top_m = re.search(r'top:([\d\.]+)pt', p_tag)
                top_val = top_m.group(1) if top_m else "271.5"
                text_val = re.sub(r'<[^>]+>', '', p_tag).strip()
                return (
                    f'<p style="top:{top_val}pt;left:{page_left_str};'
                    f'width:{page_width_str};margin:0;padding:0;z-index:12;">'
                    f'<span class="black-banner-span" '
                    f'style="width:{page_width_str};background-color:#404040;">'
                    f'{text_val}</span></p>'
                )
            return p_tag

        cleaned = re.sub(r'<p\s+[^>]*>.*?</p>', format_heading_p, cleaned, flags=re.DOTALL)

        # ── Step 4: Format white-text label bars (section titles) ─────────────
        # Each label bar gets per-page left + width inline so it never overflows
        def format_labelbar_p(match):
            p_tag = match.group(0)
            if (
                "color:#ffffff" in p_tag
                and "black-banner-span" not in p_tag
                and "table-header-cell" not in p_tag
            ):
                top_m = re.search(r'top:([\d\.]+)pt', p_tag)
                if top_m:
                    top_val = top_m.group(1)
                    # Rewrite the <p> position to match per-page bounds
                    p_tag_mod = re.sub(r'left:[\d\.]+pt', f'left:{page_left_str}', p_tag)
                    if 'left:' not in p_tag:
                        p_tag_mod = p_tag_mod.replace('style="', f'style="left:{page_left_str};')
                    p_tag_mod = re.sub(r'width:[\d\.]+pt', f'width:{page_width_str}', p_tag_mod)

                    # Rewrite every <span> inside to carry per-page width + brand color inline
                    def fix_span(sm):
                        span = sm.group(0)
                        span = re.sub(r'background-color:\s*[^;"]+', 'background-color:#1f497d', span)
                        if 'background-color' not in span:
                            span = span.replace('style="', 'style="background-color:#1f497d;')
                        span = re.sub(r'width:\s*[^;"]+', f'width:{page_width_str}', span)
                        if 'width:' not in span:
                            span = span.replace('style="', f'style="width:{page_width_str};')
                        if 'display:' not in span:
                            span = span.replace('style="', 'style="display:inline-block;')
                        return span

                    return re.sub(r'<span\s+[^>]*>.*?</span>', fix_span, p_tag_mod, flags=re.DOTALL)
            return p_tag

        cleaned = re.sub(r'<p\s+[^>]*>.*?</p>', format_labelbar_p, cleaned, flags=re.DOTALL)

        # ── Step 5: Section box overlays ──────────────────────────────────────
        section_overlays = get_page_section_overlays(page, page_left_str, page_width_str)

        html_parts.append(cleaned)
        html_parts.extend(section_overlays)
        html_parts.extend(table_header_html_divs)
        html_parts.extend(table_grid_html_divs)
        html_parts.append("</div>")

    html_parts.append("</div></body></html>")

    full_html = "\n".join(html_parts)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    doc.close()
    return full_html


def render_html_to_pdf_and_preview(html_path, output_pdf_path, preview_img_path=None):
    """
    Render an HTML file to PDF via Playwright Chromium.
    Optionally saves a PNG screenshot of the first viewport.
    """
    html_path = Path(html_path).absolute()
    output_pdf_path = Path(output_pdf_path)
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 1200})
        page.goto(html_path.as_uri(), wait_until="networkidle")

        if preview_img_path:
            preview_img_path = Path(preview_img_path)
            preview_img_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(preview_img_path), full_page=False)

        page.pdf(
            path=str(output_pdf_path),
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
        )
        page.close()
        browser.close()

    return output_pdf_path


def convert_pdf_to_word(pdf_path, docx_path):
    """
    Convert a PDF file to Word (.docx) using pdf2docx.
    """
    from pdf2docx import Converter as DocxConverter
    pdf_path = Path(pdf_path).absolute()
    docx_path = Path(docx_path).absolute()
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    cv = DocxConverter(str(pdf_path))
    cv.convert(str(docx_path), start=0, end=None)
    cv.close()
    return docx_path
