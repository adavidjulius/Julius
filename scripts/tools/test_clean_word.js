const opentype = require('../.agents/skills/draw-your-font/engine/node_modules/opentype.js');
const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const fs = require('fs');
const path = require('path');

const UPM = 1000;
const CAP = 700;
const XH = 490;
const ASC = 730;
const DESC = -210;
const OVS = 14;

// Metrics for Regular
const S = 82;        // Stem width
const T = 36;        // Thin bar width
const SE = 42;       // Serif extension
const ST = 22;       // Serif thickness at tip
const SB = 62;       // Serif bracket height

// Helper to draw a bracketed vertical stem with top and bottom serifs
// dirTop: 'both' | 'left' | 'right' | 'none'
// dirBot: 'both' | 'left' | 'right' | 'none'
function stemContour(x, yBot, yTop, w, seL_bot, seR_bot, seL_top, seR_top) {
  const p = [];
  // 1. Bottom-left
  if (seL_bot > 0) {
    p.push({ type: 'M', x: x - seL_bot, y: yBot });
    p.push({ type: 'L', x: x - seL_bot, y: yBot + ST });
    p.push({ type: 'C', x1: x - seL_bot * 0.4, y1: yBot + ST, x2: x, y2: yBot + ST + SB * 0.4, x: x, y: yBot + SB });
  } else {
    p.push({ type: 'M', x, y: yBot });
  }

  // 2. Up left face to top-left
  if (seL_top > 0) {
    p.push({ type: 'L', x, y: yTop - SB });
    p.push({ type: 'C', x1: x, y1: yTop - ST - SB * 0.4, x2: x - seL_top * 0.4, y2: yTop - ST, x: x - seL_top, y: yTop - ST });
    p.push({ type: 'L', x: x - seL_top, y: yTop });
  } else {
    p.push({ type: 'L', x, y: yTop });
  }

  // 3. Across top to top-right
  if (seR_top > 0) {
    p.push({ type: 'L', x: x + w + seR_top, y: yTop });
    p.push({ type: 'L', x: x + w + seR_top, y: yTop - ST });
    p.push({ type: 'C', x1: x + w + seR_top * 0.4, y1: yTop - ST, x2: x + w, y2: yTop - ST - SB * 0.4, x: x + w, y: yTop - SB });
  } else {
    p.push({ type: 'L', x: x + w, y: yTop });
  }

  // 4. Down right face to bottom-right
  if (seR_bot > 0) {
    p.push({ type: 'L', x: x + w, y: yBot + SB });
    p.push({ type: 'C', x1: x + w, y1: yBot + ST + SB * 0.4, x2: x + w + seR_bot * 0.4, y2: yBot + ST, x: x + w + seR_bot, y: yBot + ST });
    p.push({ type: 'L', x: x + w + seR_bot, y: yBot });
  } else {
    p.push({ type: 'L', x: x + w, y: yBot });
  }

  p.push({ type: 'Z' });
  return p;
}

function applyContour(path, cmds) {
  for (const c of cmds) {
    if (c.type === 'M') path.moveTo(c.x, c.y);
    else if (c.type === 'L') path.lineTo(c.x, c.y);
    else if (c.type === 'C') path.bezierCurveTo(c.x1, c.y1, c.x2, c.y2, c.x, c.y);
    else if (c.type === 'Z') path.close();
  }
}

