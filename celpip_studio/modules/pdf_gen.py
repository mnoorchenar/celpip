"""
PDF generation using fpdf2 — no external tools required.
"""
import os
from datetime import datetime
from config import TASK_DEFAULTS

# Map Unicode characters that Latin-1 core fonts cannot encode to safe ASCII.
_UNICODE_MAP = str.maketrans({
    '\u2014': '--',   # em dash
    '\u2013': '-',    # en dash
    '\u2018': "'",    # left single quote
    '\u2019': "'",    # right single quote
    '\u201c': '"',    # left double quote
    '\u201d': '"',    # right double quote
    '\u2022': '*',    # bullet
    '\u2026': '...',  # ellipsis
    '\u00b7': '.',    # middle dot
    '\u2015': '--',   # horizontal bar
})


def _safe(text):
    """Replace unsupported Unicode chars and encode as Latin-1-safe string."""
    text = str(text).translate(_UNICODE_MAP)
    return text.encode('latin-1', errors='replace').decode('latin-1')


def generate_pdf(job_data, session_dir):
    from fpdf import FPDF

    question = job_data['question']
    answer   = job_data['answer']
    vocab    = job_data.get('vocab', [])
    task_num = job_data['task_num']
    category = job_data.get('category', 'General')
    band     = job_data.get('band', '')
    title    = job_data.get('title', '')

    task_info  = TASK_DEFAULTS.get(int(task_num), {})
    task_name  = task_info.get('name', f'Task {task_num}')
    band_label = {'7_8': 'Band 7–8', '9_10': 'Band 9–10', '5_6': 'Band 5–6'}.get(band, '')

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    W = pdf.w - pdf.l_margin - pdf.r_margin

    # ── Header block ──────────────────────────────────────────────────────────
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(W, 9, _safe(f'CELPIP Speaking -- Task {task_num}: {task_name}'), align='L')

    sub_parts = [category]
    if band_label:
        sub_parts.append(band_label)
    subtitle = ' | '.join(sub_parts)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(W, 6, _safe(subtitle), align='L')
    pdf.multi_cell(W, 6, datetime.now().strftime('%B %d, %Y'), align='L')

    pdf.ln(3)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(6)

    # ── Section helpers ───────────────────────────────────────────────────────
    def section_heading(text):
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(37, 99, 235)
        pdf.multi_cell(W, 8, _safe(text), align='L')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(55, 65, 81)

    def body_text(text):
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(55, 65, 81)
        pdf.multi_cell(W, 6, _safe(text), align='L')
        pdf.ln(2)

    # ── Question ──────────────────────────────────────────────────────────────
    section_heading('Question')
    body_text(question)
    pdf.ln(4)

    # ── Answer ────────────────────────────────────────────────────────────────
    section_heading('Model Answer')
    body_text(answer)
    pdf.ln(4)

    # ── Vocabulary ────────────────────────────────────────────────────────────
    if vocab:
        section_heading('Vocabulary')
        pdf.ln(2)
        for item in vocab:
            word      = _safe(item.get('word', ''))
            defn      = _safe(item.get('definition', ''))
            word_type = _safe(item.get('type', ''))
            example   = _safe(item.get('example', ''))

            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(30, 41, 59)
            word_w = pdf.get_string_width(word) + 2
            pdf.cell(word_w, 6, word)

            if word_type:
                pdf.set_font('Helvetica', 'I', 9)
                pdf.set_text_color(148, 163, 184)
                pdf.multi_cell(0, 6, f'  ({word_type})', align='L')
            else:
                pdf.ln(6)

            if defn:
                pdf.set_x(pdf.l_margin + 6)
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(75, 85, 99)
                pdf.multi_cell(W - 6, 5, defn, align='L')

            if example:
                pdf.set_x(pdf.l_margin + 6)
                pdf.set_font('Helvetica', 'I', 10)
                pdf.set_text_color(148, 163, 184)
                pdf.multi_cell(W - 6, 5, f'e.g. {example}', align='L')

            pdf.ln(3)

    pdf_name = 'practice.pdf'
    pdf_path = os.path.join(session_dir, pdf_name)
    pdf.output(pdf_path)
    return pdf_path
