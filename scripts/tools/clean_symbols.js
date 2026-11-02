const opentype = require('opentype.js');
const fs = require('fs');
const sharp = require('sharp');
const potrace = require('potrace');

function svgDToFontPath(d, baselineY, scale = 1.0) {
  const p = new opentype.Path();
  const tokens = d.match(/([a-zA-Z]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)/g);
  if (!tokens) return p;

  let i = 0;
  let cmd = '';

  function nextNum() {
    return parseFloat(tokens[i++]);
  }

  function toFontX(x) {
    return Math.round(x * scale);
  }

  function toFontY(y) {
    return Math.round((baselineY - y) * scale);
  }

  while (i < tokens.length) {
    const t = tokens[i++];
    if (/^[a-zA-Z]$/.test(t)) {
      cmd = t;
    } else {
      i--;
    }

    if (cmd === 'M') {
      const x = nextNum(), y = nextNum();
      p.moveTo(toFontX(x), toFontY(y));
    } else if (cmd === 'L') {
      const x = nextNum(), y = nextNum();
      p.lineTo(toFontX(x), toFontY(y));
    } else if (cmd === 'C') {
      const x1 = nextNum(), y1 = nextNum();
      const x2 = nextNum(), y2 = nextNum();
      const x = nextNum(), y = nextNum();
      p.bezierCurveTo(toFontX(x1), toFontY(y1), toFontX(x2), toFontY(y2), toFontX(x), toFontY(y));
    } else if (cmd === 'Q') {
      const x1 = nextNum(), y1 = nextNum();
      const x = nextNum(), y = nextNum();
      p.quadTo(toFontX(x1), toFontY(y1), toFontX(x), toFontY(y));
    } else if (cmd === 'Z' || cmd === 'z') {
      p.close();
    }
  }

  return p;
}

// Geometric paths for perfectly crisp basic symbols
function createExactPath(char, isBold = false) {
  const p = new opentype.Path();
  const stroke = isBold ? 65 : 46;
  const halfS = stroke / 2;

  if (char === '_') {
    // Underscore: clean bar below baseline
    const yTop = -40;
    const yBottom = yTop - stroke;
    const x1 = 40;
    const x2 = 460;
    p.moveTo(x1, yTop);
    p.lineTo(x2, yTop);
    p.lineTo(x2, yBottom);
    p.lineTo(x1, yBottom);
    p.close();
    return { path: p, adv: 500 };
  }

  if (char === '-') {
    // Hyphen: centered at mid x-height (y=230)
    const yTop = 230 + halfS;
    const yBottom = 230 - halfS;
    const x1 = 60;
    const x2 = 380;
    p.moveTo(x1, yTop);
    p.lineTo(x2, yTop);
    p.lineTo(x2, yBottom);
    p.lineTo(x1, yBottom);
    p.close();
    return { path: p, adv: 440 };
  }

  if (char === '=') {
    // Equals: two parallel horizontal bars
    const y1 = 310;
    const y2 = 180;
    const x1 = 60;
    const x2 = 440;
    p.moveTo(x1, y1 + halfS);
    p.lineTo(x2, y1 + halfS);
    p.lineTo(x2, y1 - halfS);
    p.lineTo(x1, y1 - halfS);
    p.close();
    p.moveTo(x1, y2 + halfS);
    p.lineTo(x2, y2 + halfS);
    p.lineTo(x2, y2 - halfS);
    p.lineTo(x1, y2 - halfS);
    p.close();
    return { path: p, adv: 500 };
  }

  if (char === '+') {
    // Plus: intersecting bars
    const midY = 245;
    const midX = 260;
    const arm = 155;
    p.moveTo(midX - arm, midY + halfS);
    p.lineTo(midX - halfS, midY + halfS);
    p.lineTo(midX - halfS, midY + arm);
    p.lineTo(midX + halfS, midY + arm);
    p.lineTo(midX + halfS, midY + halfS);
    p.lineTo(midX + arm, midY + halfS);
    p.lineTo(midX + arm, midY - halfS);
    p.lineTo(midX + halfS, midY - halfS);
    p.lineTo(midX + halfS, midY - arm);
    p.lineTo(midX - halfS, midY - arm);
    p.lineTo(midX - halfS, midY - halfS);
    p.lineTo(midX - arm, midY - halfS);
    p.close();
    return { path: p, adv: 520 };
  }

  if (char === '|') {
    const midX = 160;
    const yTop = 680;
    const yBottom = -60;
    p.moveTo(midX - halfS, yTop);
    p.lineTo(midX + halfS, yTop);
    p.lineTo(midX + halfS, yBottom);
    p.lineTo(midX - halfS, yBottom);
    p.close();
    return { path: p, adv: 320 };
  }

  if (char === '/') {
    // Diagonal slash
    p.moveTo(340, 680);
    p.lineTo(340 + stroke, 680);
    p.lineTo(80 + stroke, -60);
    p.lineTo(80, -60);
    p.close();
    return { path: p, adv: 440 };
  }

  if (char === '\\') {
    // Backslash
    p.moveTo(80, 680);
    p.lineTo(80 + stroke, 680);
    p.lineTo(340 + stroke, -60);
    p.lineTo(340, -60);
    p.close();
    return { path: p, adv: 440 };
  }

  if (char === '<') {
    // Less than chevron
    const midY = 245;
    const xTip = 80;
    const xBase = 370;
    const yTop = midY + 165;
    const yBot = midY - 165;
    const thick = stroke * 1.25;
    p.moveTo(xBase, yTop);
    p.lineTo(xTip, midY);
    p.lineTo(xBase, yBot);
    p.lineTo(xBase, yBot + thick);
    p.lineTo(xTip + thick, midY);
    p.lineTo(xBase, yTop - thick);
    p.close();
    return { path: p, adv: 460 };
  }

  if (char === '>') {
    // Greater than chevron
    const midY = 245;
    const xTip = 380;
    const xBase = 90;
    const yTop = midY + 165;
    const yBot = midY - 165;
    const thick = stroke * 1.25;
    p.moveTo(xBase, yTop);
    p.lineTo(xTip, midY);
    p.lineTo(xBase, yBot);
    p.lineTo(xBase, yBot + thick);
    p.lineTo(xTip - thick, midY);
    p.lineTo(xBase, yTop - thick);
    p.close();
    return { path: p, adv: 460 };
  }

  return null;
}