// Draw 'J'
function makeJ() {
  const p = new opentype.Path();
  const x = 240;
  // Start at top-left serif
  p.moveTo(x - SE, CAP);
  p.lineTo(x + S + SE, CAP);
  p.lineTo(x + S + SE, CAP - ST);
  p.bezierCurveTo(x + S + SE * 0.4, CAP - ST, x + S, CAP - ST - SB * 0.4, x + S, CAP - SB);
  // Down stem
  p.lineTo(x + S, 120);
  // Curve down and left
  p.bezierCurveTo(x + S, 20, x + 20, -OVS, x - 90, -OVS);
  p.bezierCurveTo(x - 170, -OVS, x - 200, 25, x - 200, 80);
  p.bezierCurveTo(x - 200, 120, x - 175, 140, x - 145, 140);
  p.bezierCurveTo(x - 115, 140, x - 90, 115, x - 90, 85);
  p.bezierCurveTo(x - 90, 65, x - 105, 50, x - 125, 50);
  p.bezierCurveTo(x - 130, 50, x - 135, 52, x - 140, 55);
  // Inner curve back to stem
  p.bezierCurveTo(x - 140, 35, x - 120, 15, x - 85, 15);
  p.bezierCurveTo(x - 20, 15, x, 60, x, 140);
  // Up inner stem
  p.lineTo(x, CAP - SB);
  p.bezierCurveTo(x, CAP - ST - SB * 0.4, x - SE * 0.4, CAP - ST, x - SE, CAP - ST);
  p.close();
  return p;
}

// Draw lowercase 'u'
function makeU() {
  const p = new opentype.Path();
  const x1 = 65, x2 = 340;
  // Left stem top serif
  p.moveTo(x1 - SE * 0.7, XH);
  p.lineTo(x1 + S, XH);
  p.lineTo(x1 + S, 150);
  // Bottom curve connecting to right stem
  p.bezierCurveTo(x1 + S, 40, 180, -OVS, 260, -OVS);
  p.bezierCurveTo(310, -OVS, x2, 20, x2, 90);
  // Right stem up
  p.lineTo(x2, XH);
  p.lineTo(x2 + S + SE * 0.6, XH);
  p.lineTo(x2 + S + SE * 0.6, XH - ST);
  p.bezierCurveTo(x2 + S + SE * 0.2, XH - ST, x2 + S, XH - ST - SB * 0.3, x2 + S, XH - SB);
  // Down right stem to bottom-right foot serif
  p.lineTo(x2 + S, SB);
  p.bezierCurveTo(x2 + S, ST + SB * 0.3, x2 + S + SE * 0.2, ST, x2 + S + SE * 0.6, ST);
  p.lineTo(x2 + S + SE * 0.6, 0);
  p.lineTo(x2 - SE * 0.4, 0);
  p.lineTo(x2 - SE * 0.4, ST);
  p.bezierCurveTo(x2 - SE * 0.1, ST, x2, ST + SB * 0.2, x2, SB);
  p.lineTo(x2, 70);
  // Inner curve from right stem to left stem
  p.bezierCurveTo(x2, 25, 290, 15, 245, 15);
  p.bezierCurveTo(175, 15, x1, 55, x1, 160);
  // Up outer left stem
  p.lineTo(x1, XH - SB);
  p.bezierCurveTo(x1, XH - ST - SB * 0.3, x1 - SE * 0.3, XH - ST, x1 - SE * 0.7, XH - ST);
  p.close();
  return p;
}

// Draw lowercase 'l'
function makeL() {
  const p = new opentype.Path();
  const cmds = stemContour(75, 0, ASC, S, SE * 0.6, SE * 0.6, SE * 0.6, SE * 0.4);
  applyContour(p, cmds);
  return p;
}

// Draw lowercase 'i'
function makeI() {
  const p = new opentype.Path();
  const cmds = stemContour(75, 0, XH, S, SE * 0.6, SE * 0.6, SE * 0.6, SE * 0.3);
  applyContour(p, cmds);
  // Dot (softly rounded square/circle)
  const cx = 75 + S / 2, cy = XH + 115, r = S * 0.42;
  const k = r * 0.5523;
  p.moveTo(cx, cy + r);
  p.bezierCurveTo(cx + k, cy + r, cx + r, cy + k, cx + r, cy);
  p.bezierCurveTo(cx + r, cy - k, cx + k, cy - r, cx, cy - r);
  p.bezierCurveTo(cx - k, cy - r, cx - r, cy - k, cx - r, cy);
  p.bezierCurveTo(cx - r, cy + k, cx - k, cy + r, cx, cy + r);
  p.close();
  return p;
}

