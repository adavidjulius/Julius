const opentype = require('../.agents/skills/draw-your-font/engine/node_modules/opentype.js');
const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const fs = require('fs');
const path = require('path');

const CAP = 680, XH = 490;

function makeAmpersand(isBold = false) {
  const p = new opentype.Path();
  const t = isBold ? 50 : 36;
  const s = isBold ? 100 : 75;

  const bcx = 260, bcy = 160, brx = 180, bry = 170;
  const tcx = 290, tcy = CAP - 170, trx = 125, try_ = 135;

  // Outer silhouette (CCW in TrueType coords)
  p.moveTo(540, -10);
  p.lineTo(440, bcy - 70);
  p.bezierCurveTo(380, bcy - bry, bcx + brx * 0.55, bcy - bry, bcx, bcy - bry);
  p.bezierCurveTo(bcx - brx * 0.55, bcy - bry, bcx - brx, bcy - bry, bcx - brx, bcy);
  p.bezierCurveTo(bcx - brx, 180, 120, 200, 220, 230);
  p.bezierCurveTo(tcx - 40, tcy - try_, tcx - trx, tcy - 60, tcx - trx, tcy);
  p.bezierCurveTo(tcx - trx, tcy + try_, tcx - trx * 0.55, tcy + try_, tcx, tcy + try_);
  p.bezierCurveTo(tcx + trx * 0.55, tcy + try_, tcx + trx, tcy + try_, tcx + trx, tcy);
  p.bezierCurveTo(tcx + trx, tcy - 50, 430, tcy - try_, 410, 160);
  p.lineTo(540 + t, -10);
  p.close();

  // Top counter (CW)
  const itrx = trx - s * 0.65, itry = try_ - t * 0.7;
  p.moveTo(tcx, tcy + itry);
  p.bezierCurveTo(tcx + itrx * 0.55, tcy + itry, tcx + itrx, tcy + itry * 0.55, tcx + itrx, tcy);
  p.bezierCurveTo(tcx + itrx, tcy - itry * 0.55, tcx + itrx * 0.55, tcy - itry, tcx, tcy - itry);
  p.bezierCurveTo(tcx - itrx * 0.55, tcy - itry, tcx - itrx, tcy - itry * 0.55, tcx - itrx, tcy);
  p.bezierCurveTo(tcx - itrx, tcy + itry * 0.55, tcx - itrx * 0.55, tcy + itry, tcx, tcy + itry);
  p.close();

  // Bottom counter (CW)
  const ibrx = brx - s * 0.75, ibry = bry - t * 0.75;
  p.moveTo(bcx, bcy + ibry);
  p.bezierCurveTo(bcx + ibrx * 0.55, bcy + ibry, bcx + ibrx, bcy + ibry * 0.55, bcx + ibrx, bcy);
  p.bezierCurveTo(bcx + ibrx, bcy - ibry * 0.55, bcx + ibrx * 0.55, bcy - ibry, bcx, bcy - ibry);
  p.bezierCurveTo(bcx - ibrx * 0.55, bcy - ibry, bcx - ibrx, bcy - ibry * 0.55, bcx - ibrx, bcy);
  p.bezierCurveTo(bcx - ibrx, bcy + ibry * 0.55, bcx - ibrx * 0.55, bcy + ibry, bcx, bcy + ibry);
  p.close();

  return p;
}

const rawFont = new opentype.Font({
  familyName: 'TestAmp',
  styleName: 'Regular',
  unitsPerEm: 1024,
  ascender: 743,
  descender: -266,
  glyphs: [
    new opentype.Glyph({ name: '.notdef', unicode: 0, advanceWidth: 500, path: new opentype.Path() }),
    new opentype.Glyph({ name: 'ampersand', unicode: 38, advanceWidth: 620, path: makeAmpersand() }),
  ]
});

const buf = Buffer.from(rawFont.toArrayBuffer());
const font = opentype.parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));

// Define constant svg set to `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
  <rect width="300" height="300" fill="#161b22"/>
  <g fill="#f59e0b">
    ${font.getPath('&', 40, 220, 180).toSVG(2)}
  </g>
</svg>`;

// Execute statement: fs.writeFileSync(path.join(__dirname, 'test_amp_only.svg'), svg);
fs.writeFileSync(path.join(__dirname, 'test_amp_only.svg'), svg);
// Execute statement: sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_amp_only.png')).then(() => {
sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_amp_only.png')).then(() => {
  // Log diagnostic message to console: 'Saved test_amp_only.png'
  console.log('Saved test_amp_only.png');
});
