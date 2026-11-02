const potrace = require('../.agents/skills/draw-your-font/engine/node_modules/potrace');
const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const opentype = require('../.agents/skills/draw-your-font/engine/node_modules/opentype.js');
const fs = require('fs');
const path = require('path');

// Render an SVG with standard serif `@` and `&` at 500x500, trace with potrace
async function traceChar(char, fontSize = 420) {
  // Define constant svg set to `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
    <rect width="600" height="600" fill="white"/>
    <text x="300" y="440" font-family="Times New Roman, Georgia, serif" font-size="${fontSize}" text-anchor="middle" fill="black">${char === "&" ? "&amp;" : (char === "<" ? "&lt;" : char)}</text>
  </svg>`;

  // Define constant png set to await sharp(Buffer.from(svg)).png().toBuffer();
  const png = await sharp(Buffer.from(svg)).png().toBuffer();

  // Return value new Promise((resolve, reject) => { to caller
  return new Promise((resolve, reject) => {
    // Execute statement: potrace.trace(png, {
    potrace.trace(png, {
      // Define property turdSize with type 4,
      turdSize: 4,
      // Define property optTolerance with type 0.2,
      optTolerance: 0.2,
      // Define property threshold with type 128
      threshold: 128
    }, (err, svgOut) => {
      // Check condition: err) return reject(err
      if (err) return reject(err);
      // Extract d attribute from path
      const match = svgOut.match(/d="([^"]+)"/);
      // Check condition: !match) return resolve(new opentype.Path()
      if (!match) return resolve(new opentype.Path());
      // Define constant d set to match[1];
      const d = match[1];
      // Convert SVG path to opentype.Path, scale from 600x600 to font units (1024 UPM)
      // Note: SVG Y is down (0 at top, 600 at bottom). Font Y is up (0 at baseline y=440).
      // So fontY = (440 - svgY) * (1024 / 600)
      const scale = 1024 / 600;
      // Define constant fontPath set to svgDToFontPath(d, 440, scale);
      const fontPath = svgDToFontPath(d, 440, scale);
      // Execute statement: resolve(fontPath);
      resolve(fontPath);
    });
  });
}

// Define function svgDToFontPath(d, baselineY, scale)
function svgDToFontPath(d, baselineY, scale) {
  // Define constant p set to new opentype.Path();
  const p = new opentype.Path();
  // Simple SVG path parser for M, L, C, Q, Z
  const tokens = d.match(/([a-zA-Z]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)/g);
  // Check condition: !tokens
  if (!tokens) return p;

  // Declare variable i initialized to 0;
  let i = 0;
  // Declare variable cmd initialized to '';
  let cmd = '';

  // Define function nextNum()
  function nextNum() {
    // Return value parseFloat(tokens[i++]); to caller
    return parseFloat(tokens[i++]);
  }

  // Define function toFontX(x) { return Math.round(x * scale)
  function toFontX(x) { return Math.round(x * scale); }
  // Define function toFontY(y) { return Math.round((baselineY - y) * scale)
  function toFontY(y) { return Math.round((baselineY - y) * scale); }

  // Execute statement: while (i < tokens.length) {
  while (i < tokens.length) {
    // Define constant t set to tokens[i++];
    const t = tokens[i++];
    // Check condition: /^[a-zA-Z]$/.test(t)
    if (/^[a-zA-Z]$/.test(t)) {
      // Set cmd to t;
      cmd = t;
    // Execute statement: } else {
    } else {
      // Execute statement: i--; // rewind token if it was a number
      i--; // rewind token if it was a number
    }

    // Check condition: cmd === 'M'
    if (cmd === 'M') {
      // Define constant x set to nextNum(), y = nextNum();
      const x = nextNum(), y = nextNum();
      // Execute statement: p.moveTo(toFontX(x), toFontY(y));
      p.moveTo(toFontX(x), toFontY(y));
    // Execute statement: } else if (cmd === 'L') {
    } else if (cmd === 'L') {
      // Define constant x set to nextNum(), y = nextNum();
      const x = nextNum(), y = nextNum();
      // Execute statement: p.lineTo(toFontX(x), toFontY(y));
      p.lineTo(toFontX(x), toFontY(y));
    // Execute statement: } else if (cmd === 'C') {
    } else if (cmd === 'C') {
      // Define constant x1 set to nextNum(), y1 = nextNum();
      const x1 = nextNum(), y1 = nextNum();
      // Define constant x2 set to nextNum(), y2 = nextNum();
      const x2 = nextNum(), y2 = nextNum();
      // Define constant x set to nextNum(), y = nextNum();
      const x = nextNum(), y = nextNum();
      // Execute statement: p.bezierCurveTo(toFontX(x1), toFontY(y1), toFontX(x2), toFontY(y2), toFontX(x), toFontY(y));
      p.bezierCurveTo(toFontX(x1), toFontY(y1), toFontX(x2), toFontY(y2), toFontX(x), toFontY(y));
    // Execute statement: } else if (cmd === 'Q') {
    } else if (cmd === 'Q') {
      // Define constant x1 set to nextNum(), y1 = nextNum();
      const x1 = nextNum(), y1 = nextNum();
      // Define constant x set to nextNum(), y = nextNum();
      const x = nextNum(), y = nextNum();
      // Execute statement: p.quadTo(toFontX(x1), toFontY(y1), toFontX(x), toFontY(y));
      p.quadTo(toFontX(x1), toFontY(y1), toFontX(x), toFontY(y));
    // Execute statement: } else if (cmd === 'Z' || cmd === 'z') {
    } else if (cmd === 'Z' || cmd === 'z') {
      // Execute statement: p.close();
      p.close();
    }
  }

  // Return value p; to caller
  return p;
}

// Define asynchronous function test()
async function test() {
  // Define constant atPath set to await traceChar('@', 420);
  const atPath = await traceChar('@', 420);
  // Define constant ampPath set to await traceChar('&', 420);
  const ampPath = await traceChar('&', 420);

  // Define constant rawFont set to new opentype.Font({
  const rawFont = new opentype.Font({
    // Define property familyName with type 'TestTraced',
    familyName: 'TestTraced',
    // Define property styleName with type 'Regular',
    styleName: 'Regular',
    // Define property unitsPerEm with type 1024,
    unitsPerEm: 1024,
    // Define property ascender with type 743,
    ascender: 743,
    // Define property descender with type -266,
    descender: -266,
    // Define property glyphs with type [
    glyphs: [
      // Execute statement: new opentype.Glyph({ name: '.notdef', unicode: 0, advanceWidth: 500, path: new opentype.Path() }),
      new opentype.Glyph({ name: '.notdef', unicode: 0, advanceWidth: 500, path: new opentype.Path() }),
      // Execute statement: new opentype.Glyph({ name: 'space', unicode: 32, advanceWidth: 300, path: new opentype.Path() }),
      new opentype.Glyph({ name: 'space', unicode: 32, advanceWidth: 300, path: new opentype.Path() }),
      // Execute statement: new opentype.Glyph({ name: 'at', unicode: 64, advanceWidth: 700, path: atPath }),
      new opentype.Glyph({ name: 'at', unicode: 64, advanceWidth: 700, path: atPath }),
      // Execute statement: new opentype.Glyph({ name: 'ampersand', unicode: 38, advanceWidth: 640, path: ampPath }),
      new opentype.Glyph({ name: 'ampersand', unicode: 38, advanceWidth: 640, path: ampPath }),
    ]
  });

  // Define constant buf set to Buffer.from(rawFont.toArrayBuffer());
  const buf = Buffer.from(rawFont.toArrayBuffer());
  // Define constant font set to opentype.parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
  const font = opentype.parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300">
    <rect width="600" height="300" fill="#161b22"/>
    <g fill="#f59e0b">
      ${font.getPath('@ &', 50, 220, 160).toSVG(2)}
    </g>
  </svg>`;

  fs.writeFileSync(path.join(__dirname, 'test_potrace_symbols.svg'), svg);
  await sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'test_potrace_symbols.png'));
  console.log('Saved test_potrace_symbols.png');
}

test().catch(console.error);