// Draw lowercase 's' (single beautiful continuous ribbon)
function makeS() {
  const p = new opentype.Path();
  const w = 420, cx = w / 2;
  // Outer contour clockwise
  p.moveTo(w - 60, XH - 85);
  p.bezierCurveTo(w - 60, XH + OVS, cx + 30, XH + OVS, cx, XH + OVS);
  p.bezierCurveTo(cx - 100, XH + OVS, 55, XH - 45, 55, XH - 125);
  p.bezierCurveTo(55, XH - 205, 125, XH * 0.53, cx, XH * 0.5);
  p.bezierCurveTo(cx + 95, XH * 0.47, w - 50, 160, w - 50, 95);
  p.bezierCurveTo(w - 50, 20, cx + 55, -OVS, cx, -OVS);
  p.bezierCurveTo(cx - 75, -OVS, 65, 10, 60, 85);
  p.lineTo(60 + S * 0.8, 98);
  p.bezierCurveTo(65 + S * 0.8, 18, cx - 25, 18, cx, 18);
  p.bezierCurveTo(cx + 65, 18, w - 50 - S * 0.8, 45, w - 50 - S * 0.8, 95);
  p.bezierCurveTo(w - 50 - S * 0.8, 145, cx + 80, XH * 0.47 + T * 0.4, cx, XH * 0.5 + T * 0.4);
  p.bezierCurveTo(cx - 85, XH * 0.53 + T * 0.4, 55 + S * 0.85, XH - 180, 55 + S * 0.85, XH - 125);
  p.bezierCurveTo(55 + S * 0.85, XH - 65, cx - 60, XH + OVS - T * 0.6, cx, XH + OVS - T * 0.6);
  p.bezierCurveTo(cx + 35, XH + OVS - T * 0.6, w - 60 - S * 0.7, XH - 25, w - 60 - S * 0.8, XH - 95);
  p.close();
  return p;
}

const font = new opentype.Font({
  familyName: 'TestJulius',
  styleName: 'Regular',
  unitsPerEm: 1000,
  ascender: 800,
  descender: -200,
  glyphs: [
    new opentype.Glyph({ name: '.notdef', unicode: 0, advanceWidth: 500, path: new opentype.Path() }),
    new opentype.Glyph({ name: 'space', unicode: 32, advanceWidth: 260, path: new opentype.Path() }),
    new opentype.Glyph({ name: 'J', unicode: 74, advanceWidth: 420, path: makeJ() }),
    new opentype.Glyph({ name: 'u', unicode: 117, advanceWidth: 500, path: makeU() }),
    new opentype.Glyph({ name: 'l', unicode: 108, advanceWidth: 270, path: makeL() }),
    new opentype.Glyph({ name: 'i', unicode: 105, advanceWidth: 270, path: makeI() }),
    new opentype.Glyph({ name: 's', unicode: 115, advanceWidth: 430, path: makeS() }),
  ]
});

font.kerningPairs = {}; const textPath = font.getPath('Julius', 50, 280, 220);
// Define constant svg set to `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="380" viewBox="0 0 900 380">
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="380" viewBox="0 0 900 380">
  <rect width="900" height="380" fill="#0b0f19" rx="16"/>
  <g fill="#f59e0b">${textPath.toSVG(2)}</g>
</svg>`;

// Execute statement: fs.writeFileSync(path.join(__dirname, 'test_julius.svg'), svg);
fs.writeFileSync(path.join(__dirname, 'test_julius.svg'), svg);
// Execute statement: sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_julius.png')).then(() => {
sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_julius.png')).then(() => {
  // Log diagnostic message to console: 'Rendered test_julius.png'
  console.log('Rendered test_julius.png');
});
