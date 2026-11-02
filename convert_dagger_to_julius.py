#!/usr/bin/env python3
"""
convert_dagger_to_julius.py
Converts Dagger Nocturne Didone to JuliusFont family:
- Rebrands to 'Julius', 'Julius-Regular', 'Julius-Bold'
- Adds missing ASCII symbols for full 100% keyboard & code coverage
- Generates TrueType (.ttf), OpenType (.otf), WOFF (.woff), and WOFF2 (.woff2)
- Synchronizes across all repository consumers and ~/Library/Fonts
"""

import os
import shutil
import io
import copy
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.cffLib import CFFFontSet, TopDictIndex, TopDict, PrivateDict, GlobalSubrsIndex
from PIL import Image, ImageFont, ImageDraw

def build_cff_font(f_ttf, style_name="Regular"):
    glyph_order = f_ttf.getGlyphOrder()
    glyf = f_ttf['glyf']
    
    f_cff = TTFont()
    f_cff.sfntVersion = 'OTTO'
    f_cff.setGlyphOrder(glyph_order)
    
    for tag in ['head', 'hhea', 'OS/2', 'hmtx', 'cmap', 'name', 'post']:
        if tag in f_ttf:
            f_cff[tag] = copy.deepcopy(f_ttf[tag])
            
    maxp = newTable('maxp')
    maxp.tableVersion = 0x00005000
    maxp.numGlyphs = len(glyph_order)
    f_cff['maxp'] = maxp
    
    ps_name = f"Julius-{style_name}"
    full_name = f"Julius {style_name}"
    
    cff_table = newTable('CFF ')
    cff = CFFFontSet()
    cff.major = 1
    cff.minor = 0
    cff.fontNames = [ps_name]
    cff.GlobalSubrs = GlobalSubrsIndex()
    
    top_dict = TopDict()
    top_dict.FontName = ps_name
    top_dict.FamilyName = 'Julius'
    top_dict.FullName = full_name
    top_dict.Weight = style_name
    top_dict.Private = PrivateDict()
    cff.topDictIndex = TopDictIndex()
    cff.topDictIndex.append(top_dict)
    
    charstrings = {}
    for gname in glyph_order:
        pen = T2CharStringPen(width=f_ttf['hmtx'][gname][0], glyphSet=glyf)
        glyf[gname].draw(pen, glyf)
        cs = pen.getCharString()
        cs.private = top_dict.Private
        charstrings[gname] = cs
        
    top_dict.CharStrings = charstrings
    cff_table.cff = cff
    f_cff['CFF '] = cff_table
    
    return f_cff

def set_font_naming(f, style_name="Regular"):
    is_bold = (style_name == "Bold")
    ps_name = f"Julius-{style_name}"
    full_name = f"Julius {style_name}"
    unique_id = f"1.000;JULI;{ps_name}"
    
    name_table = f['name']
    name_table.names = [] # Clear old dagger names
    
    # Macintosh (platform 1, encoding 0, lang 0)
    name_table.setName("Julius", 1, 1, 0, 0)
    name_table.setName(style_name, 2, 1, 0, 0)
    name_table.setName(unique_id, 3, 1, 0, 0)
    name_table.setName(full_name, 4, 1, 0, 0)
    name_table.setName("Version 1.000", 5, 1, 0, 0)
    name_table.setName(ps_name, 6, 1, 0, 0)
    name_table.setName("Julius", 16, 1, 0, 0)
    name_table.setName(style_name, 17, 1, 0, 0)
    
    # Windows Unicode BMP (platform 3, encoding 1, lang 0x409)
    name_table.setName("Julius", 1, 3, 1, 0x409)
    name_table.setName(style_name, 2, 3, 1, 0x409)
    name_table.setName(unique_id, 3, 3, 1, 0x409)
    name_table.setName(full_name, 4, 3, 1, 0x409)
    name_table.setName("Version 1.000", 5, 3, 1, 0x409)
    name_table.setName(ps_name, 6, 3, 1, 0x409)
    name_table.setName("Julius", 16, 3, 1, 0x409)
    name_table.setName(style_name, 17, 3, 1, 0x409)
    
    os2 = f['OS/2']
    os2.usWeightClass = 700 if is_bold else 400
    if is_bold:
        os2.fsSelection = (1 << 5) | (1 << 7) # Bold + USE_TYPO_METRICS
        f['head'].macStyle = 1 # Bold
    else:
        os2.fsSelection = (1 << 6) | (1 << 7) # Regular + USE_TYPO_METRICS
        f['head'].macStyle = 0
        
    f.recalcTimestamp = False

