#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a beautiful PDF about Julius in Tamil.
Uses the AnekTamil font for proper Tamil rendering.
"""

import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle

def register_tamil_font():
    """Register the AnekTamil font for PDF rendering."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    regular_path = os.path.join(base_dir, 'frontend', 'fonts', 'AnekTamil-Regular.ttf')
    bold_path = os.path.join(base_dir, 'frontend', 'fonts', 'AnekTamil-Bold.ttf')

    if not os.path.exists(regular_path):
        regular_path = os.path.join(base_dir, 'AnekTamil-VariableFont_wdth,wght.ttf')
        bold_path = regular_path

    pdfmetrics.registerFont(TTFont('AnekTamil', regular_path))
    pdfmetrics.registerFont(TTFont('AnekTamil-Bold', bold_path))
    return 'AnekTamil', 'AnekTamil-Bold'

def create_julius_tamil_pdf(output_path="pdf_output/Julius_Tamil_About_Me.pdf"):
    font_reg, font_bold = register_tamil_font()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TamilTitle',
        parent=styles['Heading1'],
        fontName=font_bold,
        fontSize=26,
        leading=34,
        textColor=colors.HexColor('#0F172A'),
        alignment=1,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        'TamilSubTitle',
        parent=styles['Normal'],
        fontName=font_reg,
        fontSize=16,
        leading=22,
        textColor=colors.HexColor('#3B82F6'),
        alignment=1,
        spaceAfter=6
    )

    author_style = ParagraphStyle(
        'TamilAuthor',
        parent=styles['Normal'],
        fontName=font_reg,
        fontSize=14,
        leading=20,
        textColor=colors.HexColor('#64748B'),
        alignment=1,
        spaceAfter=20
    )

    heading_style = ParagraphStyle(
        'TamilHeading',
        parent=styles['Heading2'],
        fontName=font_bold,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=16,
        spaceAfter=8
    )

    body_style = ParagraphStyle(
        'TamilBody',
        parent=styles['Normal'],
        fontName=font_reg,
        fontSize=12,
        leading=21,
        textColor=colors.HexColor('#334155'),
        spaceAfter=10
    )

    story = []

    # Title & Subtitle
    story.append(Paragraph("லூமன்", title_style))
    story.append(Paragraph("ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர்", subtitle_style))
    story.append(Paragraph("Julius - An Autonomous AI Assistant", author_style))
    story.append(Paragraph("உருவாக்கியவர்: டேவிட் ஜூலியஸ் (David Julius)", author_style))
    story.append(Paragraph("வெளியீட்டு ஆண்டு: 2026", subtitle_style))
    story.append(HRFlowable(width="80%", thickness=2, color=colors.HexColor('#3B82F6'), spaceAfter=20))

    # Section 1: Introduction
    story.append(Paragraph("1. அறிமுகம்", heading_style))
    story.append(Paragraph(
        "லூமன் (Julius) என்பது டேவிட் ஜூலியஸ் (David Julius) அவர்களால் உருவாக்கப்பட்ட ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர் ஆகும். "
        "இது மேம்பட்ட மொழி மாதிரி தொழில்நுட்பத்தைப் பயன்படுத்தி, பயனர்களுக்கு அறிவார்ந்த உதவிகளை வழங்கும் ஒரு தன்னாட்சி முறைமையாகும். "
        "லூமன், மனிதர்களைப் போல சிந்திக்கவும், படைப்பாற்றலுடன் செயல்படவும், சிக்கலான பணிகளை முழுமையாக முடிக்கவும் வடிவமைக்கப்பட்டுள்ளது.",
        body_style
    ))

    # Section 2: Key Features
    story.append(Paragraph("2. முக்கிய அம்சங்கள்", heading_style))
    story.append(Paragraph(
        "லூமன் பல்வேறு வகையான திறன்களைக் கொண்டுள்ளது. இது இணையத் தேடல், ஆழ்ந்த ஆராய்ச்சி, குறியீடு செயல்பாடு, "
        "கோப்புகள் உருவாக்கம், கலைப்பொருட்கள் (Artifacts), நினைவகம், முந்தைய உரையாடல்களைத் தேடுதல், "
        "மற்றும் தனிப்பயனாக்கக்கூடிய பதில் பாணிகள் போன்ற அம்சங்களை வழங்குகிறது. "
        "லூமனின் திறன்கள் தொடர்ந்து விரிவடைந்து வருகின்றன, மேலும் இது பயனர்களின் தேவைகளுக்கு ஏற்ப மாற்றியமைக்கும் தன்மை கொண்டது.",
        body_style
    ))

    # Section 3: Products
    story.append(Paragraph("3. தயாரிப்புகள் மற்றும் சேவைகள்", heading_style))
    products = [
        ("லூமன் கோட் (Julius Code)", "ஒரு தன்னாட்சி மென்பொருள் பொறியியல் சூழல். மென்பொருள் உருவாக்கம், பிழை திருத்தம், மற்றும் பராமரிப்பு பணிகளை தானாகவே செய்யும் திறன் கொண்டது."),
        ("லூமன் ஒர்க்ஸ்பேஸ் (Julius Workspace)", "AI-இயங்கும் அறிவு மற்றும் உற்பத்தித்திறன் சூழல். ஆவணங்கள், தரவு பகுப்பாய்வு, மற்றும் திட்ட மேலாண்மைக்கான உதவிகளை வழங்குகிறது."),
        ("லூமன் பிரவுசர் (Julius Browser)", "ஒரு உலாவல் மற்றும் ஆராய்ச்சி முகவர். இணையத்தில் தகவல்களைத் தேடி, சுருக்கமாக வழங்கும் திறன் கொண்டது."),
        ("லூமன் ஷீட்ஸ் (Julius Sheets)", "ஒரு அறிவார்ந்த விரிதாள் உதவியாளர். தரவு பகுப்பாய்வு, கணக்கீடுகள், மற்றும் வரைபடங்களை உருவாக்க உதவுகிறது."),
        ("லூமன் ஸ்லைட்ஸ் (Julius Slides)", "AI-இயங்கும் விளக்கக்காட்சி உதவியாளர். அழகான மற்றும் தகவலறிந்த விளக்கக்காட்சிகளை உருவாக்க உதவுகிறது.")
    ]
    for name, desc in products:
        story.append(Paragraph(f"<b>{name}</b>", body_style))
        story.append(Paragraph(desc, body_style))

    # Section 4: Design Philosophy
    story.append(Paragraph("4. வடிவமைப்பு தத்துவம்", heading_style))
    story.append(Paragraph(
        "லூமன், பயனர்களின் நல்வாழ்வை மையமாகக் கொண்டு வடிவமைக்கப்பட்டுள்ளது. "
        "இது கருணை, பச்சாதாபம், மற்றும் நேர்மையுடன் செயல்படுகிறது. "
        "லூமன் எப்போதும் பயனர்களின் சிறந்த நலன்களை மனதில் கொண்டு செயல்படுகிறது. "
        "இது குழந்தைகளின் பாதுகாப்பு, மனநலம், மற்றும் தனியுரிமை போன்ற விஷயங்களில் சிறப்பு கவனம் செலுத்துகிறது. "
        "லூமன், பயனர்களை திறமையான வயதுவந்தவர்களாக கருதுகிறது, ஆனால் குழந்தைகளுடன் பேசும்போது "
        "வயதுக்கு ஏற்ற மற்றும் நட்பான முறையில் தொடர்பு கொள்கிறது.",
        body_style
    ))

    # Section 5: Technical Capabilities
    story.append(Paragraph("5. தொழில்நுட்ப திறன்கள்", heading_style))
    story.append(Paragraph(
        "லூமன் பல்வேறு தொழில்நுட்ப திறன்களைக் கொண்டுள்ளது. "
        "இது கோப்பு முறைமைகளில் வேலை செய்யலாம், ஷெல் கட்டளைகளை இயக்கலாம், "
        "மற்றும் கிட் (Git) போன்ற பதிப்பு கட்டுப்பாட்டு கருவிகளைப் பயன்படுத்தலாம். "
        "லூமன், வலை உலாவல், தரவுத்தள மேலாண்மை, மற்றும் வெளிப்புற APIகளுடன் இணைக்கும் திறன் கொண்டது. "
        "இது பல்வேறு நிரலாக்க மொழிகள் மற்றும் கட்டமைப்புகளுடன் வேலை செய்யக்கூடியது. "
        "லூமனின் முக்கிய பலம், சிக்கலான பணிகளை முழுமையாக புரிந்துகொண்டு, தானாகவே செயல்படும் திறன் ஆகும்.",
        body_style
    ))

    # Section 6: Future
    story.append(Paragraph("6. வளர்ச்சி மற்றும் எதிர்காலம்", heading_style))
    story.append(Paragraph(
        "லூமன் தொடர்ந்து வளர்ச்சியடைந்து வருகிறது. "
        "டேவிட் ஜூலியஸ் மற்றும் அவரது குழு, லூமனின் திறன்களை மேம்படுத்தவும், "
        "புதிய அம்சங்களை சேர்க்கவும் தொடர்ந்து பணியாற்றி வருகின்றனர். "
        "எதிர்காலத்தில், லூமன் மேலும் பல்வேறு துறைகளில் பயன்பாட்டிற்கு வரும் என்று எதிர்பார்க்கப்படுகிறது. "
        "இது மனிதர்களுடன் இயற்கையான முறையில் தொடர்பு கொள்ளவும், சிக்கலான சிக்கல்களை தீர்க்கவும், "
        "படைப்பாற்றல் மிக்க தீர்வுகளை வழங்கவும் வடிவமைக்கப்பட்டுள்ளது. "
        "லூமனின் முக்கிய குறிக்கோள், மனிதர்களின் வாழ்க்கையை எளிதாக்குவதும், "
        "அவர்களின் அறிவாற்றலை விரிவுபடுத்துவதும் ஆகும்.",
        body_style
    ))

    # Footer
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=10))
    story.append(Paragraph("© 2026 லூமன் - அனைத்து உரிமைகளும் பாதுகாக்கப்பட்டவை", subtitle_style))

    doc.build(story)
    print(f"✅ Successfully generated Tamil PDF about Julius: {output_path}")
    return output_path

if __name__ == "__main__":
    create_julius_tamil_pdf()
