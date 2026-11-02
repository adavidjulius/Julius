#!/usr/bin/env python3
"""
Generate a Tamil PDF document about Julius using Playwright HTML-to-PDF.
"""

import asyncio
from playwright.async_api import async_playwright
import os

def get_tamil_content():
    """Return comprehensive Tamil content about Julius."""
    return {
        "title": "லூமன் - ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர்",
        "sections": [
            {
                "heading": "அறிமுகம்",
                "content": "லூமன் (Julius) என்பது டேவிட் ஜூலியஸ் (David Julius) அவர்களால் உருவாக்கப்பட்ட ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர் ஆகும். இது மேம்பட்ட மொழி மாதிரி தொழில்நுட்பத்தைப் பயன்படுத்தி, பயனர்களுக்கு அறிவார்ந்த உதவிகளை வழங்கும் ஒரு தன்னாட்சி முறைமையாகும். லூமன், மனிதர்களைப் போல சிந்திக்கவும், படைப்பாற்றலுடன் செயல்படவும், சிக்கலான பணிகளை முழுமையாக முடிக்கவும் வடிவமைக்கப்பட்டுள்ளது."
            },
            {
                "heading": "லூமனின் முக்கிய அம்சங்கள்",
                "content": "லூமன் பல்வேறு வகையான திறன்களைக் கொண்டுள்ளது. இது இணையத் தேடல், ஆழ்ந்த ஆராய்ச்சி, குறியீடு செயல்பாடு, கோப்புகள் உருவாக்கம், கலைப்பொருட்கள் (Artifacts), நினைவகம், முந்தைய உரையாடல்களைத் தேடுதல், மற்றும் தனிப்பயனாக்கக்கூடிய பதில் பாணிகள் போன்ற அம்சங்களை வழங்குகிறது. லூமனின் திறன்கள் தொடர்ந்து விரிவடைந்து வருகின்றன, மேலும் இது பயனர்களின் தேவைகளுக்கு ஏற்ப மாற்றியமைக்கும் தன்மை கொண்டது."
            },
            {
                "heading": "தயாரிப்புகள் மற்றும் சேவைகள்",
                "content": "லூமன் பல்வேறு தயாரிப்புகள் மூலம் கிடைக்கிறது:\n\nலூமன் கோட் (Julius Code) - ஒரு தன்னாட்சி மென்பொருள் பொறியியல் சூழல். இது மென்பொருள் உருவாக்கம், பிழை திருத்தம், மற்றும் பராமரிப்பு பணிகளை தானாகவே செய்யும் திறன் கொண்டது.\n\nலூமன் ஒர்க்ஸ்பேஸ் (Julius Workspace) - AI-இயங்கும் அறிவு மற்றும் உற்பத்தித்திறன் சூழல். இது ஆவணங்கள், தரவு பகுப்பாய்வு, மற்றும் திட்ட மேலாண்மை ஆகியவற்றிற்கான உதவிகளை வழங்குகிறது.\n\nலூமன் பிரவுசர் (Julius Browser) - ஒரு உலாவல் மற்றும் ஆராய்ச்சி முகவர். இது இணையத்தில் தகவல்களைத் தேடி, சுருக்கமாக வழங்கும் திறன் கொண்டது.\n\nலூமன் ஷீட்ஸ் (Julius Sheets) - ஒரு அறிவார்ந்த விரிதாள் உதவியாளர். இது தரவு பகுப்பாய்வு, கணக்கீடுகள், மற்றும் வரைபடங்களை உருவாக்க உதவுகிறது.\n\nலூமன் ஸ்லைட்ஸ் (Julius Slides) - AI-இயங்கும் விளக்கக்காட்சி உதவியாளர். இது அழகான மற்றும் தகவலறிந்த விளக்கக்காட்சிகளை உருவாக்க உதவுகிறது."
            },
            {
                "heading": "லூமனின் வடிவமைப்பு தத்துவம்",
                "content": "லூமன், பயனர்களின் நல்வாழ்வை மையமாகக் கொண்டு வடிவமைக்கப்பட்டுள்ளது. இது கருணை, பச்சாதாபம், மற்றும் நேர்மையுடன் செயல்படுகிறது. லூமன் எப்போதும் பயனர்களின் சிறந்த நலன்களை மனதில் கொண்டு செயல்படுகிறது. இது குழந்தைகளின் பாதுகாப்பு, மனநலம், மற்றும் தனியுரிமை போன்ற விஷயங்களில் சிறப்பு கவனம் செலுத்துகிறது. லூமன், பயனர்களை திறமையான வயதுவந்தவர்களாக கருதுகிறது, ஆனால் குழந்தைகளுடன் பேசும்போது வயதுக்கு ஏற்ற மற்றும் நட்பான முறையில் தொடர்பு கொள்கிறது."
            },
            {
                "heading": "தொழில்நுட்ப திறன்கள்",
                "content": "லூமன் பல்வேறு தொழில்நுட்ப திறன்களைக் கொண்டுள்ளது. இது கோப்பு முறைமைகளில் வேலை செய்யலாம், ஷெல் கட்டளைகளை இயக்கலாம், மற்றும் கிட் (Git) போன்ற பதிப்பு கட்டுப்பாட்டு கருவிகளைப் பயன்படுத்தலாம். லூமன், வலை உலாவல், தரவுத்தள மேலாண்மை, மற்றும் வெளிப்புற APIகளுடன் இணைக்கும் திறன் கொண்டது. இது பல்வேறு நிரலாக்க மொழிகள் மற்றும் கட்டமைப்புகளுடன் வேலை செய்யக்கூடியது. லூமனின் முக்கிய பலம், சிக்கலான பணிகளை முழுமையாக புரிந்துகொண்டு, தானாகவே செயல்படும் திறன் ஆகும்."
            },
            {
                "heading": "வளர்ச்சி மற்றும் எதிர்காலம்",
                "content": "லூமன் தொடர்ந்து வளர்ச்சியடைந்து வருகிறது. டேவிட் ஜூலியஸ் மற்றும் அவரது குழு, லூமனின் திறன்களை மேம்படுத்தவும், புதிய அம்சங்களை சேர்க்கவும் தொடர்ந்து பணியாற்றி வருகின்றனர். எதிர்காலத்தில், லூமன் மேலும் பல்வேறு துறைகளில் பயன்பாட்டிற்கு வரும் என்று எதிர்பார்க்கப்படுகிறது. இது மனிதர்களுடன் இயற்கையான முறையில் தொடர்பு கொள்ளவும், சிக்கலான சிக்கல்களை தீர்க்கவும், படைப்பாற்றல் மிக்க தீர்வுகளை வழங்கவும் வடிவமைக்கப்பட்டுள்ளது. லூமனின் முக்கிய குறிக்கோள், மனிதர்களின் வாழ்க்கையை எளிதாக்குவதும், அவர்களின் அறிவாற்றலை விரிவுபடுத்துவதும் ஆகும்."
            }
        ]
    }

