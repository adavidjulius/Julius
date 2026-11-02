#!/usr/bin/env python3
"""
Generate vector SVG logo assets and high-resolution raster icons for Julius Logo.
Source: Uploaded high-fidelity logo image
Color: #7ED321 (Primary Green)
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_IMG = Path(os.environ.get("LOGO_UPLOAD_IMG", "/tmp/logo.png"))
SCRATCH_DIR = Path(os.environ.get("SCRATCH_DIR", "/tmp/scratch"))

JULIUS_LOGO_DIR = WORKSPACE_ROOT / "Julius Logo"
JULIUS_LOGO_SVG_DIR = JULIUS_LOGO_DIR / "svg"
JULIUS_LOGO_PNG_DIR = JULIUS_LOGO_DIR / "png"
ROOT_SVG_DIR = WORKSPACE_ROOT / "svg"

PRIMARY_COLOR = "#7ED321"

def extract_normalized_path():
    """Extract smooth subpixel bezier path from uploaded image using Potrace 2x Lanczos upsampling."""
    img = Image.open(UPLOAD_IMG)
    alpha = img.split()[-1]
    
    # 2x Lanczos upsample for subpixel anti-aliasing curve fitting
    w, h = 576 * 2, 576 * 2
    up = alpha.resize((w, h), Image.Resampling.LANCZOS)
    bmp_path = SCRATCH_DIR / "mask_2x_run.bmp"
    up.point(lambda p: 0 if p > 128 else 255).save(bmp_path)
    
    svg_temp = SCRATCH_DIR / "trace_2x_run.svg"
    subprocess.run([
        'potrace', '-s',
        '-a', '1.0',
        '-O', '0.2',
        '-C', PRIMARY_COLOR,
        '-o', str(svg_temp),
        str(bmp_path)
    ], check=True)
    
    with open(svg_temp) as f:
        content = f.read()
    
    m = re.search(r'd="([^"]+)"', content)
    d_raw = m.group(1)
    
    # Normalize potrace output (scale 0.05, flip Y coordinate from 576)
    tokens = re.findall(r'([A-Za-z]|[-+]?[0-9]+(?:\.[0-9]+)?)', d_raw)
    out_tokens = []
    i = 0
    scale = 0.05
    target_height = 576
    
    while i < len(tokens):
        tok = tokens[i]
        if tok == 'M':
            x = float(tokens[i+1]) * scale
            y = target_height - float(tokens[i+2]) * scale
            out_tokens.append(f'M {x:.2f} {y:.2f}')
            i += 3
        elif tok == 'c':
            out_tokens.append('c')
            i += 1
            while i < len(tokens) and not tokens[i].isalpha():
                dx1 = float(tokens[i]) * scale
                dy1 = -float(tokens[i+1]) * scale
                dx2 = float(tokens[i+2]) * scale
                dy2 = -float(tokens[i+3]) * scale
                dx = float(tokens[i+4]) * scale
                dy = -float(tokens[i+5]) * scale
                out_tokens.append(f'{dx1:.2f} {dy1:.2f} {dx2:.2f} {dy2:.2f} {dx:.2f} {dy:.2f}')
                i += 6
        elif tok == 'l':
            out_tokens.append('l')
            i += 1
            while i < len(tokens) and not tokens[i].isalpha():
                dx = float(tokens[i]) * scale
                dy = -float(tokens[i+1]) * scale
                out_tokens.append(f'{dx:.2f} {dy:.2f}')
                i += 2
        elif tok in ('z', 'Z'):
            out_tokens.append('Z')
            i += 1
        else:
            i += 1
            
    return ' '.join(out_tokens)

def scale_path(d_str, factor):
    tokens = re.findall(r'([A-Za-z]|[-+]?[0-9]+(?:\.[0-9]+)?)', d_str)
    out = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            out.append(tok)
            i += 1
        else:
            val = float(tok) * factor
            out.append(f'{val:.2f}')
            i += 1
    return ' '.join(out)

def create_svg_markup(path_d, width=None, height=None, view_box="0 0 512 512", fill=PRIMARY_COLOR, background=None, rx=None):
    dims = ""
    if width and height:
        dims = f'width="{width}" height="{height}" '
    else:
        dims = 'width="100%" height="100%" '
        
    bg_element = ""
    if background:
        if rx:
            bg_element = f'  <rect width="100%" height="100%" rx="{rx}" fill="{background}" />\n'
        else:
            bg_element = f'  <rect width="100%" height="100%" fill="{background}" />\n'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" {dims}viewBox="{view_box}">
{bg_element}  <path fill="{fill}" d="{path_d}" />
</svg>
'''

def main():
    print("🚀 Extracting normalized vector curves...")
    path_576 = extract_normalized_path()
    path_512 = scale_path(path_576, 512.0 / 576.0)
    
    # Ensure output directories exist
    JULIUS_LOGO_SVG_DIR.mkdir(parents=True, exist_ok=True)
    JULIUS_LOGO_PNG_DIR.mkdir(parents=True, exist_ok=True)
    ROOT_SVG_DIR.mkdir(parents=True, exist_ok=True)
    
    sizes = [16, 24, 32, 48, 64, 96, 128, 180, 192, 256, 384, 512, 1024]
    
    svg_files = {}
    
    # 1. Responsive Master Logo
    svg_files["logo.svg"] = create_svg_markup(path_512, view_box="0 0 512 512", fill=PRIMARY_COLOR)
    
    # 2. Original Canvas (576x576)
    svg_files["logo-original.svg"] = create_svg_markup(path_576, width=576, height=576, view_box="0 0 576 576", fill=PRIMARY_COLOR)
    
    # 3. Favicon SVG
    svg_files["favicon.svg"] = create_svg_markup(path_512, width=32, height=32, view_box="0 0 512 512", fill=PRIMARY_COLOR)

    # 4. Monochrome Variations
    svg_files["logo-white.svg"] = create_svg_markup(path_512, view_box="0 0 512 512", fill="#FFFFFF")
    svg_files["logo-black.svg"] = create_svg_markup(path_512, view_box="0 0 512 512", fill="#000000")
    
    # 5. Badge Variations (Squircle / App Icon style)
    svg_files["logo-badge-dark.svg"] = create_svg_markup(path_512, width=512, height=512, view_box="0 0 512 512", fill=PRIMARY_COLOR, background="#0F172A", rx="115")
    svg_files["logo-badge-light.svg"] = create_svg_markup(path_512, width=512, height=512, view_box="0 0 512 512", fill=PRIMARY_COLOR, background="#FFFFFF", rx="115")
    
    # 6. Sized SVGs
    for s in sizes:
        svg_files[f"logo-{s}x{s}.svg"] = create_svg_markup(path_512, width=s, height=s, view_box="0 0 512 512", fill=PRIMARY_COLOR)
    
    # Write SVG files to both Julius Logo/svg/ and svg/
    print(f"📦 Writing {len(svg_files)} SVG variants...")
    for filename, content in svg_files.items():
        # Destination 1: Julius Logo/svg/
        dest1 = JULIUS_LOGO_SVG_DIR / filename
        with open(dest1, "w", encoding="utf-8") as f:
            f.write(content)
            
        # Destination 2: svg/
        dest2 = ROOT_SVG_DIR / filename
        with open(dest2, "w", encoding="utf-8") as f:
            f.write(content)
            
    # Also write default logo.svg directly inside Julius Logo/
    shutil.copyfile(JULIUS_LOGO_SVG_DIR / "logo.svg", JULIUS_LOGO_DIR / "logo.svg")
    
    # Render high-resolution PNGs using Playwright
    print("🎨 Rendering pixel-perfect PNGs for all sizes...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        for s in sizes:
            page = browser.new_page(viewport={"width": s, "height": s})
            svg_content = svg_files[f"logo-{s}x{s}.svg"]
            html = f"""<!DOCTYPE html>
