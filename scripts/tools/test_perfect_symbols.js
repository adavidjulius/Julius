const opentype = require('opentype.js');
const fs = require('fs');
const sharp = require('sharp');
const potrace = require('potrace');

// Helper to convert SVG path d to opentype.Path
function svgDToFontPath(d, baselineY, scale = 1.0, fontUnitsPerEm = 1024) {
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

// Clean vector generator for pure geometric symbols
function createCleanPath(char, isBold = false) {
  const p = new opentype.Path();
  const stroke = isBold ? 65 : 48;
  const halfS = stroke / 2;

  if (char === '_') {
    // Underscore: horizontal bar below baseline, rounded or clean
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
    // Hyphen: centered at half x-height (around y=230)
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
    const y1 = 320;
    const y2 = 180;
    const x1 = 60;
    const x2 = 460;
    // Top bar
    p.moveTo(x1, y1 + halfS);
    p.lineTo(x2, y1 + halfS);
    p.lineTo(x2, y1 - halfS);
    p.lineTo(x1, y1 - halfS);
    p.close();
    // Bottom bar
    p.moveTo(x1, y2 + halfS);
    p.lineTo(x2, y2 + halfS);
    p.lineTo(x2, y2 - halfS);
    p.lineTo(x1, y2 - halfS);
    p.close();
    return { path: p, adv: 520 };
  }

  if (char === '+') {
    // Plus: horizontal & vertical intersecting bars
    const midY = 250;
    const midX = 260;
    const arm = 170;
    // Horizontal
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
    // Vertical bar
    const midX = 160;
    const yTop = 680;
    const yBottom = -80;
    p.moveTo(midX - halfS, yTop);
    p.lineTo(midX + halfS, yTop);
    p.lineTo(midX + halfS, yBottom);
    p.lineTo(midX - halfS, yBottom);
    p.close();
    return { path: p, adv: 320 };
  }

  if (char === '/') {
    // Slash: diagonal from (60, -40) to (380, 680)
    const slant = 18; // degrees
    p.moveTo(350, 680);
    p.lineTo(350 + stroke, 680);
    p.lineTo(80 + stroke, -60);
    p.lineTo(80, -60);
    p.close();
    return { path: p, adv: 440 };
  }

  if (char === '\\') {
    // Backslash: diagonal from (80, 680) to (350, -60)
    p.moveTo(80, 680);
    p.lineTo(80 + stroke, 680);
    p.lineTo(350 + stroke, -60);
    p.lineTo(350, -60);
    p.close();
    return { path: p, adv: 440 };
  }

  if (char === '<') {
    // Less than: chevron pointing left
    const midY = 250;
    const xTip = 80;
    const xBase = 380;
    const yTop = midY + 180;
    const yBot = midY - 180;
    p.moveTo(xBase, yTop);
    p.lineTo(xTip, midY);
    p.lineTo(xBase, yBot);
    p.lineTo(xBase, yBot + stroke * 1.3);
    p.lineTo(xTip + stroke * 1.3, midY);
    p.lineTo(xBase, yTop - stroke * 1.3);
    p.close();
    return { path: p, adv: 480 };
  }

  if (char === '>') {
    // Greater than: chevron pointing right
    const midY = 250;
    const xTip = 400;
    const xBase = 100;
    const yTop = midY + 180;
    const yBot = midY - 180;
    p.moveTo(xBase, yTop);
    p.lineTo(xTip, midY);
    p.lineTo(xBase, yBot);
    p.lineTo(xBase, yBot + stroke * 1.3);
    p.lineTo(xTip - stroke * 1.3, midY);
    p.lineTo(xBase, yTop - stroke * 1.3);
    p.close();
    return { path: p, adv: 480 };
  }

  return null;
}

// Crisp modern tracing for complex symbols (#, @, &, *, {, }, etc.)
async function traceCleanSymbol(char, isBold = false) {
  const direct = createCleanPath(char, isBold);
  if (direct) return direct;

  const weight = isBold ? '700' : '500';
  const escapedChar = char === '&' ? '&amp;' : (char === '<' ? '&lt;' : (char === '>' ? '&gt;' : (char === '"' ? '&quot;' : char)));
  
  // Clean canvas 800x800 for high resolution tracing
  const fontSize = 520;
  const baselineY = 580;
  // Define constant svg set to `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800">
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800">
    <rect width="800" height="800" fill="white"/>
    <text x="400" y="${baselineY}" font-family="Helvetica Neue, Arial, sans-serif" font-weight="${weight}" font-size="${fontSize}" text-anchor="middle" fill="black">${escapedChar}</text>
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
      // Define constant scale set to 1024 / 800;
      const scale = 1024 / 800;
      // Define constant path set to svgDToFontPath(match[1], baselineY, scale);
      const path = svgDToFontPath(match[1], baselineY, scale);
      // Define constant bbox set to path.getBoundingBox();
      const bbox = path.getBoundingBox();
      // Define constant glyphWidth set to bbox.x2 - bbox.x1;
      const glyphWidth = bbox.x2 - bbox.x1;
      // Define constant adv set to Math.max(Math.round(glyphWidth + 120), 400);
      const adv = Math.max(Math.round(glyphWidth + 120), 400);
      // Execute statement: resolve({ path, adv });
      resolve({ path, adv });
    });
  });
}

