---
name: tamil-pdf
description: Use this skill whenever creating, generating, editing, or formatting PDFs containing Tamil text, Tamil user documents, Tamil stories, or non-Latin Indic scripts. Instructs agents step-by-step how to render dynamic Tamil content into PDF using Playwright HTML-to-PDF with HarfBuzz shaping.
---

# Tamil PDF Generation & Font Rendering Skill Guide

## Core Objective & Rules for Agents

When generating any PDF containing Tamil or Indic script text:

1. **NEVER use standard ReportLab (`pdfmetrics.registerFont` / `TTFont` canvas)** for Tamil text.
   - **Why**: ReportLab lacks an Indic complex script shaping engine (HarfBuzz/ICU). It renders characters sequentially, causing Tamil vowels and diacritics (`ி`, `ீ`, `்`, `ை`) to detach from consonants and display as broken/spaced-out glyphs (`த ம ி ழ ்` instead of `தமிழ்`).
   - **Rule**: **ALWAYS use Playwright HTML-to-PDF (`page.pdf()`) or WeasyPrint**. Chromium's rendering engine uses HarfBuzz script shaping, producing 100% accurate Tamil ligatures and typography matching Google Fonts.

2. **ALWAYS parse the user's prompt dynamically**:
   - Extract the user's requested document title, headings, and text content dynamically from the user's message.
   - Never hardcode fixed story text or sample templates when fulfilling a user prompt.

---

## Workspace Font Specifications

Local TTF font paths available in this repository:
- Regular: `frontend/fonts/AnekTamil-Regular.ttf`
- Bold: `frontend/fonts/AnekTamil-Bold.ttf`
- Variable: `AnekTamil-VariableFont_wdth,wght.ttf`

In CSS, embed the font via `@font-face` using `file://` scheme or load Google Fonts:
```css
@font-face {
  font-family: 'AnekTamil';
  src: url('file:///path/to/frontend/fonts/AnekTamil-Regular.ttf') format('truetype');
  font-weight: 400;
}
@font-face {
  font-family: 'AnekTamil';
  src: url('file:///path/to/frontend/fonts/AnekTamil-Bold.ttf') format('truetype');
  font-weight: 700;
}
```

---

## Agent Step-by-Step Implementation Guide

When an agent needs to create a Tamil PDF for a user request:

### Step 1: Extract Content & Structure
Extract the dynamic text from the user prompt:
- `title`: Main document heading
- `subtitle`: (Optional) Subheading / metadata
- `sections`: List of sections with headings, paragraphs, and optional callout boxes or tables.

### Step 2: Construct HTML String
Construct a valid HTML5 string containing:
- `<meta charset="UTF-8">`
- CSS `@font-face` referencing local `AnekTamil` or `@import url('https://fonts.googleapis.com/css2?family=Anek+Tamil:wght@400;700&display=swap');`
- Clean CSS styling: `font-family: 'AnekTamil', sans-serif; line-height: 1.8; color: #0f172a;`
- Injected user text inside semantic tags (`<h1>`, `<h2>`, `<p>`, `<table>`, etc.).

### Step 3: Render PDF via Playwright
Write a single-use inline Python script using `playwright.async_api`:

```python
import os
import asyncio
from playwright.async_api import async_playwright

async def main():
    # 1. User content & output path
    output_pdf = "pdf_output/target_filename.pdf"
    
    # 2. Dynamic HTML with UTF-8 encoding and Tamil font styling
    html_content = """..."""

    # 3. Render PDF via Playwright Chromium (HarfBuzz shaping)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content, wait_until="networkidle")
        
        abs_output = os.path.abspath(output_pdf)
        os.makedirs(os.path.dirname(abs_output), exist_ok=True)
        
        await page.pdf(
            path=abs_output,
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
        )
        await browser.close()

asyncio.run(main())
```

---

## Verification Checklist for Agents
- [ ] Rendered via Playwright HTML-to-PDF (not ReportLab canvas).
- [ ] Tamil text contains dynamic user input (no hardcoded static story).
- [ ] Output PDF generated successfully and verified.
