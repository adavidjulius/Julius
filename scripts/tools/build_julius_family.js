const fs = require('fs');
const path = require('path');

const engineModules = path.join(__dirname, '..', '.agents', 'skills', 'draw-your-font', 'engine', 'node_modules');
const opentype = require(path.join(engineModules, 'opentype.js'));
const ttf2woff = require(path.join(engineModules, 'ttf2woff'));
const wawoff2  = require(path.join(engineModules, 'wawoff2'));
const sharp    = require(path.join(engineModules, 'sharp'));

const masterFont = opentype.loadSync(path.join(__dirname, 'reel_frame.ttf'));

const UPM = 1024;
const ASC = 743;
const DESC = -266;
const CAP = 680;
const XH = 490;

// Missing symbols constructor
function createMissingGlyphs(isBold) {
  const S = isBold ? 115 : 80;
  const T = isBold ? 55 : 38;
  const glyphs = {};

  function addG(name, uc, adv, fn) {
    const p = new opentype.Path();
    fn(p);
    glyphs[uc] = new opentype.Glyph({
      // Import or destructure parameter name
      name,
      unicode: uc,
      advanceWidth: Math.round(adv),
      path: p
    });
  }

  // Helper rect (CCW for TrueType outer outline)
  function rect(p, x, y, w, h) {
    p.moveTo(x, y);
    p.lineTo(x, y + h);
    p.lineTo(x + w, y + h);
    p.lineTo(x + w, y);
    p.close();
  }

  // / (47)
  addG('slash', 47, 440, p => {
    p.moveTo(60, -80);
    p.lineTo(360 - T, CAP + 40);
    p.lineTo(360, CAP + 40);
    p.lineTo(60 + T, -80);
    p.close();
  });

  // \ (92)
  addG('backslash', 92, 440, p => {
    p.moveTo(60, CAP + 40);
    p.lineTo(60 + T, CAP + 40);
    p.lineTo(360, -80);
    p.lineTo(360 - T, -80);
    p.close();
  });

  // | (124)
  addG('bar', 124, 300, p => {
    rect(p, 150 - T / 2, -180, T, CAP + 260);
  });

  // + (43)
  addG('plus', 43, 560, p => {
    const cy = XH * 0.55, cx = 280, arm = 170;
    rect(p, cx - T / 2, cy - arm, T, arm * 2);
    rect(p, cx - arm, cy - T / 2, arm * 2, T);
  });

  // = (61)
  addG('equal', 61, 560, p => {
    const cx = 280, w = 360;
    rect(p, cx - w / 2, XH * 0.55 + 65, w, T);
    rect(p, cx - w / 2, XH * 0.55 - 65 - T, w, T);
  });

  // < (60)
  addG('less', 60, 520, p => {
    const cy = XH * 0.55;
    p.moveTo(420, cy + 180);
    p.lineTo(100, cy);
    p.lineTo(420, cy - 180);
    p.lineTo(420, cy - 180 + T * 1.2);
    p.lineTo(150, cy);
    p.lineTo(420, cy + 180 - T * 1.2);
    p.close();
  });

  // > (62)
  addG('greater', 62, 520, p => {
    const cy = XH * 0.55;
    p.moveTo(100, cy + 180);
    p.lineTo(100, cy + 180 - T * 1.2);
    p.lineTo(370, cy);
    p.lineTo(100, cy - 180 + T * 1.2);
    p.lineTo(100, cy - 180);
    p.lineTo(420, cy);
    p.close();
  });

  // _ (95)
  addG('underscore', 95, 500, p => {
    rect(p, 20, -140, 460, T);
  });

  // ^ (94)
  addG('asciicircum', 94, 500, p => {
    p.moveTo(250, CAP + 50);
    p.lineTo(90, CAP - 160);
    p.lineTo(90 + T * 1.1, CAP - 160);
    p.lineTo(250, CAP + 50 - T * 1.5);
    p.lineTo(410 - T * 1.1, CAP - 160);
    p.lineTo(410, CAP - 160);
    p.close();
  });

  // ~ (126)
  addG('asciitilde', 126, 540, p => {
    const cy = XH * 0.55;
    p.moveTo(60, cy);
    p.bezierCurveTo(110, cy + 100, 200, cy + 100, 270, cy);
    p.bezierCurveTo(340, cy - 100, 430, cy - 100, 480, cy);
    p.lineTo(480, cy + T);
    p.bezierCurveTo(430, cy - 100 + T, 340, cy - 100 + T, 270, cy + T);
    p.bezierCurveTo(200, cy + 100 + T, 110, cy + 100 + T, 60, cy + T);
    p.close();
  });

  // ` (96)
  addG('grave', 96, 300, p => {
    // Execute statement: p.moveTo(80, CAP + 30);
    p.moveTo(80, CAP + 30);
    // Execute statement: p.lineTo(160, CAP - 90);
    p.lineTo(160, CAP - 90);
    // Execute statement: p.lineTo(160 + T, CAP - 90);
    p.lineTo(160 + T, CAP - 90);
    // Execute statement: p.lineTo(80 + T, CAP + 30);
    p.lineTo(80 + T, CAP + 30);
    // Execute statement: p.close();
    p.close();
  });

  // { (123)
  addG('braceleft', 123, 360, p => {
    // Define constant cy set to XH * 0.55;
    const cy = XH * 0.55;
    // Execute statement: p.moveTo(270, CAP + 40);
    p.moveTo(270, CAP + 40);
    // Execute statement: p.bezierCurveTo(190, CAP + 40, 180, cy + 80, 180, cy + 40);
    p.bezierCurveTo(190, CAP + 40, 180, cy + 80, 180, cy + 40);
    // Execute statement: p.lineTo(120, cy);
    p.lineTo(120, cy);
    // Execute statement: p.lineTo(180, cy - 40);
    p.lineTo(180, cy - 40);
    // Execute statement: p.bezierCurveTo(180, cy - 80, 190, -100, 270, -100);
    p.bezierCurveTo(180, cy - 80, 190, -100, 270, -100);
    // Execute statement: p.lineTo(270, -100 + T);
    p.lineTo(270, -100 + T);
    // Execute statement: p.bezierCurveTo(210, -100 + T, 210, cy - 60, 210, cy - 30);
    p.bezierCurveTo(210, -100 + T, 210, cy - 60, 210, cy - 30);
    // Execute statement: p.lineTo(160, cy);
    p.lineTo(160, cy);
    // Execute statement: p.lineTo(210, cy + 30);
    p.lineTo(210, cy + 30);
    // Execute statement: p.bezierCurveTo(210, cy + 60, 210, CAP + 40 - T, 270, CAP + 40 - T);
    p.bezierCurveTo(210, cy + 60, 210, CAP + 40 - T, 270, CAP + 40 - T);
    // Execute statement: p.close();
    p.close();
  });

  // } (125)
  addG('braceright', 125, 360, p => {
    // Define constant cy set to XH * 0.55;
    const cy = XH * 0.55;
    // Execute statement: p.moveTo(90, CAP + 40);
    p.moveTo(90, CAP + 40);
    // Execute statement: p.bezierCurveTo(170, CAP + 40, 180, cy + 80, 180, cy + 40);
    p.bezierCurveTo(170, CAP + 40, 180, cy + 80, 180, cy + 40);
    // Execute statement: p.lineTo(240, cy);
    p.lineTo(240, cy);
    // Execute statement: p.lineTo(180, cy - 40);
    p.lineTo(180, cy - 40);
    // Execute statement: p.bezierCurveTo(180, cy - 80, 170, -100, 90, -100);
    p.bezierCurveTo(180, cy - 80, 170, -100, 90, -100);
    // Execute statement: p.lineTo(90, -100 + T);
    p.lineTo(90, -100 + T);
    // Execute statement: p.bezierCurveTo(150, -100 + T, 150, cy - 60, 150, cy - 30);
    p.bezierCurveTo(150, -100 + T, 150, cy - 60, 150, cy - 30);
    // Execute statement: p.lineTo(200, cy);
    p.lineTo(200, cy);
    // Execute statement: p.lineTo(150, cy + 30);
    p.lineTo(150, cy + 30);
    // Execute statement: p.bezierCurveTo(150, cy + 60, 150, CAP + 40 - T, 90, CAP + 40 - T);
    p.bezierCurveTo(150, cy + 60, 150, CAP + 40 - T, 90, CAP + 40 - T);
    // Execute statement: p.close();
    p.close();
  });

  // # (35)
  addG('numbersign', 35, 600, p => {
    // Execute statement: rect(p, 175, 40, T, CAP - 80);
    rect(p, 175, 40, T, CAP - 80);
    // Execute statement: rect(p, 365, 40, T, CAP - 80);
    rect(p, 365, 40, T, CAP - 80);
    // Execute statement: rect(p, 60, CAP * 0.65 - T / 2, 480, T);
    rect(p, 60, CAP * 0.65 - T / 2, 480, T);
    // Execute statement: rect(p, 60, CAP * 0.35 - T / 2, 480, T);
    rect(p, 60, CAP * 0.35 - T / 2, 480, T);
  });

  // $ (36)
  addG('dollar', 36, 580, p => {
    // Vertical spine
    rect(p, 290 - T * 0.4, -60, T * 0.8, CAP + 120);
    // S-curve
    const cx = 290;
    // Execute statement: p.moveTo(460, CAP - 75);
    p.moveTo(460, CAP - 75);
    // Execute statement: p.bezierCurveTo(460, CAP + 14, cx + 30, CAP + 14, cx, CAP + 14);
    p.bezierCurveTo(460, CAP + 14, cx + 30, CAP + 14, cx, CAP + 14);
    // Execute statement: p.bezierCurveTo(cx - 100, CAP + 14, 85, CAP - 45, 85, CAP - 130);
    p.bezierCurveTo(cx - 100, CAP + 14, 85, CAP - 45, 85, CAP - 130);
    // Execute statement: p.bezierCurveTo(85, CAP - 225, 175, CAP * 0.52 + 20, cx, CAP * 0.52);
    p.bezierCurveTo(85, CAP - 225, 175, CAP * 0.52 + 20, cx, CAP * 0.52);
    // Execute statement: p.bezierCurveTo(cx + 115, CAP * 0.52 - 20, 470, 180, 470, 105);
    p.bezierCurveTo(cx + 115, CAP * 0.52 - 20, 470, 180, 470, 105);
    // Execute statement: p.bezierCurveTo(470, 15, cx + 75, -14, cx, -14);
    p.bezierCurveTo(470, 15, cx + 75, -14, cx, -14);
    // Execute statement: p.bezierCurveTo(cx - 55, -14, 95, 0, 95, 75);
    p.bezierCurveTo(cx - 55, -14, 95, 0, 95, 75);
    // Execute statement: p.lineTo(95 + S * 0.75, 85);
    p.lineTo(95 + S * 0.75, 85);
    // Execute statement: p.bezierCurveTo(95 + S * 0.8, 14, cx - 25, 14, cx, 14);
    p.bezierCurveTo(95 + S * 0.8, 14, cx - 25, 14, cx, 14);
    // Execute statement: p.bezierCurveTo(cx + 55, 14, 470 - S, 25, 470 - S, 105);
    p.bezierCurveTo(cx + 55, 14, 470 - S, 25, 470 - S, 105);
    // Execute statement: p.bezierCurveTo(470 - S, 165, cx + 95, CAP * 0.52 - 20 + T * 0.5, cx, CAP * 0.52 + T * 0.5);
    p.bezierCurveTo(470 - S, 165, cx + 95, CAP * 0.52 - 20 + T * 0.5, cx, CAP * 0.52 + T * 0.5);
    // Execute statement: p.bezierCurveTo(cx - 95, CAP * 0.52 + 20 + T * 0.5, 85 + S, CAP - 205, 85 + S, CAP - 130);
    p.bezierCurveTo(cx - 95, CAP * 0.52 + 20 + T * 0.5, 85 + S, CAP - 205, 85 + S, CAP - 130);
    // Execute statement: p.bezierCurveTo(85 + S, CAP - 50, cx - 55, CAP + 14 - T * 0.7, cx, CAP + 14 - T * 0.7);
    p.bezierCurveTo(85 + S, CAP - 50, cx - 55, CAP + 14 - T * 0.7, cx, CAP + 14 - T * 0.7);
    // Execute statement: p.bezierCurveTo(cx + 25, CAP + 14 - T * 0.7, 460 - S * 0.7, CAP - 10, 460 - S * 0.8, CAP - 85);
    p.bezierCurveTo(cx + 25, CAP + 14 - T * 0.7, 460 - S * 0.7, CAP - 10, 460 - S * 0.8, CAP - 85);
    // Execute statement: p.close();
    p.close();
  });

  // % (37)
  addG('percent', 37, 680, p => {
    // Slash
    p.moveTo(120, -30);
    // Execute statement: p.lineTo(540 - T, CAP + 30);
    p.lineTo(540 - T, CAP + 30);
    // Execute statement: p.lineTo(540, CAP + 30);
    p.lineTo(540, CAP + 30);
    // Execute statement: p.lineTo(120 + T, -30);
    p.lineTo(120 + T, -30);
    // Execute statement: p.close();
    p.close();
    // Top circle
    const r1 = 80, c1x = 210, c1y = CAP - 140;
    // Define constant k1 set to r1 * 0.5523;
    const k1 = r1 * 0.5523;
    // Execute statement: p.moveTo(c1x, c1y + r1);
    p.moveTo(c1x, c1y + r1);
    // Execute statement: p.bezierCurveTo(c1x + k1, c1y + r1, c1x + r1, c1y + k1, c1x + r1, c1y);
    p.bezierCurveTo(c1x + k1, c1y + r1, c1x + r1, c1y + k1, c1x + r1, c1y);
    // Execute statement: p.bezierCurveTo(c1x + r1, c1y - k1, c1x + k1, c1y - r1, c1x, c1y - r1);
    p.bezierCurveTo(c1x + r1, c1y - k1, c1x + k1, c1y - r1, c1x, c1y - r1);
    // Execute statement: p.bezierCurveTo(c1x - k1, c1y - r1, c1x - r1, c1y - k1, c1x - r1, c1y);
    p.bezierCurveTo(c1x - k1, c1y - r1, c1x - r1, c1y - k1, c1x - r1, c1y);
    // Execute statement: p.bezierCurveTo(c1x - r1, c1y + k1, c1x - k1, c1y + r1, c1x, c1y + r1);
    p.bezierCurveTo(c1x - r1, c1y + k1, c1x - k1, c1y + r1, c1x, c1y + r1);
    // Execute statement: p.close();
    p.close();
    // Hole
    const ir1 = r1 - T * 0.8, ik1 = ir1 * 0.5523;
    // Execute statement: p.moveTo(c1x, c1y + ir1);
    p.moveTo(c1x, c1y + ir1);
    // Execute statement: p.bezierCurveTo(c1x - ik1, c1y + ir1, c1x - ir1, c1y + ik1, c1x - ir1, c1y);
    p.bezierCurveTo(c1x - ik1, c1y + ir1, c1x - ir1, c1y + ik1, c1x - ir1, c1y);
    // Execute statement: p.bezierCurveTo(c1x - ir1, c1y - ik1, c1x - ik1, c1y - ir1, c1x, c1y - ir1);
    p.bezierCurveTo(c1x - ir1, c1y - ik1, c1x - ik1, c1y - ir1, c1x, c1y - ir1);
    // Execute statement: p.bezierCurveTo(c1x + ik1, c1y - ir1, c1x + ir1, c1y - ik1, c1x + ir1, c1y);
    p.bezierCurveTo(c1x + ik1, c1y - ir1, c1x + ir1, c1y - ik1, c1x + ir1, c1y);
    // Execute statement: p.bezierCurveTo(c1x + ir1, c1y + ik1, c1x + ik1, c1y + ir1, c1x, c1y + ir1);
    p.bezierCurveTo(c1x + ir1, c1y + ik1, c1x + ik1, c1y + ir1, c1x, c1y + ir1);
    // Execute statement: p.close();
    p.close();
    // Bottom circle
    const r2 = 80, c2x = 470, c2y = 140;
    // Define constant k2 set to r2 * 0.5523;
    const k2 = r2 * 0.5523;
    // Execute statement: p.moveTo(c2x, c2y + r2);
    p.moveTo(c2x, c2y + r2);
    // Execute statement: p.bezierCurveTo(c2x + k2, c2y + r2, c2x + r2, c2y + k2, c2x + r2, c2y);
    p.bezierCurveTo(c2x + k2, c2y + r2, c2x + r2, c2y + k2, c2x + r2, c2y);
    // Execute statement: p.bezierCurveTo(c2x + r2, c2y - k2, c2x + k2, c2y - r2, c2x, c2y - r2);
    p.bezierCurveTo(c2x + r2, c2y - k2, c2x + k2, c2y - r2, c2x, c2y - r2);
    // Execute statement: p.bezierCurveTo(c2x - k2, c2y - r2, c2x - r2, c2y - k2, c2x - r2, c2y);
    p.bezierCurveTo(c2x - k2, c2y - r2, c2x - r2, c2y - k2, c2x - r2, c2y);
    // Execute statement: p.bezierCurveTo(c2x - r2, c2y + k2, c2x - k2, c2y + r2, c2x, c2y + r2);
    p.bezierCurveTo(c2x - r2, c2y + k2, c2x - k2, c2y + r2, c2x, c2y + r2);
    // Execute statement: p.close();
    p.close();
    // Define constant ir2 set to r2 - T * 0.8, ik2 = ir2 * 0.5523;
    const ir2 = r2 - T * 0.8, ik2 = ir2 * 0.5523;
    // Execute statement: p.moveTo(c2x, c2y + ir2);
    p.moveTo(c2x, c2y + ir2);
    // Execute statement: p.bezierCurveTo(c2x - ik2, c2y + ir2, c2x - ir2, c2y + ik2, c2x - ir2, c2y);
    p.bezierCurveTo(c2x - ik2, c2y + ir2, c2x - ir2, c2y + ik2, c2x - ir2, c2y);
    // Execute statement: p.bezierCurveTo(c2x - ir2, c2y - ik2, c2x - ik2, c2y - ir2, c2x, c2y - ir2);
    p.bezierCurveTo(c2x - ir2, c2y - ik2, c2x - ik2, c2y - ir2, c2x, c2y - ir2);
    // Execute statement: p.bezierCurveTo(c2x + ik2, c2y - ir2, c2x + ir2, c2y - ik2, c2x + ir2, c2y);
    p.bezierCurveTo(c2x + ik2, c2y - ir2, c2x + ir2, c2y - ik2, c2x + ir2, c2y);
    // Execute statement: p.bezierCurveTo(c2x + ir2, c2y + ik2, c2x + ik2, c2y + ir2, c2x, c2y + ir2);
    p.bezierCurveTo(c2x + ir2, c2y + ik2, c2x + ik2, c2y + ir2, c2x, c2y + ir2);
    // Execute statement: p.close();
    p.close();
  });

  // & (38)
  addG('ampersand', 38, 640, p => {
    // Execute statement: p.moveTo(560, 40);
    p.moveTo(560, 40);
    // Execute statement: p.lineTo(560, 40 + T);
    p.lineTo(560, 40 + T);
    // Execute statement: p.bezierCurveTo(460, 40 + T, 380, 100, 340, 160);
    p.bezierCurveTo(460, 40 + T, 380, 100, 340, 160);
    // Execute statement: p.bezierCurveTo(390, 240, 420, 360, 420, 450);
    p.bezierCurveTo(390, 240, 420, 360, 420, 450);
    // Execute statement: p.bezierCurveTo(420, CAP + 14, 280, CAP + 14, 230, CAP - 60);
    p.bezierCurveTo(420, CAP + 14, 280, CAP + 14, 230, CAP - 60);
    // Execute statement: p.bezierCurveTo(180, CAP - 150, 180, 360, 240, 280);
    p.bezierCurveTo(180, CAP - 150, 180, 360, 240, 280);
    // Execute statement: p.bezierCurveTo(150, 220, 90, 140, 90, 50);
    p.bezierCurveTo(150, 220, 90, 140, 90, 50);
    // Execute statement: p.bezierCurveTo(90, -14, 200, -14, 300, 40);
    p.bezierCurveTo(90, -14, 200, -14, 300, 40);
    // Execute statement: p.lineTo(440, -14);
    p.lineTo(440, -14);
    // Execute statement: p.lineTo(440 + T, -14);
    p.lineTo(440 + T, -14);
    // Execute statement: p.lineTo(315, 65);
    p.lineTo(315, 65);
    // Execute statement: p.bezierCurveTo(240, 15, 150, 15, 150, 55);
    p.bezierCurveTo(240, 15, 150, 15, 150, 55);
    // Execute statement: p.bezierCurveTo(150, 110, 200, 180, 270, 230);
    p.bezierCurveTo(150, 110, 200, 180, 270, 230);
    // Execute statement: p.bezierCurveTo(320, 160, 430, 40, 560, 40);
    p.bezierCurveTo(320, 160, 430, 40, 560, 40);
    // Execute statement: p.close();
    p.close();
  });

  // * (42)
  addG('asterisk', 42, 420, p => {
    // Define constant cx set to 210, cy = CAP - 110, len = 110;
    const cx = 210, cy = CAP - 110, len = 110;
    // Execute statement: for (let i = 0; i < 5; i++) {
    for (let i = 0; i < 5; i++) {
      // Define constant a set to (i * 2 * Math.PI) / 5 - Math.PI / 2;
      const a = (i * 2 * Math.PI) / 5 - Math.PI / 2;
      // Define constant dx set to Math.cos(a), dy = Math.sin(a);
      const dx = Math.cos(a), dy = Math.sin(a);
      // Define constant nx set to -dy, ny = dx;
      const nx = -dy, ny = dx;
      // Execute statement: p.moveTo(cx + dx * 20 - nx * (T / 2), cy + dy * 20 - ny * (T / 2));
      p.moveTo(cx + dx * 20 - nx * (T / 2), cy + dy * 20 - ny * (T / 2));
      // Execute statement: p.lineTo(cx + dx * len - nx * (T / 2), cy + dy * len - ny * (T / 2));
      p.lineTo(cx + dx * len - nx * (T / 2), cy + dy * len - ny * (T / 2));
      // Execute statement: p.lineTo(cx + dx * len + nx * (T / 2), cy + dy * len + ny * (T / 2));
      p.lineTo(cx + dx * len + nx * (T / 2), cy + dy * len + ny * (T / 2));
      // Execute statement: p.lineTo(cx + dx * 20 + nx * (T / 2), cy + dy * 20 + ny * (T / 2));
      p.lineTo(cx + dx * 20 + nx * (T / 2), cy + dy * 20 + ny * (T / 2));
      // Execute statement: p.close();
      p.close();
    }
  });

  // @ (64)
  addG('at', 64, 780, p => {
    // Define constant cx set to 390, cy = XH * 0.55;
    const cx = 390, cy = XH * 0.55;
    // Define constant rx set to 330, ry = 360;
    const rx = 330, ry = 360;
    // Define constant kx set to rx * 0.5523, ky = ry * 0.5523;
    const kx = rx * 0.5523, ky = ry * 0.5523;
    // Outer loop
    p.moveTo(cx, cy + ry);
    // Execute statement: p.bezierCurveTo(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy);
    p.bezierCurveTo(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy);
    // Execute statement: p.bezierCurveTo(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry);
    p.bezierCurveTo(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry);
    // Execute statement: p.bezierCurveTo(cx + kx * 0.8, cy - ry, cx + rx * 0.85, cy - 100, cx + rx * 0.85, cy);
    p.bezierCurveTo(cx + kx * 0.8, cy - ry, cx + rx * 0.85, cy - 100, cx + rx * 0.85, cy);
    // Execute statement: p.lineTo(cx + rx * 0.85 - T, cy);
    p.lineTo(cx + rx * 0.85 - T, cy);
    // Execute statement: p.bezierCurveTo(cx + rx * 0.85 - T, cy - 80, cx + kx * 0.7, cy - ry + T, cx, cy - ry + T);
    p.bezierCurveTo(cx + rx * 0.85 - T, cy - 80, cx + kx * 0.7, cy - ry + T, cx, cy - ry + T);
    // Execute statement: p.bezierCurveTo(cx - kx * 0.85, cy - ry + T, cx - rx + T, cy - ky * 0.85, cx - rx + T, cy);
    p.bezierCurveTo(cx - kx * 0.85, cy - ry + T, cx - rx + T, cy - ky * 0.85, cx - rx + T, cy);
    // Execute statement: p.bezierCurveTo(cx - rx + T, cy + ky * 0.85, cx - kx * 0.85, cy + ry - T, cx, cy + ry - T);
    p.bezierCurveTo(cx - rx + T, cy + ky * 0.85, cx - kx * 0.85, cy + ry - T, cx, cy + ry - T);
    // Execute statement: p.close();
    p.close();
    // Inner 'a'
    const irx = 130, iry = 140;
    // Define constant ikx set to irx * 0.5523, iky = iry * 0.5523;
    const ikx = irx * 0.5523, iky = iry * 0.5523;
    // Execute statement: p.moveTo(cx, cy + iry);
    p.moveTo(cx, cy + iry);
    // Execute statement: p.bezierCurveTo(cx + ikx, cy + iry, cx + irx, cy + iky, cx + irx, cy);
    p.bezierCurveTo(cx + ikx, cy + iry, cx + irx, cy + iky, cx + irx, cy);
    // Execute statement: p.bezierCurveTo(cx + irx, cy - iky, cx + ikx, cy - iry, cx, cy - iry);
    p.bezierCurveTo(cx + irx, cy - iky, cx + ikx, cy - iry, cx, cy - iry);
    // Execute statement: p.bezierCurveTo(cx - ikx, cy - iry, cx - irx, cy - iky, cx - irx, cy);
    p.bezierCurveTo(cx - ikx, cy - iry, cx - irx, cy - iky, cx - irx, cy);
    // Execute statement: p.bezierCurveTo(cx - irx, cy + iky, cx - ikx, cy + iry, cx, cy + iry);
    p.bezierCurveTo(cx - irx, cy + iky, cx - ikx, cy + iry, cx, cy + iry);
    // Execute statement: p.close();
    p.close();
  });

  // Return value glyphs; to caller
  return glyphs;
}