// Define asynchronous function run()
async function run() {
  // Define constant chars set to ['#', '@', '&', '*', '_', '-', '+', '=', '/', '\\', '<', '>', '{', '}', '[', ']'];
  const chars = ['#', '@', '&', '*', '_', '-', '+', '=', '/', '\\', '<', '>', '{', '}', '[', ']'];
  // Log diagnostic message to console: 'Generating symbols test...'
  console.log('Generating symbols test...');
  // Declare variable svgParts initialized to [`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="0 0 1200 500" style="background:#0f172a">`];
  let svgParts = [`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="0 0 1200 500" style="background:#0f172a">`];
  // Execute statement: svgParts.push(`<line x1="0" y1="200" x2="1200" y2="200" stroke="#334155" stroke-dasharray="4,4"/>`);
  svgParts.push(`<line x1="0" y1="200" x2="1200" y2="200" stroke="#334155" stroke-dasharray="4,4"/>`);
  // Execute statement: svgParts.push(`<line x1="0" y1="400" x2="1200" y2="400" stroke="#334155" stroke-dasharray="4,4"/>`);
  svgParts.push(`<line x1="0" y1="400" x2="1200" y2="400" stroke="#334155" stroke-dasharray="4,4"/>`);

  // Declare variable x initialized to 40;
  let x = 40;
  // Declare variable y initialized to 200;
  let y = 200;
  // Execute statement: for (let i = 0; i < chars.length; i++) {
  for (let i = 0; i < chars.length; i++) {
    // Define constant ch set to chars[i];
    const ch = chars[i];
    // Check condition: i === 8
    if (i === 8) {
      // Set x to 40;
      x = 40;
      // Set y to 400;
      y = 400;
    }
    // Define constant res set to await traceCleanSymbol(ch, false);
    const res = await traceCleanSymbol(ch, false);
    // Draw in font coordinate scale (1024 -> 60px display scale)
    const scale = 50 / 1024;
    // Define constant scaledPath set to new opentype.Path();
    const scaledPath = new opentype.Path();
    // Execute statement: for (const cmd of res.path.commands) {
    for (const cmd of res.path.commands) {
      // Check condition: cmd.type === 'M') scaledPath.moveTo(x + cmd.x * scale, y - cmd.y * scale
      if (cmd.type === 'M') scaledPath.moveTo(x + cmd.x * scale, y - cmd.y * scale);
      // Alternative condition check: cmd.type === 'L') scaledPath.lineTo(x + cmd.x * scale, y - cmd.y * scale
      else if (cmd.type === 'L') scaledPath.lineTo(x + cmd.x * scale, y - cmd.y * scale);
      // Alternative condition check: cmd.type === 'C') scaledPath.bezierCurveTo(x + cmd.x1 * scale, y - cmd.y1 * scale, x + cmd.x2 * scale, y - cmd.y2 * scale, x + cmd.x * scale, y - cmd.y * scale
      else if (cmd.type === 'C') scaledPath.bezierCurveTo(x + cmd.x1 * scale, y - cmd.y1 * scale, x + cmd.x2 * scale, y - cmd.y2 * scale, x + cmd.x * scale, y - cmd.y * scale);
      // Alternative condition check: cmd.type === 'Q') scaledPath.quadTo(x + cmd.x1 * scale, y - cmd.y1 * scale, x + cmd.x * scale, y - cmd.y * scale
      else if (cmd.type === 'Q') scaledPath.quadTo(x + cmd.x1 * scale, y - cmd.y1 * scale, x + cmd.x * scale, y - cmd.y * scale);
      // Alternative condition check: cmd.type === 'Z' || cmd.type === 'z') scaledPath.close(
      else if (cmd.type === 'Z' || cmd.type === 'z') scaledPath.close();
    }
    // Define constant esc set to ch === '&' ? '&amp;' : (ch === '<' ? '&lt;' : (ch === '>' ? '&gt;' : ch));
    const esc = ch === '&' ? '&amp;' : (ch === '<' ? '&lt;' : (ch === '>' ? '&gt;' : ch));
    // Execute statement: svgParts.push(`<text x="${x}" y="${y + 35}" fill="#94a3b8" font-size="14" font-family="monospace">${esc}</text>`);
    svgParts.push(`<text x="${x}" y="${y + 35}" fill="#94a3b8" font-size="14" font-family="monospace">${esc}</text>`);
    // Execute statement: svgParts.push(scaledPath.toSVG({ fill: '#f8fafc' }));
    svgParts.push(scaledPath.toSVG({ fill: '#f8fafc' }));
    // Execute statement: x += Math.round(res.adv * scale) + 30;
    x += Math.round(res.adv * scale) + 30;
  }
  // Execute statement: svgParts.push(`</svg>`);
  svgParts.push(`</svg>`);
  // Execute statement: fs.writeFileSync('Julius_Test/clean_symbols_test.svg', svgParts.join('\n'));
  fs.writeFileSync('Julius_Test/clean_symbols_test.svg', svgParts.join('\n'));
  // Asynchronously await promise resolution: sharp('Julius_Test/clean_symbols_test.svg').png().toFile('Julius_Test/clean_symbols_test.png');
  await sharp('Julius_Test/clean_symbols_test.svg').png().toFile('Julius_Test/clean_symbols_test.png');
  // Log diagnostic message to console: 'Saved Julius_Test/clean_symbols_test.png'
  console.log('Saved Julius_Test/clean_symbols_test.png');
}

// Execute statement: run().catch(console.error);
run().catch(console.error);
