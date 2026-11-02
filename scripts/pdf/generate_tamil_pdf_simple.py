#!/usr/bin/env python3
"""Generate Tamil PDF using Playwright."""
import asyncio
from playwright.async_api import async_playwright
import os

HTML = '''<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<title>லூமன் - Julius</title>
<link href="https://fonts.googleapis.com/css2?family=Anek+Tamil:wght@400;700&display=swap" rel="stylesheet">
<style>
body { font-family: 'Anek Tamil', sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; line-height: 1.8; }
h1 { color: #1a1a2e; text-align: center; font-size: 28px; }
h2 { color: #16213e; border-bottom: 2px solid #4a6fa5; padding-bottom: 8px; }
.cover { text-align: center; padding: 60px 20px 40px; border-bottom: 3px solid #4a6fa5; margin-bottom: 30px; }
.section { margin-bottom: 25px; }
p { text-align: justify; text-indent: 2em; }
.footer { text-align: center; margin-top: 40px; padding-top: 20px; border-top: 2px solid #e8ecf1; color: #8a9baa; font-size: 12px; }
</style>
</head>
<body>
<div class="cover">
<h1>லூமன் - ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர்</h1>
<p style="text-indent:0;text-align:center;color:#4a6fa5;font-size:18px;">Julius - An Autonomous AI Assistant</p>
<p style="text-indent:0;text-align:center;color:#6b7b8d;">உருவாக்கியவர்: டேவிட் ஜூலியஸ் (David Julius)</p>
<p style="text-indent:0;text-align:center;color:#8a9baa;">2026</p>
</div>

<div class="section">
<h2>அறிமுகம்</h2>
<p>லூமன் (Julius) என்பது டேவிட் ஜூலியஸ் அவர்களால் உருவாக்கப்பட்ட ஒரு சுயாதீன செயற்கை நுண்ணறிவு உதவியாளர் ஆகும். இது மேம்பட்ட மொழி மாதிரி தொழில்நுட்பத்தைப் பயன்படுத்தி, பயனர்களுக்கு அறிவார்ந்த உதவிகளை வழங்கும் ஒரு தன்னாட்சி முறைமையாகும். லூமன், மனிதர்களைப் போல சிந்திக்கவும், படைப்பாற்றலுடன் செயல்படவும், சிக்கலான பணிகளை முழுமையாக முடிக்கவும் வடிவமைக்கப்பட்டுள்ளது.</p>
</div>

<div class="section">
<h2>முக்கிய அம்சங்கள்</h2>
<p>லூமன் இணையத் தேடல், ஆழ்ந்த ஆராய்ச்சி, குறியீடு செயல்பாடு, கோப்புகள் உருவாக்கம், கலைப்பொருட்கள், நினைவகம், முந்தைய உரையாடல்களைத் தேடுதல், மற்றும் தனிப்பயனாக்கக்கூடிய பதில் பாணிகள் போன்ற அம்சங்களை வழங்குகிறது. லூமனின் திறன்கள் தொடர்ந்து விரிவடைந்து வருகின்றன.</p>
</div>

<div class="section">
<h2>தயாரிப்புகள்</h2>
<p><strong>லூமன் கோட் (Julius Code)</strong> - தன்னாட்சி மென்பொருள் பொறியியல் சூழல். மென்பொருள் உருவாக்கம், பிழை திருத்தம், பராமரிப்பு பணிகளை தானாக செய்யும்.</p>
<p><strong>லூமன் ஒர்க்ஸ்பேஸ் (Julius Workspace)</strong> - AI-இயங்கும் அறிவு மற்றும் உற்பத்தித்திறன் சூழல். ஆவணங்கள், தரவு பகுப்பாய்வு, திட்ட மேலாண்மைக்கான உதவிகள்.</p>
<p><strong>லூமன் பிரவுசர் (Julius Browser)</strong> - உலாவல் மற்றும் ஆராய்ச்சி முகவர். இணையத்தில் தகவல்களைத் தேடி சுருக்கமாக வழங்கும்.</p>
<p><strong>லூமன் ஷீட்ஸ் (Julius Sheets)</strong> - அறிவார்ந்த விரிதாள் உதவியாளர். தரவு பகுப்பாய்வு, கணக்கீடுகள், வரைபடங்களை உருவாக்க உதவும்.</p>
<p><strong>லூமன் ஸ்லைட்ஸ் (Julius Slides)</strong> - AI-இயங்கும் விளக்கக்காட்சி உதவியாளர். அழகான மற்றும் தகவலறிந்த விளக்கக்காட்சிகளை உருவாக்கும்.</p>
</div>

<div class="section">
<h2>வடிவமைப்பு தத்துவம்</h2>
<p>லூமன் பயனர்களின் நல்வாழ்வை மையமாகக் கொண்டு வடிவமைக்கப்பட்டுள்ளது. கருணை, பச்சாதாபம், நேர்மையுடன் செயல்படுகிறது. குழந்தைகளின் பாதுகாப்பு, மனநலம், தனியுரிமை போன்றவற்றில் சிறப்பு கவனம் செலுத்துகிறது.</p>
</div>

<div class="section">
<h2>தொழில்நுட்ப திறன்கள்</h2>
<p>லூமன் கோப்பு முறைமைகளில் வேலை செய்யலாம், ஷெல் கட்டளைகளை இயக்கலாம், கிட் போன்ற பதிப்பு கட்டுப்பாட்டு கருவிகளைப் பயன்படுத்தலாம். வலை உலாவல், தரவுத்தள மேலாண்மை, வெளிப்புற APIகளுடன் இணைக்கும் திறன் கொண்டது.</p>
</div>

<div class="section">
<h2>வளர்ச்சி மற்றும் எதிர்காலம்</h2>
<p>லூமன் தொடர்ந்து வளர்ச்சியடைந்து வருகிறது. டேவிட் ஜூலியஸ் மற்றும் அவரது குழு புதிய அம்சங்களை சேர்க்க தொடர்ந்து பணியாற்றி வருகின்றனர். மனிதர்களுடன் இயற்கையாக தொடர்பு கொள்ளவும், சிக்கலான சிக்கல்களை தீர்க்கவும் வடிவமைக்கப்பட்டுள்ளது.</p>
</div>

<div class="footer">© 2026 லூமன் - அனைத்து உரிமைகளும் பாதுகாக்கப்பட்டவை</div>
</body>
</html>'''

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(HTML)
        os.makedirs("pdf_output", exist_ok=True)
        await page.pdf(path="pdf_output/Julius_Tamil_About.pdf", format="A4", print_background=True)
        await browser.close()
        print("✅ PDF generated: pdf_output/Julius_Tamil_About.pdf")

if __name__ == "__main__":
    asyncio.run(main())