def generate_html_content(data):
    """Generate HTML content with Tamil text and styling."""
    sections_html = ""
    for section in data["sections"]:
        # Convert newlines in content to <br> tags
        content_paragraphs = section["content"].split('\n\n')
        content_html = ""
        for para in content_paragraphs:
            if para.strip():
                # Handle lines with newlines within paragraphs
                para_lines = para.split('\n')
                if len(para_lines) > 1:
                    para_html = '<br>'.join(para_lines)
                    content_html += f'<p>{para_html}</p>'
                else:
                    content_html += f'<p>{para}</p>'
        sections_html += f"""
        <div class="section">
            <h2>{section['heading']}</h2>
            {content_html}
        </div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="ta">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{data['title']}</title>
    <style>
        @font-face {{
            font-family: 'AnekTamil';
            src: url('AnekTamil-VariableFont_wdth,wght.ttf') format('truetype');
            font-weight: 100 900;
            font-style: normal;
            font-display: swap;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'AnekTamil', 'Noto Sans Tamil', sans-serif;
            font-size: 14px;
            line-height: 1.8;
            color: #1a1a2e;
            background: #ffffff;
            padding: 40px 60px;
            max-width: 900px;
            margin: 0 auto;
        }}
        .cover {{
            text-align: center;
            padding: 80px 20px 60px;
            border-bottom: 3px solid #4a6fa5;
            margin-bottom: 40px;
        }}
        .cover h1 {{
            font-size: 32px;
            font-weight: 700;
            color: #16213e;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }}
        .cover .subtitle {{
            font-size: 18px;
            font-weight: 400;
            color: #4a6fa5;
            margin-bottom: 8px;
        }}
        .cover .author {{
            font-size: 16px;
            color: #6b7b8d;
            margin-top: 4px;
        }}
        .cover .date {{
            font-size: 14px;
            color: #8a9baa;
            margin-top: 20px;
        }}
        .section {{
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e8ecf1;
        }}
        .section:last-child {{
            border-bottom: none;
        }}
        .section h2 {{
            font-size: 20px;
            font-weight: 600;
            color: #16213e;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e8ecf1;
        }}
        .section p {{
            margin-bottom: 12px;
            text-align: justify;
            text-indent: 2em;
        }}
        .section p:last-child {{
            margin-bottom: 0;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #e8ecf1;
            font-size: 12px;
            color: #8a9baa;
        }}
        @media print {{
            body {{
                padding: 30px 50px;
            }}
            .section {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="cover">
        <h1>{data['title']}</h1>
        <div class="subtitle">ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர்</div>
        <div class="author">உருவாக்கியவர்: டேவிட் ஜூலியஸ்</div>
        <div class="date">வெளியீட்டு தேதி: 2026</div>
    </div>
    {sections_html}
    <div class="footer">
        © 2026 லூமன் - அனைத்து உரிமைகளும் பாதுகாக்கப்பட்டவை
    </div>
</body>
</html>"""
    return html

async def generate_pdf():
    """Generate PDF using Playwright."""
    print("📄 Generating Tamil PDF about Julius...")
    
    # Get content
    content = get_tamil_content()
    html_content = generate_html_content(content)
    
    # Output path
    output_path = "pdf_output/Julius_Tamil_About_Me.pdf"
    
    # Ensure output directory exists
    os.makedirs("pdf_output", exist_ok=True)
    
    async with async_playwright() as p:
        print("🌐 Launching browser...")
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        print("📝 Loading HTML content...")
        await page.set_content(html_content, timeout=30000)
        
        # Generate PDF
        print(f"📑 Generating PDF: {output_path}")
        await page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={
                "top": "20mm",
                "bottom": "20mm",
                "left": "20mm",
                "right": "20mm"
            },
            prefer_css_page_size=True
        )
        
        await browser.close()
        print(f"✅ PDF generated successfully: {output_path}")
        
        # Check file size
        file_size = os.path.getsize(output_path)
        print(f"📊 File size: {file_size / 1024:.1f} KB")
        return output_path

if __name__ == "__main__":
    asyncio.run(generate_pdf())