<html>
<head>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {s}px; height: {s}px; overflow: hidden; background: transparent; }}
svg {{ width: {s}px; height: {s}px; display: block; }}
</style>
</head>
<body>
{svg_content}
</body>
</html>"""
            page.set_content(html)
            png_dest = JULIUS_LOGO_PNG_DIR / f"logo-{s}x{s}.png"
            page.screenshot(path=str(png_dest), omit_background=True)
            
        # Render Badge PNGs
        for badge_name, badge_file in [("badge-dark", "logo-badge-dark.svg"), ("badge-light", "logo-badge-light.svg")]:
            page = browser.new_page(viewport={"width": 512, "height": 512})
            html = f"""<!DOCTYPE html><html><body style="margin:0;overflow:hidden">{svg_files[badge_file]}</body></html>"""
            page.set_content(html)
            page.screenshot(path=str(JULIUS_LOGO_PNG_DIR / f"logo-{badge_name}-512x512.png"))

        browser.close()
        
    # Copy master 1024x1024 PNG as 'Julius Logo.png'
    shutil.copyfile(JULIUS_LOGO_PNG_DIR / "logo-1024x1024.png", WORKSPACE_ROOT / "Julius Logo.png")
    shutil.copyfile(JULIUS_LOGO_PNG_DIR / "logo-1024x1024.png", JULIUS_LOGO_DIR / "Julius Logo.png")
    
    # Generate favicon.ico (multi-size: 16x16, 32x32, 48x48)
    print("🌐 Generating multi-resolution favicon.ico...")
    img16 = Image.open(JULIUS_LOGO_PNG_DIR / "logo-16x16.png")
    img32 = Image.open(JULIUS_LOGO_PNG_DIR / "logo-32x32.png")
    img48 = Image.open(JULIUS_LOGO_PNG_DIR / "logo-48x48.png")
    
    ico_dest = JULIUS_LOGO_DIR / "favicon.ico"
    img32.save(ico_dest, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[img16, img48])
    shutil.copyfile(ico_dest, JULIUS_LOGO_PNG_DIR / "favicon.ico")
    shutil.copyfile(ico_dest, ROOT_SVG_DIR / "favicon.ico")

    # Generate macOS icon.icns if iconutil is available
    print("🍏 Generating macOS iconset and icon.icns...")
    iconset_dir = SCRATCH_DIR / "icon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)
    
    src_master = JULIUS_LOGO_PNG_DIR / "logo-1024x1024.png"
    icon_specs = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    
    master_img = Image.open(src_master)
    for fname, sz in icon_specs:
        resized = master_img.resize((sz, sz), Image.Resampling.LANCZOS)
        resized.save(iconset_dir / fname)
        
    assets_dir = WORKSPACE_ROOT / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(assets_dir / "icon.icns")], check=True)
        shutil.copyfile(assets_dir / "icon.icns", JULIUS_LOGO_DIR / "icon.icns")
        print("✅ Successfully generated icon.icns in assets/ and Julius Logo/")
    except Exception as e:
        print(f"⚠️ Note on iconutil: {e}")

    # Generate README documentation
    readme_content = f"""# Julius Logo Asset Pack

