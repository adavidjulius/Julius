const path = require('path');
const fs = require('fs');

const engineModules = path.join(__dirname, '..', '.agents', 'skills', 'draw-your-font', 'engine', 'node_modules');
const opentype = require(path.join(engineModules, 'opentype.js'));

const UPM = 1000;
const CAP = 700;
const XH = 510;
const DESC = -210;
const ASC = 730;
const SQ_K = 0.68;

function addSquircleOuter(p, x, y, w, h, rx, ry) {
  const kx = rx * SQ_K;
  const ky = ry * SQ_K;
  p.moveTo(x + rx, y + h);
  p.lineTo(x + w - rx, y + h);
  p.bezierCurveTo(x + w - rx + kx, y + h, x + w, y + h - ry + ky, x + w, y + h - ry);
  p.lineTo(x + w, y + ry);
  p.bezierCurveTo(x + w, y + ry - ky, x + w - rx + kx, y, x + w - rx, y);
  p.lineTo(x + rx, y);
  p.bezierCurveTo(x + rx - kx, y, x, y + ry - ky, x, y + ry);
  p.lineTo(x, y + h - ry);
  p.bezierCurveTo(x, y + h - ry + ky, x + rx - kx, y + h, x + rx, y + h);
  p.close();
}

function addSquircleInner(p, x, y, w, h, rx, ry) {
  const kx = rx * SQ_K;
  const ky = ry * SQ_K;
  p.moveTo(x + rx, y + h);
  p.bezierCurveTo(x + rx - kx, y + h, x, y + h - ry + ky, x, y + h - ry);
  p.lineTo(x, y + ry);
  p.bezierCurveTo(x, y + ry - ky, x + rx - kx, y, x + rx, y);
  p.lineTo(x + w - rx, y);
  p.bezierCurveTo(x + w - rx + kx, y, x + w, y + ry - ky, x + w, y + ry);
  p.lineTo(x + w, y + h - ry);
  p.bezierCurveTo(x + w, y + h - ry + ky, x + w - rx + kx, y + h, x + w - rx, y + h);
  p.lineTo(x + rx, y + h);
  p.close();
}

function addRoundRect(p, x, y, w, h, r = 8) {
  if (r <= 0) {
    p.moveTo(x, y + h);
    p.lineTo(x + w, y + h);
    p.lineTo(x + w, y);
    p.lineTo(x, y);
    p.close();
    return;
  }
  const kr = r * 0.55228;
  p.moveTo(x + r, y + h);
  p.lineTo(x + w - r, y + h);
  p.bezierCurveTo(x + w - r + kr, y + h, x + w, y + h - r + kr, x + w, y + h - r);
  p.lineTo(x + w, y + r);
  p.bezierCurveTo(x + w, y + r - kr, x + w - r + kr, y, x + w - r, y);
  p.lineTo(x + r, y);
  p.bezierCurveTo(x + r - kr, y, x, y + r - kr, x, y + r);
  p.lineTo(x, y + h - r);
  p.bezierCurveTo(x, y + h - r + kr, x + r - kr, y + h, x + r, y + h);
  p.close();
}

/**
 * Solid, thick, beautiful S and s glyph builder
 */
function buildGlyphS(p, w, hw, r, topY, botY, width) {
  const left = 60;
  const right = width - 60;
  const midY = (topY + botY) / 2;
  const sw = w; // uniform spine stroke width
  
  // Outer contour clockwise
  p.moveTo(right - 20, topY - 100);
  p.bezierCurveTo(right - 40, topY + 8, width / 2 + 30, topY + 8, width / 2 - 20, topY - 30);
  p.bezierCurveTo(left + 20, topY - 90, left + 40, midY + 40, width / 2 - 10, midY + 10);
  p.bezierCurveTo(right - 20, midY - 20, right, botY + 120, right - 50, botY + 30);
  p.bezierCurveTo(right - 100, botY - 8, width / 2 - 40, botY - 8, left + 20, botY + 70);
  
  // Bottom terminal rounded cut
  p.lineTo(left + 20 + sw * 0.8, botY + 85);
  
  // Inner lower curve
  p.bezierCurveTo(left + 90, botY + hw, width / 2 - 30, botY + hw, right - 90, botY + 60);
  p.bezierCurveTo(right - sw - 20, botY + 100, right - sw - 40, midY - 50, width / 2, midY - 20);
  p.bezierCurveTo(left + 40, midY + 10, left + sw, topY - 80, width / 2 - 10, topY - hw - 10);
  p.bezierCurveTo(width / 2 + 50, topY - hw - 10, right - sw - 30, topY - 80, right - sw - 10, topY - 110);
  p.close();
}

/**
 * Clean 'b' glyph without overlapping counter hole
 */
function buildGlyphB(p, w, hw, r) {
  // Ascender stem from XH down to ASC
  addRoundRect(p, 70, XH - 10, w, ASC - (XH - 10), r);
  // Bowl + lower stem integrated:
  // Outer squircle starting at stem left
  addSquircleOuter(p, 70, -8, 480, XH + 16, 150, 140);
  // Inner counter hole
  addSquircleInner(p, 70 + w, -8 + hw, 480 - w - w * 0.9, XH + 16 - 2 * hw, 100, 90);
}

/**
 * Clean 'd' glyph without overlapping counter hole
 */
function buildGlyphD(p, w, hw, r) {
  const stemX = 540 - w;
  addRoundRect(p, stemX, XH - 10, w, ASC - (XH - 10), r);
  addSquircleOuter(p, 60, -8, 480, XH + 16, 150, 140);
  addSquircleInner(p, 60 + w * 0.9, -8 + hw, 480 - w - w * 0.9, XH + 16 - 2 * hw, 100, 90);
}

/**
 * Clean 'p' glyph
 */
function buildGlyphP(p, w, hw, r) {
  // Descender stem from baseline down to DESC
  addRoundRect(p, 70, DESC, w, -DESC + 10, r);
  // Bowl
  addSquircleOuter(p, 70, -8, 480, XH + 16, 150, 140);
  addSquircleInner(p, 70 + w, -8 + hw, 480 - w - w * 0.9, XH + 16 - 2 * hw, 100, 90);
}

/**
 * Clean 'q' glyph
 */
function buildGlyphQ(p, w, hw, r) {
  const stemX = 540 - w;
  addRoundRect(p, stemX, DESC, w, -DESC + 10, r);
  addSquircleOuter(p, 60, -8, 480, XH + 16, 150, 140);
  addSquircleInner(p, 60 + w * 0.9, -8 + hw, 480 - w - w * 0.9, XH + 16 - 2 * hw, 100, 90);
}

console.log('Test functions defined successfully.');
