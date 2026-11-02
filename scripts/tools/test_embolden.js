const opentype = require('../.agents/skills/draw-your-font/engine/node_modules/opentype.js');
const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const fs = require('fs');
const path = require('path');

const font = opentype.loadSync(path.join(__dirname, 'reel_frame.ttf'));

// Embolden a glyph path:
// Horizontal expansion dx, vertical expansion dy
function emboldenPath(origPath, dx = 32, dy = 16) {
  const p = new opentype.Path();
  const cmds = origPath.commands;
  if (!cmds || cmds.length === 0) return p;

  // Find center of bounding box to expand outwards
  const bb = origPath.getBoundingBox();
  const cx = (bb.x1 + bb.x2) / 2;
  const cy = (bb.y1 + bb.y2) / 2;

  for (let i = 0; i < cmds.length; i++) {
    const cmd = cmds[i];
    if (cmd.type === 'M') {
      const sx = cmd.x > cx ? dx : -dx;
      const sy = cmd.y > cy ? dy : -dy;
      p.moveTo(cmd.x + sx, cmd.y + sy);
    } else if (cmd.type === 'L') {
      const sx = cmd.x > cx ? dx : -dx;
      const sy = cmd.y > cy ? dy : -dy;
      p.lineTo(cmd.x + sx, cmd.y + sy);
    } else if (cmd.type === 'C') {
      const s1x = cmd.x1 > cx ? dx : -dx;
      const s1y = cmd.y1 > cy ? dy : -dy;
      const s2x = cmd.x2 > cx ? dx : -dx;
      const s2y = cmd.y2 > cy ? dy : -dy;
      const sx = cmd.x > cx ? dx : -dx;
      const sy = cmd.y > cy ? dy : -dy;
      p.bezierCurveTo(cmd.x1 + s1x, cmd.y1 + s1y, cmd.x2 + s2x, cmd.y2 + s2y, cmd.x + sx, cmd.y + sy);
    } else if (cmd.type === 'Q') {
      const s1x = cmd.x1 > cx ? dx : -dx;
      const s1y = cmd.y1 > cy ? dy : -dy;
      const sx = cmd.x > cx ? dx : -dx;
      const sy = cmd.y > cy ? dy : -dy;
      p.quadTo(cmd.x1 + s1x, cmd.y1 + s1y, cmd.x + sx, cmd.y + sy);
    } else if (cmd.type === 'Z') {
      p.close();
    }
  }
  return p;
}

// Alternatively, let's test SVG stroke expansion!
// When SVG path is rendered with stroke-width and stroke-linejoin="round",
// it naturally produces a perfect, smooth bold weight!
console.log('Testing emboldening methods...');
