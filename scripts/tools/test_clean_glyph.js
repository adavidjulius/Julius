const opentype = require('../.agents/skills/draw-your-font/engine/node_modules/opentype.js');
const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const fs = require('fs');
const path = require('path');

// Let's create an 'H' as a single unified continuous contour (CW).
// An 'H' has:
// Left stem with top serif and bottom serif
// Right stem with top serif and bottom serif
// Crossbar connecting them
// If we trace the entire outer perimeter as ONE continuous path, there are NO overlaps!

function createCleanH(CAP = 700, S = 90, T = 40, SE = 45, ST = 22, SB = 65, W = 700) {
  const p = new opentype.Path();
  const x1 = 80;
  const x2 = W - 80 - S;
  const cy = CAP / 2;
  const barY1 = cy - T / 2;
  const barY2 = cy + T / 2;

  // Start at bottom-left serif tip
  p.moveTo(x1 - SE, 0);
  p.lineTo(x1 - SE, ST);
  p.bezierCurveTo(x1 - SE * 0.4, ST, x1, ST + SB * 0.4, x1, SB);
  // Up left stem to top-left bracket
  p.lineTo(x1, CAP - SB);
  p.bezierCurveTo(x1, CAP - ST - SB * 0.4, x1 - SE * 0.4, CAP - ST, x1 - SE, CAP - ST);
  p.lineTo(x1 - SE, CAP);
  // Across top-left serif to inner top-left
  p.lineTo(x1 + S + SE, CAP);
  p.lineTo(x1 + S + SE, CAP - ST);
  p.bezierCurveTo(x1 + S + SE * 0.4, CAP - ST, x1 + S, CAP - ST - SB * 0.4, x1 + S, CAP - SB);
  // Down to crossbar top
  p.lineTo(x1 + S, barY2);
  // Across crossbar to right stem
  p.lineTo(x2, barY2);
  // Up right stem to top-left of right stem
  p.lineTo(x2, CAP - SB);
  p.bezierCurveTo(x2, CAP - ST - SB * 0.4, x2 - SE * 0.4, CAP - ST, x2 - SE, CAP - ST);
  p.lineTo(x2 - SE, CAP);
  p.lineTo(x2 + S + SE, CAP);
  p.lineTo(x2 + S + SE, CAP - ST);
  p.bezierCurveTo(x2 + S + SE * 0.4, CAP - ST, x2 + S, CAP - ST - SB * 0.4, x2 + S, CAP - SB);
  // Down right outer face to bottom-right serif
  p.lineTo(x2 + S, SB);
  p.bezierCurveTo(x2 + S, ST + SB * 0.4, x2 + S + SE * 0.4, ST, x2 + S + SE, ST);
  p.lineTo(x2 + S + SE, 0);
  // Across bottom of right stem
  p.lineTo(x2 - SE, 0);
  p.lineTo(x2 - SE, ST);
  p.bezierCurveTo(x2 - SE * 0.4, ST, x2, ST + SB * 0.4, x2, SB);
  // Up to bottom of crossbar
  p.lineTo(x2, barY1);
  // Across crossbar to left stem
  p.lineTo(x1 + S, barY1);
  // Down to inner bottom-left serif
  p.lineTo(x1 + S, SB);
  p.bezierCurveTo(x1 + S, ST + SB * 0.4, x1 + S + SE * 0.4, ST, x1 + S + SE, ST);
  p.lineTo(x1 + S + SE, 0);
  // Back to start
  p.close();

  return p;
}

const font = new opentype.Font({
  familyName: 'TestClean',
  styleName: 'Regular',
  unitsPerEm: 1000,
  ascender: 800,
  descender: -200,
  glyphs: [
    new opentype.Glyph({ name: '.notdef', unicode: 0, advanceWidth: 500, path: new opentype.Path() }),
    new opentype.Glyph({ name: 'H', unicode: 72, advanceWidth: 700, path: createCleanH() })
  ]
});

const svg = font.getPath('H', 50, 400, 400).toSVG(2);
// Define constant fullSvg set to `<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500" viewBox="0 0 500 500">
const fullSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500" viewBox="0 0 500 500">
  <rect width="500" height="500" fill="#161b22"/>
  <g fill="#f59e0b">${svg}</g>
</svg>`;

// Execute statement: fs.writeFileSync(path.join(__dirname, 'test_clean_H.svg'), fullSvg);
fs.writeFileSync(path.join(__dirname, 'test_clean_H.svg'), fullSvg);
// Execute statement: sharp(Buffer.from(fullSvg)).png().toFile(path.join(__dirname, 'test_clean_H.png')).then(() => {
sharp(Buffer.from(fullSvg)).png().toFile(path.join(__dirname, 'test_clean_H.png')).then(() => {
  // Log diagnostic message to console: 'Generated test_clean_H.png'
  console.log('Generated test_clean_H.png');
});