High-fidelity vector SVG and raster icons generated from the official Julius logo artwork.

## Color Palette
- **Primary Green**: `{PRIMARY_COLOR}`
  - RGB: `rgb(126, 211, 33)`
  - HSL: `hsl(93, 73%, 48%)`
- **Monochrome White**: `#FFFFFF`
- **Monochrome Black**: `#000000`
- **Badge Dark BG**: `#0F172A`

---

## Directory Structure

```
Julius Logo/
├── logo.svg                     # Master responsive SVG (viewBox 0 0 512 512)
├── Julius Logo.png              # Master high-res 1024x1024 PNG
├── favicon.ico                  # Multi-resolution ICO (16x16, 32x32, 48x48)
├── icon.icns                    # macOS Apple Icon Image
├── svg/
│   ├── logo.svg                 # Fluid scalable vector
│   ├── logo-original.svg        # Original 576x576 canvas
│   ├── favicon.svg              # 32x32 SVG favicon
│   ├── logo-white.svg           # Monochrome white (for dark mode)
│   ├── logo-black.svg           # Monochrome black (for print)
│   ├── logo-badge-dark.svg      # App icon badge on dark slate background
│   ├── logo-badge-light.svg     # App icon badge on white background
│   ├── logo-16x16.svg           # Small favicon
│   ├── logo-24x24.svg           # Toolbar icon
│   ├── logo-32x32.svg           # Standard favicon
│   ├── logo-48x48.svg           # Windows small icon
│   ├── logo-64x64.svg           # Medium icon
│   ├── logo-96x96.svg           # High-DPI icon
│   ├── logo-128x128.svg         # Dock / App icon
│   ├── logo-180x180.svg         # Apple touch icon
│   ├── logo-192x192.svg         # Android PWA home screen
│   ├── logo-256x256.svg         # App store standard
│   ├── logo-384x384.svg         # Android splash icon
│   ├── logo-512x512.svg         # PWA / Web store master
│   └── logo-1024x1024.svg       # Retina display master
└── png/
    ├── logo-16x16.png
    ├── logo-24x24.png
    ├── logo-32x32.png
    ├── logo-48x48.png
    ├── logo-64x64.png
    ├── logo-96x96.png
    ├── logo-128x128.png
    ├── logo-180x180.png
    ├── logo-192x192.png
    ├── logo-256x256.png
    ├── logo-384x384.png
    ├── logo-512x512.png
    ├── logo-1024x1024.png
    ├── logo-badge-dark-512x512.png
    ├── logo-badge-light-512x512.png
    └── favicon.ico
```

The `svg/` directory at the repository root contains identical SVG vector files for direct reference.

---

## Usage Examples

### 1. HTML Web Favicon
```html
<link rel="icon" type="image/svg+xml" href="/svg/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/Julius Logo/png/logo-32x32.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/Julius Logo/png/logo-180x180.png" />
```

### 2. React / JSX Component
```tsx
export function JuliusLogo({{ size = 32, color = "{PRIMARY_COLOR}", className = "" }}: {{ size?: number; color?: string; className?: string }}) {{
  return (
    <svg width={{size}} height={{size}} viewBox="0 0 512 512" fill="none" className={{className}} xmlns="http://www.w3.org/2000/svg">
      <path fill={{color}} d="{path_512}" />
    </svg>
  );
}}
```

### 3. CSS Inline Background
```css
.julius-brand-icon {{
  width: 48px;
  height: 48px;
  background-image: url('/Julius Logo/svg/logo.svg');
  background-repeat: no-repeat;
  background-size: contain;
}}
```
"""
    with open(JULIUS_LOGO_DIR / "README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
        
    print("✨ All logo assets and documentation generated successfully!")

if __name__ == "__main__":
    main()