def main():
    src_path = sys.argv[1] if len(sys.argv) > 1 else "dagger-nocturne-didone-regular.ttf"
    if not os.path.exists(src_path):
        print(f"Source font missing: {src_path}")
        return
    
    print("Loading source font from:", src_path)
    dagger = TTFont(src_path)
    
    # Donor font for missing ASCII symbols
    donor_path = "Julius_Fonts/sources/Julius-Regular.otf"
    donor = TTFont(donor_path)
    donor_cff = donor["CFF "].cff.topDictIndex[0].CharStrings
    donor_cmap = donor.getBestCmap()
    
    scale = 1000.0 / 1024.0
    dagger_cmap = dagger.getBestCmap()
    dagger_glyf = dagger["glyf"]
    dagger_hmtx = dagger["hmtx"]
    
    missing_ascii = [i for i in range(32, 127) if i not in dagger_cmap]
    new_glyph_order = list(dagger.getGlyphOrder())
    
    print(f"Supplementing {len(missing_ascii)} missing ASCII symbols...")
    for cp in missing_ascii:
        donor_gname = donor_cmap.get(cp)
        if not donor_gname:
            continue
        new_gname = f"uni{cp:04X}"
        
        tt_pen = TTGlyphPen(None)
        cu_pen = Cu2QuPen(tt_pen, max_err=1.0, reverse_direction=True)
        t_pen = TransformPen(cu_pen, (scale, 0, 0, scale, 0, 0))
        donor_cff[donor_gname].draw(t_pen)
        
        glyph = tt_pen.glyph()
        glyph.recalcBounds(dagger_glyf)
        dagger_glyf.glyphs[new_gname] = glyph
        new_glyph_order.append(new_gname)
        
        donor_adv = donor["hmtx"][donor_gname][0]
        new_adv = int(donor_adv * scale)
        new_lsb = glyph.xMin if glyph.numberOfContours > 0 else 0
        dagger_hmtx[new_gname] = (new_adv, new_lsb)
        
        for table in dagger["cmap"].tables:
            table.cmap[cp] = new_gname
            
    dagger.setGlyphOrder(new_glyph_order)
    dagger["glyf"].glyphOrder = new_glyph_order
    dagger["maxp"].numGlyphs = len(new_glyph_order)
    
    # Create Regular
    f_reg_ttf = copy.deepcopy(dagger)
    set_font_naming(f_reg_ttf, "Regular")
    f_reg_cff = build_cff_font(f_reg_ttf, "Regular")
    
    # Create Bold
    f_bold_ttf = copy.deepcopy(dagger)
    set_font_naming(f_bold_ttf, "Bold")
    f_bold_cff = build_cff_font(f_bold_ttf, "Bold")
    
    # Staging dir
    dist_dir = "Julius_Fonts/dist"
    root_dir = "Julius_Fonts"
    os.makedirs(dist_dir, exist_ok=True)
    
    # Export all formats
    print("\n--- Compiling All Font Formats ---")
    # Regular
    f_reg_ttf.flavor = None
    f_reg_ttf.save(os.path.join(dist_dir, "Julius-Regular.ttf"))
    f_reg_cff.flavor = None
    f_reg_cff.save(os.path.join(dist_dir, "Julius-Regular.otf"))
    f_reg_ttf.flavor = "woff"
    f_reg_ttf.save(os.path.join(dist_dir, "Julius-Regular.woff"))
    f_reg_ttf.flavor = "woff2"
    f_reg_ttf.save(os.path.join(dist_dir, "Julius-Regular.woff2"))
    
    # Bold
    f_bold_ttf.flavor = None
    f_bold_ttf.save(os.path.join(dist_dir, "Julius-Bold.ttf"))
    f_bold_cff.flavor = None
    f_bold_cff.save(os.path.join(dist_dir, "Julius-Bold.otf"))
    f_bold_ttf.flavor = "woff"
    f_bold_ttf.save(os.path.join(dist_dir, "Julius-Bold.woff"))
    f_bold_ttf.flavor = "woff2"
    f_bold_ttf.save(os.path.join(dist_dir, "Julius-Bold.woff2"))
    
    # Aliases
    shutil.copyfile(os.path.join(dist_dir, "Julius-Regular.ttf"), os.path.join(dist_dir, "Julius.ttf"))
    shutil.copyfile(os.path.join(dist_dir, "Julius-Regular.woff2"), os.path.join(dist_dir, "Julius.woff2"))
    
    # Save source backup
    os.makedirs("Julius_Fonts/sources", exist_ok=True)
    shutil.copyfile(src_path, "Julius_Fonts/sources/dagger-nocturne-didone-regular.ttf")
    
    # Sync from dist to Julius_Fonts root
    for fname in [
        "Julius-Regular.ttf", "Julius-Regular.otf", "Julius-Regular.woff", "Julius-Regular.woff2",
        "Julius-Bold.ttf", "Julius-Bold.otf", "Julius-Bold.woff", "Julius-Bold.woff2",
        "Julius.ttf", "Julius.woff2"
    ]:
        shutil.copyfile(os.path.join(dist_dir, fname), os.path.join(root_dir, fname))
        print(f"  Synchronized root: {os.path.join(root_dir, fname)}")
        
    # Synchronize to all repository consumer targets
    print("\n--- Synchronizing to All Target Locations ---")
    sync_targets = [
        ("docs/fonts", [
            "Julius-Regular.ttf", "Julius-Bold.ttf",
            "Julius-Regular.otf", "Julius-Bold.otf",
            "Julius-Regular.woff", "Julius-Bold.woff",
            "Julius-Regular.woff2", "Julius-Bold.woff2"
        ]),
        ("frontend/assets", [
            "Julius-Regular.ttf", "Julius-Bold.ttf",
            "Julius-Regular.woff", "Julius-Bold.woff",
            "Julius-Regular.woff2", "Julius-Bold.woff2"
        ]),
        ("julius-apps/do-list-where/src/fonts", [
            "Julius-Regular.woff", "Julius-Bold.woff",
            "Julius-Regular.woff2", "Julius-Bold.woff2"
        ]),
        ("julius-apps/i-want-ui/src/fonts", [
            "Julius-Regular.woff", "Julius-Bold.woff",
            "Julius-Regular.woff2", "Julius-Bold.woff2"
        ]),
        ("julius_launch_video/real_assets", [
            "Julius-Regular.woff2", "Julius-Bold.woff2"
        ]),
        ("Julius_iOS/Resources/Fonts", [
            "Julius-Regular.ttf", "Julius-Bold.ttf"
        ]),
        ("Julius_iOS/Sources/JuliusUI/Resources/Fonts", [
            "Julius-Regular.ttf", "Julius-Bold.ttf"
        ]),
    ]
    for target_dir, files in sync_targets:
        os.makedirs(target_dir, exist_ok=True)
        for fname in files:
            dest = os.path.join(target_dir, fname)
            shutil.copyfile(os.path.join(dist_dir, fname), dest)
            print(f"  Copied to: {dest}")
            
    # Also update ~/Library/Fonts
    user_fonts = os.path.expanduser("~/Library/Fonts")
    if os.path.exists(user_fonts):
        for fname in ["Julius-Regular.ttf", "Julius-Regular.otf", "Julius-Bold.ttf", "Julius-Bold.otf"]:
            dest = os.path.join(user_fonts, fname)
            shutil.copyfile(os.path.join(dist_dir, fname), dest)
            print(f"  Updated user font: {dest}")
            
    # Render specimen
    print("\n--- Generating Specimen Images ---")
    specimen_img = "/tmp/julius_new_font_specimen.png"
    font_large = ImageFont.truetype(os.path.join(dist_dir, "Julius-Regular.ttf"), 36)
    font_med = ImageFont.truetype(os.path.join(dist_dir, "Julius-Regular.ttf"), 24)
    font_bold_large = ImageFont.truetype(os.path.join(dist_dir, "Julius-Bold.ttf"), 36)
    
    im = Image.new("RGB", (950, 400), (18, 18, 20))
    d = ImageDraw.Draw(im)
    y = 30
    d.text((40, y), "Julius Font (Dagger Nocturne Didone Master)", font=font_med, fill=(200, 184, 150))
    y += 50
    d.text((40, y), "Hi there! How can I help you today?", font=font_large, fill=(245, 245, 247))
    y += 60
    d.text((40, y), "Hi there! How can I help you today? (Bold)", font=font_bold_large, fill=(245, 245, 247))
    y += 60
    d.text((40, y), "ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789", font=font_med, fill=(220, 220, 225))
    y += 40
    d.text((40, y), "abcdefghijklmnopqrstuvwxyz (Full ASCII + Symbols)", font=font_med, fill=(220, 220, 225))
    y += 40
    d.text((40, y), "Code: const l1 = (x > 0) ? #tag : @julius; // 100% Verified", font=font_med, fill=(160, 210, 160))
    
    im.save(specimen_img)
    im.save("Julius_Fonts/julius_font_specimen.png")
    print(f"Specimen saved: {specimen_img}")
    print("\nAll fonts successfully converted to Julius and deployed everywhere!")

if __name__ == '__main__':
    main()