// Vector embolden function (CCW normal pointing outwards)
function emboldenGlyph(glyph, strengthX = 26, strengthY = 15) {
  // Define constant p set to new opentype.Path();
  const p = new opentype.Path();
  // Define constant cmds set to glyph.path.commands;
  const cmds = glyph.path.commands;
  // Check condition: !cmds || cmds.length === 0
  if (!cmds || cmds.length === 0) {
    // Return value new opentype.Glyph({ to caller
    return new opentype.Glyph({
      // Define property name with type glyph.name,
      name: glyph.name,
      // Define property unicode with type glyph.unicode,
      unicode: glyph.unicode,
      // Define property advanceWidth with type glyph.advanceWidth + Math.round(strengthX * 1.5),
      advanceWidth: glyph.advanceWidth + Math.round(strengthX * 1.5),
      // Define property path with type p
      path: p
    });
  }

  // Define constant contours set to [];
  const contours = [];
  // Declare variable curr initialized to [];
  let curr = [];
  // Execute statement: for (const cmd of cmds) {
  for (const cmd of cmds) {
    // Execute statement: curr.push(cmd);
    curr.push(cmd);
    // Check condition: cmd.type === 'Z'
    if (cmd.type === 'Z') {
      // Execute statement: contours.push(curr);
      contours.push(curr);
      // Set curr to [];
      curr = [];
    }
  }
  // Check condition: curr.length > 0) contours.push(curr
  if (curr.length > 0) contours.push(curr);

  // Execute statement: for (const contour of contours) {
  for (const contour of contours) {
    // Define constant pts set to [];
    const pts = [];
    // Execute statement: for (const cmd of contour) {
    for (const cmd of contour) {
      // Check condition: cmd.type === 'M' || cmd.type === 'L'
      if (cmd.type === 'M' || cmd.type === 'L') {
        // Execute statement: pts.push({ x: cmd.x, y: cmd.y });
        pts.push({ x: cmd.x, y: cmd.y });
      // Execute statement: } else if (cmd.type === 'Q') {
      } else if (cmd.type === 'Q') {
        // Execute statement: pts.push({ x: cmd.x1, y: cmd.y1 });
        pts.push({ x: cmd.x1, y: cmd.y1 });
        // Execute statement: pts.push({ x: cmd.x, y: cmd.y });
        pts.push({ x: cmd.x, y: cmd.y });
      // Execute statement: } else if (cmd.type === 'C') {
      } else if (cmd.type === 'C') {
        // Execute statement: pts.push({ x: cmd.x1, y: cmd.y1 });
        pts.push({ x: cmd.x1, y: cmd.y1 });
        // Execute statement: pts.push({ x: cmd.x2, y: cmd.y2 });
        pts.push({ x: cmd.x2, y: cmd.y2 });
        // Execute statement: pts.push({ x: cmd.x, y: cmd.y });
        pts.push({ x: cmd.x, y: cmd.y });
      }
    }

    // Define constant n set to pts.length;
    const n = pts.length;
    // Check condition: n < 3
    if (n < 3) {
      // Execute statement: for (const cmd of contour) {
      for (const cmd of contour) {
        // Check condition: cmd.type === 'M') p.moveTo(cmd.x, cmd.y
        if (cmd.type === 'M') p.moveTo(cmd.x, cmd.y);
        // Alternative condition check: cmd.type === 'L') p.lineTo(cmd.x, cmd.y
        else if (cmd.type === 'L') p.lineTo(cmd.x, cmd.y);
        // Alternative condition check: cmd.type === 'Q') p.quadTo(cmd.x1, cmd.y1, cmd.x, cmd.y
        else if (cmd.type === 'Q') p.quadTo(cmd.x1, cmd.y1, cmd.x, cmd.y);
        // Alternative condition check: cmd.type === 'C') p.bezierCurveTo(cmd.x1, cmd.y1, cmd.x2, cmd.y2, cmd.x, cmd.y
        else if (cmd.type === 'C') p.bezierCurveTo(cmd.x1, cmd.y1, cmd.x2, cmd.y2, cmd.x, cmd.y);
        // Alternative condition check: cmd.type === 'Z') p.close(
        else if (cmd.type === 'Z') p.close();
      }
      // Skip to next loop iteration
      continue;
    }

    // Define constant offsets set to [];
    const offsets = [];
    // Execute statement: for (let i = 0; i < n; i++) {
    for (let i = 0; i < n; i++) {
      // Define constant prev set to pts[(i - 1 + n) % n];
      const prev = pts[(i - 1 + n) % n];
      // Define constant next set to pts[(i + 1) % n];
      const next = pts[(i + 1) % n];
      // Declare variable dx initialized to next.x - prev.x;
      let dx = next.x - prev.x;
      // Declare variable dy initialized to next.y - prev.y;
      let dy = next.y - prev.y;
      // Define constant len set to Math.hypot(dx, dy) || 1;
      const len = Math.hypot(dx, dy) || 1;
      // Execute statement: dx /= len;
      dx /= len;
      // Execute statement: dy /= len;
      dy /= len;
      // Normal vector
      const nx = -dy;
      // Define constant ny set to dx;
      const ny = dx;
      // Execute statement: offsets.push({ ox: nx * strengthX, oy: ny * strengthY });
      offsets.push({ ox: nx * strengthX, oy: ny * strengthY });
    }

    // Declare variable ptIdx initialized to 0;
    let ptIdx = 0;
    // Execute statement: for (const cmd of contour) {
    for (const cmd of contour) {
      // Check condition: cmd.type === 'M'
      if (cmd.type === 'M') {
        // Define constant off set to offsets[ptIdx++];
        const off = offsets[ptIdx++];
        // Execute statement: p.moveTo(cmd.x + off.ox, cmd.y + off.oy);
        p.moveTo(cmd.x + off.ox, cmd.y + off.oy);
      // Execute statement: } else if (cmd.type === 'L') {
      } else if (cmd.type === 'L') {
        // Define constant off set to offsets[ptIdx++];
        const off = offsets[ptIdx++];
        // Execute statement: p.lineTo(cmd.x + off.ox, cmd.y + off.oy);
        p.lineTo(cmd.x + off.ox, cmd.y + off.oy);
      // Execute statement: } else if (cmd.type === 'Q') {
      } else if (cmd.type === 'Q') {
        // Define constant off1 set to offsets[ptIdx++];
        const off1 = offsets[ptIdx++];
        // Define constant off2 set to offsets[ptIdx++];
        const off2 = offsets[ptIdx++];
        // Execute statement: p.quadTo(cmd.x1 + off1.ox, cmd.y1 + off1.oy, cmd.x + off2.ox, cmd.y + off2.oy);
        p.quadTo(cmd.x1 + off1.ox, cmd.y1 + off1.oy, cmd.x + off2.ox, cmd.y + off2.oy);
      // Execute statement: } else if (cmd.type === 'C') {
      } else if (cmd.type === 'C') {
        // Define constant off1 set to offsets[ptIdx++];
        const off1 = offsets[ptIdx++];
        // Define constant off2 set to offsets[ptIdx++];
        const off2 = offsets[ptIdx++];
        // Define constant off3 set to offsets[ptIdx++];
        const off3 = offsets[ptIdx++];
        // Execute statement: p.bezierCurveTo(cmd.x1 + off1.ox, cmd.y1 + off1.oy, cmd.x2 + off2.ox, cmd.y2 + off2.oy, cmd.x + off3.ox, cmd.y + off3.oy);
        p.bezierCurveTo(cmd.x1 + off1.ox, cmd.y1 + off1.oy, cmd.x2 + off2.ox, cmd.y2 + off2.oy, cmd.x + off3.ox, cmd.y + off3.oy);
      // Execute statement: } else if (cmd.type === 'Z') {
      } else if (cmd.type === 'Z') {
        // Execute statement: p.close();
        p.close();
      }
    }
  }

  // Return value new opentype.Glyph({ to caller
  return new opentype.Glyph({
    // Define property name with type glyph.name,
    name: glyph.name,
    // Define property unicode with type glyph.unicode,
    unicode: glyph.unicode,
    // Define property advanceWidth with type glyph.advanceWidth + Math.round(strengthX * 1.5),
    advanceWidth: glyph.advanceWidth + Math.round(strengthX * 1.5),
    // Define property path with type p
    path: p
  });
}

