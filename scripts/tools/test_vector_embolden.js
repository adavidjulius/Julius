const opentype = require('../.agents/skills/draw-your-font/engine/node_modules/opentype.js');
const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const fs = require('fs');
const path = require('path');

const font = opentype.loadSync(path.join(__dirname, 'reel_frame.ttf'));

function emboldenGlyph(glyph, strengthX = 28, strengthY = 16) {
  const p = new opentype.Path();
  const cmds = glyph.path.commands;
  if (!cmds || cmds.length === 0) {
    return new opentype.Glyph({
      name: glyph.name,
      unicode: glyph.unicode,
      advanceWidth: glyph.advanceWidth + strengthX * 2,
      path: p
    });
  }

  // Split commands into contours (between M and Z)
  const contours = [];
  let curr = [];
  for (const cmd of cmds) {
    curr.push(cmd);
    if (cmd.type === 'Z') {
      contours.push(curr);
      curr = [];
    }
  }
  if (curr.length > 0) contours.push(curr);

  for (const contour of contours) {
    // Extract points in contour
    const pts = [];
    for (const cmd of contour) {
      if (cmd.type === 'M' || cmd.type === 'L') {
        pts.push({ x: cmd.x, y: cmd.y, cmd, field: 'x' });
      } else if (cmd.type === 'Q') {
        pts.push({ x: cmd.x1, y: cmd.y1, cmd, field: 'ctrl' });
        pts.push({ x: cmd.x, y: cmd.y, cmd, field: 'x' });
      } else if (cmd.type === 'C') {
        pts.push({ x: cmd.x1, y: cmd.y1, cmd, field: 'c1' });
        pts.push({ x: cmd.x2, y: cmd.y2, cmd, field: 'c2' });
        pts.push({ x: cmd.x, y: cmd.y, cmd, field: 'x' });
      }
    }

    const n = pts.length;
    if (n < 3) {
      // Just copy
      for (const cmd of contour) {
        if (cmd.type === 'M') p.moveTo(cmd.x, cmd.y);
        else if (cmd.type === 'L') p.lineTo(cmd.x, cmd.y);
        else if (cmd.type === 'Q') p.quadTo(cmd.x1, cmd.y1, cmd.x, cmd.y);
        else if (cmd.type === 'C') p.bezierCurveTo(cmd.x1, cmd.y1, cmd.x2, cmd.y2, cmd.x, cmd.y);
        else if (cmd.type === 'Z') p.close();
      }
      continue;
    }

    // Compute normals for each point
    const offsets = [];
    for (let i = 0; i < n; i++) {
      const prev = pts[(i - 1 + n) % n];
      const next = pts[(i + 1) % n];
      let dx = next.x - prev.x;
      let dy = next.y - prev.y;
      const len = Math.hypot(dx, dy) || 1;
      dx /= len;
      dy /= len;
      // Normal vector pointing to the right of travel (outwards for CW, inwards for CCW)
      const nx = -dy;
      const ny = dx;
      offsets.push({ ox: nx * strengthX, oy: ny * strengthY });
    }

    // Reconstruct commands with offsets
    let ptIdx = 0;
    for (const cmd of contour) {
      if (cmd.type === 'M') {
        const off = offsets[ptIdx++];
        p.moveTo(cmd.x + off.ox, cmd.y + off.oy);
      } else if (cmd.type === 'L') {
        const off = offsets[ptIdx++];
        p.lineTo(cmd.x + off.ox, cmd.y + off.oy);
      } else if (cmd.type === 'Q') {
        const off1 = offsets[ptIdx++];
        const off2 = offsets[ptIdx++];
        p.quadTo(cmd.x1 + off1.ox, cmd.y1 + off1.oy, cmd.x + off2.ox, cmd.y + off2.oy);
      } else if (cmd.type === 'C') {
        const off1 = offsets[ptIdx++];
        const off2 = offsets[ptIdx++];
        const off3 = offsets[ptIdx++];
        p.bezierCurveTo(cmd.x1 + off1.ox, cmd.y1 + off1.oy, cmd.x2 + off2.ox, cmd.y2 + off2.oy, cmd.x + off3.ox, cmd.y + off3.oy);
      } else if (cmd.type === 'Z') {
        p.close();
      }
    }
  }

  return new opentype.Glyph({
    name: glyph.name,
    unicode: glyph.unicode,
    advanceWidth: glyph.advanceWidth + Math.round(strengthX * 1.2),
    path: p
  });
}

const origA = font.charToGlyph('A');
const boldA = emboldenGlyph(origA, 32, 18);

// Define constant svg set to `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300">
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300">
  <rect width="600" height="300" fill="#161b22"/>
  <g fill="#58a6ff" transform="translate(50, 230) scale(0.25, -0.25)">
    ${origA.path.toSVG(2)}
  </g>
  <g fill="#f59e0b" transform="translate(320, 230) scale(0.25, -0.25)">
    ${boldA.path.toSVG(2)}
  </g>
</svg>`;

// Execute statement: fs.writeFileSync(path.join(__dirname, 'test_bold_A.svg'), svg);
fs.writeFileSync(path.join(__dirname, 'test_bold_A.svg'), svg);
// Execute statement: sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_bold_A.png')).then(() => {
sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_bold_A.png')).then(() => {
  // Log diagnostic message to console: 'Saved test_bold_A.png'
  console.log('Saved test_bold_A.png');
});
