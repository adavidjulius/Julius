#!/usr/bin/env python3
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def register_fonts():
    """Register the Anek Tamil font if available, otherwise fallback to Helvetica."""
    font_path = "AnekTamil-VariableFont_wdth,wght.ttf"
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont('AnekTamil', font_path))
            return 'AnekTamil'
        except Exception:
            pass
    return 'Helvetica'

def build_pdf(md_path: Path, output_path: Path):
    font_name = register_fonts()
    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(name='Title', parent=styles['Heading1'],
                               fontName=font_name, fontSize=24,
                               textColor=colors.HexColor('#1a237e'), alignment=TA_LEFT,
                               spaceAfter=24)
    heading_style = ParagraphStyle(name='Heading', parent=styles['Heading2'],
                                 fontName=font_name, fontSize=18,
                                 textColor=colors.HexColor('#1a237e'), alignment=TA_LEFT,
                                 spaceAfter=12)
    body_style = ParagraphStyle(name='Body', parent=styles['Normal'],
                               fontName=font_name, fontSize=12,
                               leading=16, spaceAfter=8)
    content = []
    with md_path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('## '):
                content.append(Paragraph(line[3:], heading_style))
                content.append(Spacer(1, 12))
            elif line.startswith('# '):
                content.append(Paragraph(line[2:], title_style))
                content.append(Spacer(1, 12))
            elif line.strip():
                content.append(Paragraph(line, body_style))
                content.append(Spacer(1, 6))
    doc.build(content)
    print(f"PDF generated at {output_path}")

if __name__ == '__main__':
    md_file = Path('limitation_summary.md')
    out_file = Path('pdf_output') / 'Julius_Limitations.pdf'
    build_pdf(md_file, out_file)