// Define asynchronous function buildFamily()
async function buildFamily() {
  // Log diagnostic message to console: 'Building Julius font family...'
  console.log('Building Julius font family...');

  // Define constant missingReg set to createMissingGlyphs(false);
  const missingReg = createMissingGlyphs(false);
  // Define constant missingBold set to createMissingGlyphs(true);
  const missingBold = createMissingGlyphs(true);

  // 1. Regular Glyphs
  const regGlyphs = [];
  // Execute statement: for (let i = 0; i < masterFont.glyphs.length; i++) {
  for (let i = 0; i < masterFont.glyphs.length; i++) {
    // Define constant g set to masterFont.glyphs.get(i);
    const g = masterFont.glyphs.get(i);
    // Clone glyph
    regGlyphs.push(new opentype.Glyph({
      // Define property name with type g.name,
      name: g.name,
      // Define property unicode with type g.unicode,
      unicode: g.unicode,
      // Define property unicodes with type g.unicodes,
      unicodes: g.unicodes,
      // Define property advanceWidth with type g.advanceWidth,
      advanceWidth: g.advanceWidth,
      // Define property path with type g.path
      path: g.path
    }));
  }
  // Append missing
  for (const uc of Object.keys(missingReg)) {
    // Execute statement: regGlyphs.push(missingReg[uc]);
    regGlyphs.push(missingReg[uc]);
  }

  // 2. Bold Glyphs
  const boldGlyphs = [];
  // Execute statement: for (let i = 0; i < masterFont.glyphs.length; i++) {
  for (let i = 0; i < masterFont.glyphs.length; i++) {
    // Define constant g set to masterFont.glyphs.get(i);
    const g = masterFont.glyphs.get(i);
    // Check condition: !g.path || g.path.commands.length === 0
    if (!g.path || g.path.commands.length === 0) {
      // Execute statement: boldGlyphs.push(new opentype.Glyph({
      boldGlyphs.push(new opentype.Glyph({
        // Define property name with type g.name,
        name: g.name,
        // Define property unicode with type g.unicode,
        unicode: g.unicode,
        // Define property unicodes with type g.unicodes,
        unicodes: g.unicodes,
        // Define property advanceWidth with type g.advanceWidth + 30,
        advanceWidth: g.advanceWidth + 30,
        // Define property path with type new opentype.Path()
        path: new opentype.Path()
      }));
    // Execute statement: } else {
    } else {
      // Execute statement: boldGlyphs.push(emboldenGlyph(g, 26, 15));
      boldGlyphs.push(emboldenGlyph(g, 26, 15));
    }
  }
  // Execute statement: for (const uc of Object.keys(missingBold)) {
  for (const uc of Object.keys(missingBold)) {
    // Execute statement: boldGlyphs.push(missingBold[uc]);
    boldGlyphs.push(missingBold[uc]);
  }

  // Log diagnostic message to console: `Glyph count: ${regGlyphs.length} (Regular) / ${boldGlyphs.length} (Bold)`
  console.log(`Glyph count: ${regGlyphs.length} (Regular) / ${boldGlyphs.length} (Bold)`);

  // Construct fonts
  const fontReg = new opentype.Font({
    // Define property familyName with type 'Julius',
    familyName: 'Julius',
    // Define property styleName with type 'Regular',
    styleName: 'Regular',
    // Define property unitsPerEm with type UPM,
    unitsPerEm: UPM,
    // Define property ascender with type ASC,
    ascender: ASC,
    // Define property descender with type DESC,
    descender: DESC,
    // Define property glyphs with type regGlyphs
    glyphs: regGlyphs
  });

  // Define constant fontBold set to new opentype.Font({
  const fontBold = new opentype.Font({
    // Define property familyName with type 'Julius',
    familyName: 'Julius',
    // Define property styleName with type 'Bold',
    styleName: 'Bold',
    // Define property unitsPerEm with type UPM,
    unitsPerEm: UPM,
    // Define property ascender with type ASC,
    ascender: ASC,
    // Define property descender with type DESC,
    descender: DESC,
    // Define property glyphs with type boldGlyphs
    glyphs: boldGlyphs
  });

  // Define constant destDir set to path.join(__dirname, '..', 'Julius_Fonts');
  const destDir = path.join(__dirname, '..', 'Julius_Fonts');

  // Export Regular
  const ttfReg = Buffer.from(fontReg.toArrayBuffer());
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Regular.ttf'), ttfReg);
  fs.writeFileSync(path.join(destDir, 'Julius-Regular.ttf'), ttfReg);
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Regular.otf'), ttfReg);
  fs.writeFileSync(path.join(destDir, 'Julius-Regular.otf'), ttfReg);
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius.ttf'), ttfReg);
  fs.writeFileSync(path.join(destDir, 'Julius.ttf'), ttfReg);

  // Define constant woffReg set to Buffer.from(ttf2woff(ttfReg));
  const woffReg = Buffer.from(ttf2woff(ttfReg));
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Regular.woff'), woffReg);
  fs.writeFileSync(path.join(destDir, 'Julius-Regular.woff'), woffReg);

  // Define constant woff2Reg set to Buffer.from(await wawoff2.compress(ttfReg));
  const woff2Reg = Buffer.from(await wawoff2.compress(ttfReg));
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Regular.woff2'), woff2Reg);
  fs.writeFileSync(path.join(destDir, 'Julius-Regular.woff2'), woff2Reg);
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius.woff2'), woff2Reg);
  fs.writeFileSync(path.join(destDir, 'Julius.woff2'), woff2Reg);

  // Export Bold
  const ttfBold = Buffer.from(fontBold.toArrayBuffer());
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Bold.ttf'), ttfBold);
  fs.writeFileSync(path.join(destDir, 'Julius-Bold.ttf'), ttfBold);
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Bold.otf'), ttfBold);
  fs.writeFileSync(path.join(destDir, 'Julius-Bold.otf'), ttfBold);

  // Define constant woffBold set to Buffer.from(ttf2woff(ttfBold));
  const woffBold = Buffer.from(ttf2woff(ttfBold));
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Bold.woff'), woffBold);
  fs.writeFileSync(path.join(destDir, 'Julius-Bold.woff'), woffBold);

  // Define constant woff2Bold set to Buffer.from(await wawoff2.compress(ttfBold));
  const woff2Bold = Buffer.from(await wawoff2.compress(ttfBold));
  // Execute statement: fs.writeFileSync(path.join(destDir, 'Julius-Bold.woff2'), woff2Bold);
  fs.writeFileSync(path.join(destDir, 'Julius-Bold.woff2'), woff2Bold);

  // Log diagnostic message to console: 'Successfully generated:'
  console.log('Successfully generated:');
  // Log diagnostic message to console: '  Julius-Regular.ttf, .otf, .woff, .woff2'
  console.log('  Julius-Regular.ttf, .otf, .woff, .woff2');
  // Log diagnostic message to console: '  Julius-Bold.ttf, .otf, .woff, .woff2'
  console.log('  Julius-Bold.ttf, .otf, .woff, .woff2');

  // Generate specimen SVG & PNG
  fontReg.kerningPairs = {};
  // Set fontBold.kerningPairs to {};
  fontBold.kerningPairs = {};

  // Define constant lines set to [
  const lines = [
    // Execute statement: { font: fontBold, text: 'Julius Typography', size: 64, y: 100 },
    { font: fontBold, text: 'Julius Typography', size: 64, y: 100 },
    // Execute statement: { font: fontReg, text: 'Apple Curve Aesthetics · Claude Magic of Affection', size: 28, y: 160 },
    { font: fontReg, text: 'Apple Curve Aesthetics · Claude Magic of Affection', size: 28, y: 160 },
    // Execute statement: { font: fontReg, text: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', size: 32, y: 230 },
    { font: fontReg, text: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', size: 32, y: 230 },
    // Execute statement: { font: fontReg, text: 'abcdefghijklmnopqrstuvwxyz', size: 32, y: 290 },
    { font: fontReg, text: 'abcdefghijklmnopqrstuvwxyz', size: 32, y: 290 },
    // Execute statement: { font: fontReg, text: '0123456789 · !?@#$%&*+-=()/{}[]', size: 30, y: 350 },
    { font: fontReg, text: '0123456789 · !?@#$%&*+-=()/{}[]', size: 30, y: 350 },
    // Execute statement: { font: fontReg, text: 'The quick brown fox jumps over the lazy dog.', size: 28, y: 420 },
    { font: fontReg, text: 'The quick brown fox jumps over the lazy dog.', size: 28, y: 420 },
    // Execute statement: { font: fontBold, text: 'High-legibility reading with warm humanist affection.', size: 28, y: 480 },
    { font: fontBold, text: 'High-legibility reading with warm humanist affection.', size: 28, y: 480 },
  // Execute statement: ];
  ];

  let svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 560" width="1100" height="560">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0c10"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="titleGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="50%" stop-color="#ec4899"/>
      <stop offset="100%" stop-color="#8b5cf6"/>
    </linearGradient>
  </defs>
  <rect width="1100" height="560" rx="20" fill="url(#bg)"/>
  <rect x="20" y="20" width="1060" height="520" rx="14" fill="none" stroke="#30363d" stroke-width="1.5"/>
`;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const p = line.font.getPath(line.text, 60, line.y, line.size);
    const color = i === 0 ? 'url(#titleGrad)' : (i === 1 ? '#e6edf3' : (i >= 5 ? '#58a6ff' : '#8b949e'));
    svgContent += `  <g fill="${color}">\n    ${p.toSVG(2)}\n  </g>\n`;
  }
  svgContent += `</svg>`;

  fs.writeFileSync(path.join(destDir, 'julius_font_specimen.svg'), svgContent);
  await sharp(Buffer.from(svgContent)).png().toFile(path.join(destDir, 'julius_font_specimen.png'));
  console.log('Saved julius_font_specimen.png & svg');
}

buildFamily().catch(console.error);