// Tracing for complex standard symbols with Helvetica/Arial clean sans-serif
async function traceCleanSymbol(char, isBold = false) {
  const direct = createExactPath(char, isBold);
  if (direct) return direct;

  const weight = isBold ? '700' : '400';
  const escapedChar = char === '&' ? '&amp;' : (char === '<' ? '&lt;' : (char === '>' ? '&gt;' : (char === '"' ? '&quot;' : char)));
  
  const size = 480;
  const baselineY = 490;
  // Define constant svg set to `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
    <rect width="600" height="600" fill="white"/>
    <text x="300" y="${baselineY}" font-family="Helvetica Neue, Arial, sans-serif" font-weight="${weight}" font-size="${size}" text-anchor="middle" fill="black">${escapedChar}</text>
  </svg>`;

  // Define constant png set to await sharp(Buffer.from(svg)).png().toBuffer();
  const png = await sharp(Buffer.from(svg)).png().toBuffer();

  // Return value new Promise((resolve, reject) => { to caller
  return new Promise((resolve, reject) => {
    // Execute statement: potrace.trace(png, {
    potrace.trace(png, {
      // Define property turdSize with type 2,
      turdSize: 2,
      // Define property optTolerance with type 0.15,
      optTolerance: 0.15,
      // Define property threshold with type 128
      threshold: 128
    }, (err, svgOut) => {
      // Check condition: err) return reject(err
      if (err) return reject(err);
      // Define constant match set to svgOut.match(/d="([^"]+)"/);
      const match = svgOut.match(/d="([^"]+)"/);
      // Check condition: !match) return resolve({ path: new opentype.Path(), adv: 500 }
      if (!match) return resolve({ path: new opentype.Path(), adv: 500 });
      // Define constant scale set to 1024 / 600;
      const scale = 1024 / 600;
      // Define constant path set to svgDToFontPath(match[1], baselineY, scale);
      const path = svgDToFontPath(match[1], baselineY, scale);
      // Define constant bbox set to path.getBoundingBox();
      const bbox = path.getBoundingBox();
      // Define constant glyphWidth set to bbox.x2 - bbox.x1;
      const glyphWidth = bbox.x2 - bbox.x1;
      // Define constant adv set to Math.max(Math.round(glyphWidth + (isBold ? 140 : 120)), 380);
      const adv = Math.max(Math.round(glyphWidth + (isBold ? 140 : 120)), 380);
      // Execute statement: resolve({ path, adv });
      resolve({ path, adv });
    });
  });
}

// Set module.exports to { createExactPath, traceCleanSymbol };
module.exports = { createExactPath, traceCleanSymbol };

// Check condition: require.main === module
if (require.main === module) {
  // Execute statement: (async () => {
  (async () => {
    const testChars = ['#', '$', '%', '&', '*', '@', '^', '`', '{', '}', '~'];
    // Execute statement: for (const c of testChars) {
    for (const c of testChars) {
      // Define constant res set to await traceCleanSymbol(c, false);
      const res = await traceCleanSymbol(c, false);
      // Define constant bbox set to res.path.getBoundingBox();
      const bbox = res.path.getBoundingBox();
      // Log diagnostic message to console: `Char ${c}: cmds=${res.path.commands.length}, adv=${res.adv}, bbox=[${bbox.x1.toFixed(0)}, ${bbox.y1.toFixed(0)}, ${bbox.x2.toFixed(0)}, ${bbox.y2.toFixed(0)}]`
      console.log(`Char ${c}: cmds=${res.path.commands.length}, adv=${res.adv}, bbox=[${bbox.x1.toFixed(0)}, ${bbox.y1.toFixed(0)}, ${bbox.x2.toFixed(0)}, ${bbox.y2.toFixed(0)}]`);
    }
  })();
}
